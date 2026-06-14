"""
Plot System — 故事分支图管理模块

NekoBot 3.0 核心模块，提供：
- 故事节点（PlotNode）、选择（PlotChoice）、边（PlotEdge）数据模型
- AI 驱动的分支选项生成
- 故事图谱的持久化存储与 Mermaid 可视化
"""

from nbot.plot.models import PlotChoice, PlotEdge, PlotNode
from nbot.plot.graph_manager import PlotGraphManager, get_plot_graph_manager
from nbot.plot.choice_generator import PlotChoiceGenerator

__all__ = [
    "PlotNode",
    "PlotChoice",
    "PlotEdge",
    "PlotGraphManager",
    "get_plot_graph_manager",
    "PlotChoiceGenerator",
]
