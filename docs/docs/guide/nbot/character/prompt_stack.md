# 动态提示词栈 (PromptStack)

PromptStack 是实时情感引擎的核心机制，允许任意模块在任意阶段注册提示词注入项，最终统一合成为本轮顶部 system prompt。

## 核心原则

1. **动态注入只在本轮请求生效** - 不写入历史消息，避免污染
2. **按优先级排序合成** - 数值越小越靠前
3. **可调试、可观察** - 可以查看本轮所有注入项

## 为什么需要 PromptStack

当前提示词注入只能依赖第一条 system message，存在以下问题：

- 知识库、角色状态、记忆、工具规则都在抢同一个 system prompt
- 动态注入容易污染历史
- 无法观察本轮到底注入了哪些内容
- 后续角色系统拆分困难

PromptStack 的目标是：**允许任意模块在任意阶段注册提示词注入项，但最终统一合成为本轮顶部 system/developer prompt。**

## 数据结构

### PromptInjection

```python
@dataclass
class PromptInjection:
    key: str                # 注入项标识
    content: str            # 注入内容
    priority: int = 100     # 优先级
    role: str = "system"    # 角色: system/developer
    scope: str = "turn"     # 作用域: global/session/turn
    enabled: bool = True    # 是否启用
```

### PromptStack

```python
class PromptStack:
    # 推荐优先级常量
    PRIORITY_SAFETY = 10
    PRIORITY_BEHAVIOR = 20
    PRIORITY_CHARACTER_PROFILE = 30
    PRIORITY_CHARACTER_STATE = 40
    PRIORITY_CHARACTER_RELATIONSHIP = 50
    PRIORITY_CHARACTER_MEMORIES = 60
    PRIORITY_KNOWLEDGE_RAG = 70
    PRIORITY_TOOL_INSTRUCTIONS = 80
    PRIORITY_REACTION_PLAN = 90

    def add(key, content, priority=100, role="system", scope="turn")
    def remove(key) -> bool
    def get(key) -> Optional[PromptInjection]
    def render(base_prompt="") -> str
    def render_debug() -> List[Dict]
    def clear_scope(scope) -> int
```

## 推荐优先级

```
10  global.safety           # 安全规则
20  app.behavior            # 应用行为
30  character.profile       # 角色卡
40  character.runtime_state # 角色运行时状态
50  character.relationship  # 关系状态
60  character.memories      # 角色记忆
70  knowledge.rag           # 知识库
80  tool.instructions       # 工具说明
90  character.reaction_plan # 反应计划
```

## 使用示例

### 基本使用

```python
from nbot.character.prompt_stack import PromptStack

stack = PromptStack()

# 注册提示词注入项
stack.add(
    key="character.runtime_state",
    content="当前心情: 开心\n情绪强度: 0.8",
    priority=PromptStack.PRIORITY_CHARACTER_STATE,
)

stack.add(
    key="character.relationship",
    content="好感: 75/100\n信任: 60/100",
    priority=PromptStack.PRIORITY_CHARACTER_RELATIONSHIP,
)

# 合成最终提示词
composed_prompt = stack.render(base_prompt)
```

### 同 key 替换

```python
# 第一次添加
stack.add("character.state", "心情: 开心", priority=40)

# 同 key 会替换之前的内容
stack.add("character.state", "心情: 委屈", priority=40)

# 最终只有 "心情: 委屈"
```

### 分离 system prompt

```python
from nbot.character.prompt_stack import split_system_prompt

# 从消息列表中分离 system prompt
messages = [
    {"role": "system", "content": "你是助手"},
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！"},
]

base_prompt, history = split_system_prompt(messages)
# base_prompt = "你是助手"
# history = [{"role": "user", ...}, {"role": "assistant", ...}]
```

### 最终 messages 结构

```python
# 不要在历史中间插 system
# 推荐每轮请求前重新合成

messages = [
    {"role": "system", "content": composed_system_prompt},
    *history_without_old_system,
]
```

## 在 Pipeline 中使用

```python
def _phase_prepare_context(self, ctx, callbacks):
    # 分离基础 system prompt
    base_prompt, history_messages = split_system_prompt(messages_for_ai)

    # 知识库注入
    if ctx.knowledge_text:
        ctx.prompt_stack.add(
            "knowledge.rag",
            ctx.knowledge_text,
            priority=PromptStack.PRIORITY_KNOWLEDGE_RAG,
        )

    # 角色运行时注入
    if ctx.character_turn:
        ctx.prompt_stack.add(
            "character.runtime",
            ctx.character_turn.prompt_text,
            priority=PromptStack.PRIORITY_CHARACTER_PROFILE,
        )

    # 统一合成
    composed_system = ctx.prompt_stack.render(base_prompt)
    messages_for_ai = [
        {"role": "system", "content": composed_system},
        *history_messages,
    ]
```

## 调试

```python
# 获取调试信息
debug_info = stack.render_debug()
# [
#   {
#     "key": "character.runtime_state",
#     "content": "当前心情: 开心...",
#     "priority": 40,
#     "role": "system",
#     "scope": "turn",
#     "enabled": True
#   },
#   ...
# ]

# 获取所有 key
keys = stack.keys  # ["character.runtime_state", "character.relationship", ...]

# 清除指定作用域
stack.clear_scope("turn")  # 返回清除的数量
```

## 作用域说明

```python
# global - 全局作用域，跨会话有效
stack.add("global.safety", "...", scope="global")

# session - 会话作用域，当前会话有效
stack.add("session.context", "...", scope="session")

# turn - 回合作用域，仅本轮有效（默认）
stack.add("character.state", "...", scope="turn")
```

## 最佳实践

1. **使用推荐优先级** - 保持注入顺序一致
2. **设置合理的 key** - 便于调试和替换
3. **避免空内容** - 空内容不会添加到 stack
4. **及时清理** - 回合结束后清理 turn 作用域
5. **不要污染历史** - 动态内容只通过 PromptStack 注入
