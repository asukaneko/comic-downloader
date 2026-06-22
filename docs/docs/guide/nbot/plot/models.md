# Plot 数据模型

定义剧情图系统的核心数据结构：节点、选择、边。

## PlotNode

剧情节点，代表故事中的一个关键时刻。每个节点捕获该时刻的完整上下文快照。

```python
from nbot.plot import PlotNode

node = PlotNode(
    conversation_id="conv_abc",
    character_id="char_xyz",
    title="初次相遇",
    summary="在公园里偶遇了角色",
    level="important",
    scene={"location": "公园", "time": "傍晚"},
)
```

### 核心字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | 自动生成，前缀 `pn_` |
| `conversation_id` | `str` | 所属会话 |
| `character_id` | `str` | 关联角色 |
| `title` | `str` | 节点标题 |
| `summary` | `str` | 剧情摘要 |
| `level` | `str` | 重要性：`normal` / `important` / `turning_point` / `ending` |
| `created_at` | `str` | ISO 时间戳，自动生成 |

### 场景与快照

| 字段 | 类型 | 说明 |
|------|------|------|
| `scene` | `dict` | 场景信息（地点、时间等） |
| `state_snapshot` | `dict` | 角色状态快照（mood, energy） |
| `relationship_snapshot` | `dict` | 关系状态快照（affection, trust, familiarity 等） |

### 分支与消息

| 字段 | 类型 | 说明 |
|------|------|------|
| `parent_node_id` | `str` | 父节点 ID（构建树形结构） |
| `selected_choice_id` | `str` | 已选择的选项 ID |
| `user_message` | `dict` | 用户消息快照（用于分支物化） |
| `assistant_message` | `dict` | 助手消息快照（含 `id`、`content`、`audio_url`） |

### v3.1 Activity Graph 扩展

| 字段 | 类型 | 说明 |
|------|------|------|
| `activity_type` | `str` | 活动类型：`chat` / `group` / `event` / `quest` / `ending` |
| `participants` | `list[str]` | 参与者角色 ID 列表 |
| `location` | `str` | 场景地点 |
| `mood` | `str` | 整体氛围 |
| `world_changes` | `dict` | 世界状态变化记录 |
| `memory_refs` | `list[str]` | 关联记忆 ID |
| `review_score` | `dict[str, float]` | Review 评分快照 |

### 序列化

```python
# 转为字典
data = node.to_dict()

# 从字典恢复
node = PlotNode.from_dict(data)
```

## PlotChoice

玩家在某个节点可做的剧情选择。每个节点最多有 3 个未选中的选择。

```python
from nbot.plot import PlotChoice

choice = PlotChoice(
    node_id="pn_abc",
    text="轻轻握住她的手",
    level="important",
    intent="推进关系",
)
```

### 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | 自动生成，前缀 `pc_` |
| `node_id` | `str` | 所属节点 ID |
| `text` | `str` | 选择文本（第一人称可直接发送的消息） |
| `level` | `str` | `normal` / `important` / `turning_point` / `ending` / `hidden` |
| `intent` | `str` | 选择意图描述 |
| `selected` | `bool` | 是否已被选择 |
| `created_at` | `str` | ISO 时间戳 |

### v3.1 扩展

| 字段 | 类型 | 说明 |
|------|------|------|
| `risk` | `str` | 风险等级：`low` / `medium` / `high` |
| `expected_effect` | `dict` | 预期效果（relationship, world, plot） |
| `hidden_requirements` | `dict` | 隐藏条件，如 `{"affection_gte": 80, "trust_gte": 60}` |

## PlotEdge

连接两个节点的边，表示某个选择导致的剧情走向。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | 自动生成，前缀 `pe_` |
| `from_node_id` | `str` | 起始节点 |
| `to_node_id` | `str` | 目标节点 |
| `choice_id` | `str` | 关联的选择 ID |
| `label` | `str` | 边标签（通常为选择文本） |

## 数据关系

```
PlotNode (pn_001)
  ├── PlotChoice (pc_001, selected=true)
  │     └── PlotEdge (pe_001, pn_001 → pn_002)
  ├── PlotChoice (pc_002, selected=false)
  └── PlotChoice (pc_003, selected=false)

PlotNode (pn_002)
  ├── PlotChoice (pc_004, selected=false)
  └── ...
```

一个节点可以有多个子分支（通过不同 choice 连接到不同子节点），形成树状剧情图。
