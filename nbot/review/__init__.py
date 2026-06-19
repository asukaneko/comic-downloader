"""
nbot.review

Review Pipeline — 每轮对话后的结构化审查层。

职责：
  - 判断是否值得写长期记忆
  - 判断关系变化及理由
  - 判断剧情节点更新
  - 生成角色体验评分
"""

from nbot.review.models import ReviewInput, ReviewOutput, ReviewScore, MemoryItem, RelationshipDelta, PlotUpdate, WorldBookUpdate
from nbot.review.pipeline import ReviewPipeline

__all__ = [
    "ReviewInput",
    "ReviewOutput",
    "ReviewScore",
    "MemoryItem",
    "RelationshipDelta",
    "PlotUpdate",
    "WorldBookUpdate",
    "ReviewPipeline",
]
