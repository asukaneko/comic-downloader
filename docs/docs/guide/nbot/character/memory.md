# 角色记忆服务

角色记忆服务按角色+用户隔离的记忆检索与存储。

## 概述

第一版使用 `PromptManagerMemoryAdapter` 包装旧 auto_memory 系统，保持与现有 `data/memories.json` 的兼容。后续逐步迁移到独立的角色记忆存储。

## PromptManagerMemoryAdapter

包装 `nbot.core.prompt` 中的 `PromptManager`，提供按 `character_id` + `target_id` 检索记忆的能力。

```python
class PromptManagerMemoryAdapter:
    def search(
        self,
        character_id: str = "",
        target_id: str = "",
        query: str = "",
        limit: int = 8,
    ) -> List[CharacterMemory]

    def save(
        self,
        character_id: str,
        target_id: str,
        title: str,
        content: str,
        summary: str = "",
        mem_type: str = "long",
    ) -> bool

    def delete(self, memory_id: str) -> bool
```

## 记忆检索

```python
def search(
    self,
    character_id: str = "",
    target_id: str = "",
    query: str = "",
    limit: int = 8,
) -> List[CharacterMemory]:
    """
    检索相关记忆

    Args:
        character_id: 角色ID
        target_id: 目标用户ID
        query: 查询文本
        limit: 最大返回数量

    Returns:
        CharacterMemory 列表
    """
```

### 检索示例

```python
from nbot.character.memory import PromptManagerMemoryAdapter

memory_service = PromptManagerMemoryAdapter()

# 检索记忆
memories = memory_service.search(
    character_id="neko_girl",
    target_id="user_123",
    query="用户喜欢什么",
    limit=8,
)

for mem in memories:
    print(f"{mem.title}: {mem.summary}")
```

## 保存记忆

```python
def save(
    self,
    character_id: str,
    target_id: str,
    title: str,
    content: str,
    summary: str = "",
    mem_type: str = "long",
) -> bool:
    """
    保存记忆

    Args:
        character_id: 角色ID
        target_id: 目标用户ID
        title: 记忆标题
        content: 记忆内容
        summary: 记忆摘要
        mem_type: 记忆类型

    Returns:
        是否保存成功
    """
```

### 保存示例

```python
# 保存记忆
success = memory_service.save(
    character_id="neko_girl",
    target_id="user_123",
    title="用户喜欢科幻小说",
    content="用户说他最喜欢《三体》",
    summary="用户喜欢科幻小说，特别是《三体》",
    mem_type="preference",
)
```

## 删除记忆

```python
success = memory_service.delete(memory_id="mem_123")
```

## 记忆抽取

```python
def extract_and_save_if_needed(
    self,
    chat_request,
    result,
    turn_context: CharacterTurnContext,
) -> None:
    """
    记忆抽取（委托给旧 auto_memory 系统）

    第一版不在此处实现独立抽取，继续使用 Pipeline 中的 auto_memory 阶段。
    后续版本在此实现按角色+用户的记忆抽取。
    """
```

## CharacterMemory 数据结构

```python
@dataclass
class CharacterMemory:
    id: str                 # 记忆ID
    character_id: str       # 角色ID
    target_id: str          # 目标用户ID

    type: str = "long"      # 记忆类型
    title: str = ""         # 标题
    summary: str = ""       # 摘要
    content: str = ""       # 内容

    importance: int = 5     # 重要程度 1-10
    emotion_impact: Dict = {}    # 情绪影响
    source_turn_id: str = None   # 来源回合ID

    created_at: str = ""    # 创建时间
    expires_at: str = None  # 过期时间
```

## 记忆类型

```
preference   # 用户偏好
promise      # 承诺
event        # 事件
relationship # 关系节点
fact         # 稳定事实
short        # 短期记忆
long         # 长期记忆
```

## 在 Runtime 中使用

```python
from nbot.character.runtime import CharacterRuntime
from nbot.character.memory import PromptManagerMemoryAdapter

runtime = CharacterRuntime(
    profile_repo=profile_repo,
    state_repo=state_repo,
    relationship_repo=relationship_repo,
    memory_service=PromptManagerMemoryAdapter(),  # 记忆服务
    signal_analyzer=signal_analyzer,
    planner=planner,
    state_machine=state_machine,
)

# before_turn 会自动检索记忆
turn_context = runtime.before_turn(chat_request, identity)

# turn_context.memories 包含相关记忆
for mem in turn_context.memories:
    print(f"{mem.title}: {mem.summary}")
```

## 后续规划

- [ ] 独立 CharacterMemoryService
- [ ] 向量检索支持
- [ ] 记忆重要性自动评估
- [ ] 记忆过期自动清理
- [ ] 跨角色记忆共享
