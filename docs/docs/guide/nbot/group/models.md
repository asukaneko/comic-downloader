# Group 数据模型

定义群聊系统的核心数据结构：配置、会话、角色间关系。

## GroupConfig

群聊配置，控制群聊的行为参数。

```python
from nbot.group import GroupConfig

config = GroupConfig(
    speaker_strategy="mention",
    max_chars_per_turn=800,
    allow_character_cross_talk=True,
    shared_memory=True,
    token_budget=4000,
    auto_narrate=True,
    narrate_interval=3,
    cross_talk_max_mentions=5,
    round_robin_mode="async",
)
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `speaker_strategy` | `str` | `"mention"` | 发言策略（见 [scheduler.md](./scheduler.md)） |
| `max_chars_per_turn` | `int` | `800` | 每轮最大字符数 |
| `allow_character_cross_talk` | `bool` | `True` | 允许角色间 @mention 跨角色对话 |
| `shared_memory` | `bool` | `True` | 角色间共享记忆 |
| `token_budget` | `int` | `4000` | 单轮 Token 预算 |
| `auto_narrate` | `bool` | `True` | 自动旁白 |
| `narrate_interval` | `int` | `3` | 每 N 轮触发一次旁白 |
| `cross_talk_max_mentions` | `int` | `5` | 每轮最多处理的 @mention 数量 |
| `round_robin_mode` | `str` | `"async"` | 轮询模式：`async`（异步并行）或 `sequential`（顺序回复） |

## GroupConversation

群聊会话实体，包含角色列表、发言队列、关系矩阵等。

```python
from nbot.group import GroupManager

gm = GroupManager.instance()
group = gm.create_group(
    name="咖啡馆闲聊",
    character_ids=["char_a", "char_b", "char_c"],
    narrator_id="char_a",
    config=config,
)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `group_id` | `str` | 群聊 ID（自动 `gc_` 前缀） |
| `name` | `str` | 群聊名称 |
| `character_ids` | `list[str]` | 参与角色 ID 列表 |
| `narrator_id` | `str \| None` | 旁白角色 ID（可选） |
| `active_speaker` | `str` | 当前发言者 |
| `speaker_queue` | `list[str]` | 发言队列 |
| `config` | `GroupConfig` | 群聊配置 |
| `turn_count` | `int` | 回合计数 |
| `bound_channel` | `str` | 绑定的频道 ID |
| `relations` | `dict[str, InterCharacterRelation]` | 角色间关系矩阵（key 为 `a::b`） |
| `created_at` | `float` | 创建时间戳 |
| `updated_at` | `float` | 更新时间戳 |

### 方法

```python
# 获取两个角色的关系
relation = group.get_relation("char_a", "char_b")

# 设置关系
group.set_relation(relation)

# 获取关系矩阵（所有关系的列表）
matrix = group.get_relation_matrix()

# 推进回合
group.advance_turn()
```

## InterCharacterRelation

角色间关系，四维模型，双向存储。

```python
relation = group.get_relation("char_a", "char_b")
print(relation.familiarity)  # 熟悉度
print(relation.trust)        # 信任度
print(relation.affection)    # 好感度
print(relation.rivalry)      # 竞争度
```

| 字段 | 范围 | 说明 |
|------|------|------|
| `familiarity` | 0-100 | 熟悉程度 |
| `trust` | 0-100 | 信任程度 |
| `affection` | 0-100 | 好感程度 |
| `rivalry` | 0-100 | 竞争/对抗程度 |

### 关系键

关系使用归一化的键存储，确保 A→B 和 B→A 指向同一条记录：

```python
a, b = sorted([char_a, char_b])
key = f"{a}::{b}"  # 例如 "char_001::char_002"
```

### 更新关系

```python
relation.update("affection", 10, "一起经历了冒险")
```

每次变更自动记录到 `history`（最多保留 50 条）：

```json
{
  "dimension": "affection",
  "delta": 10,
  "old": 50,
  "new": 60,
  "reason": "一起经历了冒险",
  "ts": 1719000000.0
}
```

## GroupManager

群聊管理器，负责群聊的 CRUD 和频道绑定。通过 `instance()` 获取全局单例。

详见 [index.md](./index.md) 中的 GroupManager 章节。
