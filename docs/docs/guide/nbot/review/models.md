# Review 数据模型

定义 Review Pipeline 的输入/输出结构，与具体实现解耦。

## ReviewScore

角色体验评分（0-1 浮点数），8 个维度。

```python
from nbot.review.models import ReviewScore

score = ReviewScore(
    character_fidelity=0.8,
    immersion=0.7,
    relationship_progress=0.5,
    story_progress=0.6,
    memory_value=0.4,
    world_consistency=0.9,
    user_engagement=0.6,
    risk=0.1,
)
```

| 字段 | 说明 |
|------|------|
| `character_fidelity` | 角色一致性：回复是否贴合角色设定 |
| `immersion` | 沉浸感：场景描写与情感表达质量 |
| `relationship_progress` | 关系推进：关系是否有实质性发展 |
| `story_progress` | 剧情推进：剧情是否有实质性进展 |
| `memory_value` | 记忆价值：本轮对话是否值得记录 |
| `world_consistency` | 世界一致性：是否与既定世界观/设定一致 |
| `user_engagement` | 用户互动：用户参与度 |
| `risk` | 风险评分：内容是否存在偏离设定或前后矛盾的风险 |

**评分来源：**
- `character_fidelity` / `immersion` / `world_consistency` / `risk`：来自 AutoState 的 LLM 评估缓存
- `memory_value` / `story_progress` / `relationship_progress` / `user_engagement`：规则引擎计算

## MemoryItem

待写入的记忆条目。

```python
from nbot.review.models import MemoryItem

item = MemoryItem(
    target="user",
    mem_type="relationship",
    title="用户表达了喜欢",
    content="用户：我很喜欢你\n角色：谢谢你的喜欢！",
    importance=0.7,
    ttl="long",
)
```

| 字段 | 可选值 | 说明 |
|------|--------|------|
| `target` | `user` / `character` / `world` | 记忆目标 |
| `mem_type` | `short` / `long` / `relationship` / `event` | 记忆类型 |
| `title` | `str` | 记忆标题 |
| `content` | `str` | 记忆内容 |
| `importance` | `float` | 重要性（0-1） |
| `ttl` | `short` / `long` / `permanent` | 保留时间 |

## RelationshipDelta

关系变化结果，六维增量。

```python
from nbot.review.models import RelationshipDelta

delta = RelationshipDelta(
    affection=2,
    trust=1,
    familiarity=1,
    dependency=0,
    security=0,
    jealousy=0,
    reason="用户表达了亲密情感；选择了 important 级剧情分支。",
)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `affection` | `int` | 好感度增量 |
| `trust` | `int` | 信任度增量 |
| `familiarity` | `int` | 熟悉度增量 |
| `dependency` | `int` | 依赖度增量 |
| `security` | `int` | 安全感增量 |
| `jealousy` | `int` | 嫉妒度增量 |
| `reason` | `str` | 变化原因（人类可读） |
| `source` | `str` | 来源（默认 `"review_pipeline"`） |
| `plot_node_id` | `str` | 关联的剧情节点 ID |
| `conversation_id` | `str` | 关联的会话 ID |

## PlotUpdate

剧情更新建议。

| 字段 | 类型 | 说明 |
|------|------|------|
| `should_create_node` | `bool` | 是否需要创建剧情节点 |
| `level` | `str` | 节点级别：`normal` / `important` / `turning_point` / `ending` |
| `summary` | `str` | 剧情摘要 |
| `title` | `str` | 节点标题 |

## WorldBookUpdate

世界书更新建议。

| 字段 | 类型 | 说明 |
|------|------|------|
| `should_update` | `bool` | 是否需要更新世界书 |
| `reason` | `str` | 更新原因 |
| `entry_title` | `str` | 条目标题 |
| `entry_content` | `str` | 条目内容 |

## ReviewInput

Review Pipeline 输入，包含本轮对话的完整上下文。

```python
from nbot.review.models import ReviewInput

inp = ReviewInput(
    conversation_id="conv_abc",
    character_id="char_xyz",
    user_id="user_123",
    user_message="你好，今天天气真好",
    assistant_message="是的，天气很好呢！",
    selected_choice={"level": "normal", "text": "继续聊天"},
    relationship_state={"affection": 75, "trust": 60},
    character_state={"mood": "happy", "energy": 0.8},
    real_time_context={"continuity_level": "continuous", "elapsed_label": "5分钟"},
)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `conversation_id` | `str` | 会话 ID |
| `character_id` | `str` | 角色 ID |
| `user_id` | `str` | 用户 ID |
| `group_id` | `str` | 群聊 ID（可选） |
| `user_message` | `str` | 用户消息 |
| `assistant_message` | `str` | AI 回复 |
| `recent_messages` | `list[dict]` | 最近消息列表 |
| `active_plot_node` | `dict \| None` | 当前激活的剧情节点 |
| `selected_choice` | `dict \| None` | 已选择的剧情选项 |
| `relationship_state` | `dict` | 关系状态 |
| `character_state` | `dict` | 角色状态 |
| `world_context` | `dict` | 世界上下文 |
| `real_time_context` | `dict` | 现实时间上下文 |
| `tool_calls` | `list[dict]` | 工具调用记录 |

## ReviewOutput

Review Pipeline 输出，结构化的审查结果。

```python
from nbot.review.models import ReviewOutput

output = ReviewOutput(
    should_write_memory=True,
    memory_items=[MemoryItem(...)],
    relationship_delta=RelationshipDelta(...),
    plot_update=PlotUpdate(should_create_node=True, level="important"),
    scores=ReviewScore(...),
    source="rule",
    skipped=False,
)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `should_write_memory` | `bool` | 是否需要写入记忆 |
| `memory_items` | `list[MemoryItem]` | 待写入的记忆条目 |
| `relationship_delta` | `RelationshipDelta \| None` | 关系变化增量 |
| `plot_update` | `PlotUpdate \| None` | 剧情更新建议 |
| `world_book_update` | `WorldBookUpdate \| None` | 世界书更新建议 |
| `scores` | `ReviewScore \| None` | 各维度评分 |
| `source` | `str` | 审查来源：`"rule"` 或 `"llm"` |
| `skipped` | `bool` | 是否跳过（普通闲聊） |
