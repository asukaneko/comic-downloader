# 事件名常量

`nbot.events.names` 模块定义了所有标准化事件名常量，采用 `domain.phase.action` 三层命名结构。所有模块发射事件时应优先使用这里的常量。

## 常量列表

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

### group - 群聊

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

## 使用方式

```python
from nbot.events import names as _E

# 在 CharacterRuntime 中
self._emit_hook(_E.CHARACTER_TURN_BEFORE, identity, payload)

# 在 PlotGraphManager 中
self._emit(_E.PLOT_NODE_CREATED, {"node_id": node.id, "title": node.title})

# 在 ReviewPipeline 中
self._emit(_E.REVIEW_STARTED, {"conversation_id": inp.conversation_id})
```

## 事件别名映射

Hook 系统支持旧事件名到新标准化事件名的自动映射：

| 标准化事件名 | Hook 旧事件名（别名） |
|-------------|---------------------|
| `character.turn.before` | `character.before_turn.started` |
| `character.turn.after` | `character.after_turn.finished` |
| `character.memory.recalled` | `character.after_memory_retrieve` |
| `character.state.changed` | `state.changed` |
| `character.relationship.changed` | `relationship.changed` |

两种写法均可在 Hook 的 `event` 字段中使用，系统会自动进行别名映射。
