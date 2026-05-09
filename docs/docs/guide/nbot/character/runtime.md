# 运行时引擎 (CharacterRuntime)

CharacterRuntime 是角色模拟的编排中心，负责协调各个模块完成角色模拟的完整生命周期。

## 职责

`CharacterRuntime` 只做角色模拟编排，不直接处理 HTTP / Socket / QQ。

```python
class CharacterRuntime:
    def __init__(
        self,
        profile_repo,        # 角色卡仓库
        state_repo,          # 状态仓库
        relationship_repo,   # 关系仓库
        memory_service,      # 记忆服务
        signal_analyzer,     # 信号分析器
        planner,             # 反应计划生成器
        prompt_builder,      # 提示词构建器
        state_machine,       # 状态机
    )
```

## before_turn

每轮对话前的角色模拟编排。

```python
def before_turn(self, chat_request, identity: CharacterIdentity) -> CharacterTurnContext:
    """
    Args:
        chat_request: 统一聊天请求
        identity: 角色身份标识

    Returns:
        CharacterTurnContext 包含本轮所有角色上下文
    """
```

### 执行流程

```
before_turn
├── 读取角色卡 (profile_repo.get)
├── 读取或创建角色运行时状态 (state_repo.get_or_create)
├── 读取或创建关系状态 (relationship_repo.get_or_create)
├── 检索相关记忆 (memory_service.search)
├── 分析用户输入信号 (signal_analyzer.analyze)
├── 生成反应计划 (planner.plan)
└── 编译提示词 (prompt_builder.build)
```

### 代码示例

```python
from nbot.character.runtime import CharacterRuntime
from nbot.character.models import CharacterIdentity

# 创建身份标识
identity = CharacterIdentity(
    character_id="neko_girl",
    target_id="user_123",
    scope_id="web:session_456",
    channel="web"
)

# 执行 before_turn
turn_context = runtime.before_turn(chat_request, identity)

# 使用 turn_context
print(turn_context.profile.name)           # 角色名称
print(turn_context.state.mood)             # 当前心情
print(turn_context.relationship.affection) # 好感度
print(turn_context.plan.visible_emotion)   # 计划表现的情绪
print(turn_context.prompt_text)            # 编译后的提示词
```

## after_turn

每轮对话后的状态更新。

```python
def after_turn(self, chat_request, result, turn_context: CharacterTurnContext) -> None:
    """
    Args:
        chat_request: 统一聊天请求
        result: PipelineResult
        turn_context: before_turn 返回的上下文
    """
```

### 执行流程

```
after_turn
├── 应用状态变化 (state_machine.apply)
│   ├── 更新角色状态
│   └── 更新关系状态
├── 保存状态
│   ├── state_repo.save
│   └── relationship_repo.save
└── 记忆抽取 (memory_service.extract_and_save_if_needed)
```

### 代码示例

```python
# 模型调用完成后
result = await model.chat(messages)

# 执行 after_turn 更新状态
runtime.after_turn(chat_request, result, turn_context)

# 状态已自动保存
```

## 完整使用示例

```python
from nbot.character.runtime import CharacterRuntime
from nbot.character.repository import (
    ProfileRepository,
    CharacterStateRepository,
    RelationshipRepository,
)
from nbot.character.policies import SignalAnalyzer
from nbot.character.planner import ReactionPlanner
from nbot.character.state_machine import StateMachine
from nbot.character.memory import PromptManagerMemoryAdapter
from nbot.character.models import CharacterIdentity

# 初始化运行时
runtime = CharacterRuntime(
    profile_repo=ProfileRepository(base_dir),
    state_repo=CharacterStateRepository(base_dir),
    relationship_repo=RelationshipRepository(base_dir),
    memory_service=PromptManagerMemoryAdapter(),
    signal_analyzer=SignalAnalyzer(),
    planner=ReactionPlanner(),
    prompt_builder=None,  # 使用默认
    state_machine=StateMachine(),
)

# 创建身份标识
identity = CharacterIdentity(
    character_id="neko_girl",
    target_id="user_123",
    scope_id="web:session_456",
    channel="web"
)

# before_turn: 准备角色上下文
turn_context = runtime.before_turn(chat_request, identity)

# 使用编译后的提示词
messages = [
    {"role": "system", "content": turn_context.prompt_text},
    *history_messages,
]

# 调用模型
result = await model.chat(messages)

# after_turn: 更新状态
runtime.after_turn(chat_request, result, turn_context)
```

## 可选依赖

所有依赖都是可选的，如果某个模块为 None，则跳过对应功能：

```python
# 最小化运行时（只编译角色卡）
runtime = CharacterRuntime(
    profile_repo=profile_repo,
)

# 完整运行时
runtime = CharacterRuntime(
    profile_repo=profile_repo,
    state_repo=state_repo,
    relationship_repo=relationship_repo,
    memory_service=memory_service,
    signal_analyzer=signal_analyzer,
    planner=planner,
    prompt_builder=prompt_builder,
    state_machine=state_machine,
)
```

## 错误处理

运行时内部已经处理了各模块的异常，不会因为某个模块失败而导致整体失败：

```python
# _search_memories 内部捕获异常
def _search_memories(self, identity, chat_request):
    try:
        return self.memory_service.search(...)
    except Exception:
        return []  # 失败返回空列表

# _analyze_signals 内部捕获异常
def _analyze_signals(self, chat_request, state, relationship):
    try:
        return self.signal_analyzer.analyze(...)
    except Exception:
        return None  # 失败返回 None
```

## 与 Pipeline 集成

```python
class AIPipeline:
    def _phase_character_runtime_before_turn(self, ctx, callbacks):
        runtime = callbacks.get_character_runtime(ctx)
        identity = callbacks.get_character_context(ctx)

        if not runtime or not identity:
            return

        turn = runtime.before_turn(ctx.chat_request, identity)
        ctx.character_turn = turn

        ctx.prompt_stack.add(
            "character.runtime",
            turn.prompt_text,
            priority=30,
        )

    def _phase_character_runtime_after_turn(self, ctx, callbacks, result):
        runtime = callbacks.get_character_runtime(ctx)
        identity = callbacks.get_character_context(ctx)

        if not runtime or not identity or not ctx.character_turn:
            return

        runtime.after_turn(
            chat_request=ctx.chat_request,
            result=result,
            turn_context=ctx.character_turn,
        )
```

## 性能考虑

- **状态缓存**: repository 内部有缓存机制，避免频繁文件 IO
- **记忆检索**: 限制返回数量（默认 8 条）
- **异步友好**: 不阻塞主线程，可在异步环境中使用
