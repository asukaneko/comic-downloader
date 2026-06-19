"""
标准化事件名常量

命名规范：domain.phase.action
所有模块发射事件时应优先使用这里的常量，避免事件名散落在业务代码中。
"""

# ---------------------------------------------------------------------------
# character domain — 角色对话生命周期
# ---------------------------------------------------------------------------

CHARACTER_TURN_BEFORE = "character.turn.before"
CHARACTER_TURN_AFTER = "character.turn.after"

CHARACTER_MEMORY_RECALLED = "character.memory.recalled"
CHARACTER_MEMORY_REVIEWED = "character.memory.reviewed"
CHARACTER_MEMORY_WRITTEN = "character.memory.written"

CHARACTER_RELATIONSHIP_CHANGED = "character.relationship.changed"
CHARACTER_STATE_CHANGED = "character.state.changed"

CHARACTER_MODEL_GENERATED = "character.model.generated"

# ---------------------------------------------------------------------------
# plot domain — 剧情分支系统
# ---------------------------------------------------------------------------

PLOT_NODE_CREATED = "plot.node.created"
PLOT_CHOICE_GENERATED = "plot.choice.generated"
PLOT_CHOICE_SELECTED = "plot.choice.selected"
PLOT_EDGE_CREATED = "plot.edge.created"
PLOT_ROLLBACK_DONE = "plot.rollback.done"
PLOT_TURNING_POINT_REACHED = "plot.turning_point.reached"

# ---------------------------------------------------------------------------
# group domain — 群聊 / Agent Society
# ---------------------------------------------------------------------------

GROUP_MESSAGE_RECEIVED = "group.message.received"
GROUP_SPEAKER_SELECTED = "group.speaker.selected"
GROUP_NARRATION_REQUESTED = "group.narration.requested"
GROUP_NARRATION_GENERATED = "group.narration.generated"
GROUP_RELATIONSHIP_CHANGED = "group.relationship.changed"

# ---------------------------------------------------------------------------
# world domain — 世界状态与世界书
# ---------------------------------------------------------------------------

WORLD_EVENT_TRIGGERED = "world.event.triggered"
WORLD_BOOK_UPDATED = "world.book.updated"

# ---------------------------------------------------------------------------
# workflow domain — 工作流
# ---------------------------------------------------------------------------

WORKFLOW_STARTED = "workflow.started"
WORKFLOW_FINISHED = "workflow.finished"
WORKFLOW_FAILED = "workflow.failed"

# ---------------------------------------------------------------------------
# review domain — Review Pipeline
# ---------------------------------------------------------------------------

REVIEW_STARTED = "review.started"
REVIEW_FINISHED = "review.finished"
REVIEW_MEMORY_SCORED = "review.memory.scored"
REVIEW_RELATIONSHIP_SCORED = "review.relationship.scored"
REVIEW_PLOT_SCORED = "review.plot.scored"
