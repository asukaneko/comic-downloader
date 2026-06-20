# events - 事件标准化系统

## 概述

`events` 模块提供标准化事件名常量，涵盖 character、plot、group、world、workflow、review 六大域。所有模块发射事件时应优先使用这里的常量，避免事件名散落在业务代码中。

**核心特性：**
- **统一命名规范** - 采用 `domain.phase.action` 三层命名结构
- **六大事件域** - 覆盖角色、剧情、群聊、世界、工作流、审查全部场景
- **向后兼容** - 与 Hook 系统的 `HookEventType` 完全兼容

## 命名规范

所有事件名遵循 `domain.phase.action` 格式：

```
character.turn.before      # 角色回合开始前
plot.node.created          # 剧情节点创建
group.message.received     # 群聊消息接收
world.event.triggered      # 世界事件触发
workflow.started           # 工作流开始
review.memory.scored       # 记忆审查评分
```

## 事件域一览

### character - 角色对话生命周期

| 常量名 | 事件名 | 说明 |
|--------|--------|------|
| `CHARACTER_TURN_BEFORE` | `character.turn.before` | 角色回合开始前 |
| `CHARACTER_TURN_AFTER` | `character.turn.after` | 角色回合结束后 |
| `CHARACTER_MEMORY_RECALLED` | `character.memory.recalled` | 记忆召回完成 |
| `CHARACTER_MEMORY_REVIEWED` | `character.memory.reviewed` | 记忆审查完成 |
| `CHARACTER_MEMORY_WRITTEN` | `character.memory.written` | 记忆写入完成 |
| `CHARACTER_RELATIONSHIP_CHANGED` | `character.relationship.changed` | 关系状态变化 |
| `CHARACTER_STATE_CHANGED` | `character.state.changed` | 角色状态变化 |
| `CHARACTER_MODEL_GENERATED` | `character.model.generated` | 模型生成完成 |

### plot - 剧情分支系统

| 常量名 | 事件名 | 说明 |
|--------|--------|------|
| `PLOT_NODE_CREATED` | `plot.node.created` | 剧情节点创建 |
| `PLOT_CHOICE_GENERATED` | `plot.choice.generated` | 剧情选项生成 |
| `PLOT_CHOICE_SELECTED` | `plot.choice.selected` | 剧情选项选定 |
| `PLOT_EDGE_CREATED` | `plot.edge.created` | 剧情边创建 |
| `PLOT_ROLLBACK_DONE` | `plot.rollback.done` | 剧情回溯完成 |
| `PLOT_TURNING_POINT_REACHED` | `plot.turning_point.reached` | 到达转折点 |

### group - 群聊 / Agent Society

| 常量名 | 事件名 | 说明 |
|--------|--------|------|
| `GROUP_MESSAGE_RECEIVED` | `group.message.received` | 群聊消息接收 |
| `GROUP_SPEAKER_SELECTED` | `group.speaker.selected` | 发言者选定 |
| `GROUP_NARRATION_REQUESTED` | `group.narration.requested` | 旁白请求 |
| `GROUP_NARRATION_GENERATED` | `group.narration.generated` | 旁白生成 |
| `GROUP_RELATIONSHIP_CHANGED` | `group.relationship.changed` | 群聊关系变化 |

### world - 世界状态与世界书

| 常量名 | 事件名 | 说明 |
|--------|--------|------|
| `WORLD_EVENT_TRIGGERED` | `world.event.triggered` | 世界事件触发 |
| `WORLD_BOOK_UPDATED` | `world.book.updated` | 世界书更新 |

### workflow - 工作流

| 常量名 | 事件名 | 说明 |
|--------|--------|------|
| `WORKFLOW_STARTED` | `workflow.started` | 工作流开始 |
| `WORKFLOW_FINISHED` | `workflow.finished` | 工作流完成 |
| `WORKFLOW_FAILED` | `workflow.failed` | 工作流失败 |

### review - Review Pipeline

| 常量名 | 事件名 | 说明 |
|--------|--------|------|
| `REVIEW_STARTED` | `review.started` | 审查开始 |
| `REVIEW_FINISHED` | `review.finished` | 审查完成 |
| `REVIEW_MEMORY_SCORED` | `review.memory.scored` | 记忆评分 |
| `REVIEW_RELATIONSHIP_SCORED` | `review.relationship.scored` | 关系评分 |
| `REVIEW_PLOT_SCORED` | `review.plot.scored` | 剧情评分 |

## 使用示例

### 在模块中使用标准化事件

```python
from nbot.events import (
    CHARACTER_TURN_BEFORE,
    CHARACTER_MEMORY_WRITTEN,
    PLOT_NODE_CREATED,
    GROUP_MESSAGE_RECEIVED,
)
from nbot.hooks.event_bus import get_event_bus
from nbot.hooks.models import RuntimeEvent

# 发射角色回合开始事件
event_bus = get_event_bus()
event = RuntimeEvent(
    type=CHARACTER_TURN_BEFORE,
    source="character_runtime",
    conversation_id="conv_abc",
    character_id="char_xyz",
    user_id="user_123",
)
await event_bus.emit(event)

# 发射剧情节点创建事件
plot_event = RuntimeEvent(
    type=PLOT_NODE_CREATED,
    source="plot_graph_manager",
    conversation_id="conv_abc",
    payload={"node_id": "pn_001", "title": "初次相遇"},
)
await event_bus.emit(plot_event)
```

### 在 Hook 中监听标准化事件

```python
from nbot.events import CHARACTER_MEMORY_WRITTEN, PLOT_TURNING_POINT_REACHED

# 创建 Hook 监听记忆写入事件
hook_config = {
    "event": CHARACTER_MEMORY_WRITTEN,
    "action": "notify",
    "scope": "conversation",
}

# 使用通配符监听所有剧情事件
hook_config = {
    "event": "plot.*",
    "action": "log",
    "scope": "global",
}
```

## 与 Hook 系统的兼容性

标准化事件名与 Hook 系统的 `HookEventType` 完全兼容。Hook 系统已添加全部标准化事件枚举及旧事件名别名映射：

| 标准化事件名 | Hook 旧事件名（别名） |
|-------------|---------------------|
| `character.turn.before` | `character.before_turn.started` |
| `character.turn.after` | `character.after_turn.finished` |
| `character.memory.recalled` | `character.after_memory_retrieve` |
| `character.state.changed` | `state.changed` |
| `character.relationship.changed` | `relationship.changed` |

两种写法均可在 Hook 的 `event` 字段中使用，系统会自动进行别名映射。

## 目录结构

```
nbot/events/
├── __init__.py    # 模块入口，导出所有常量
└── names.py       # 标准化事件名常量定义
```

## 最佳实践

1. **优先使用常量** - 避免硬编码事件名字符串
2. **保持命名一致** - 新增事件遵循 `domain.phase.action` 规范
3. **文档同步更新** - 新增事件时同步更新本文档
4. **向后兼容** - 旧事件名通过别名映射保持兼容
