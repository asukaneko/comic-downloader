"""
nbot.review

Review Pipeline — 每轮对话后的结构化审查层。

职责：
  - 判断是否值得写长期记忆
  - 判断关系变化及理由
  - 判断剧情节点更新
  - 生成角色体验评分
"""

from nbot.review.models import (
    MemoryItem,
    OfflinePlotUpdate,
    PlotUpdate,
    RelationshipDelta,
    ReviewInput,
    ReviewOutput,
    ReviewScore,
    WorldBookUpdate,
)
from nbot.review.pipeline import ReviewPipeline
from nbot.review.rule_review import build_offline_plot_update

__all__ = [
    "ReviewInput",
    "ReviewOutput",
    "ReviewScore",
    "MemoryItem",
    "OfflinePlotUpdate",
    "RelationshipDelta",
    "PlotUpdate",
    "WorldBookUpdate",
    "ReviewPipeline",
    "build_offline_plot_update",
]
