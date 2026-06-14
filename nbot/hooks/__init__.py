"""
Hook Runtime — 统一事件驱动的对话 Hook 系统

NekoBot 3.0 核心模块，提供：
- 对话生命周期事件总线
- Hook 定义、条件匹配、动作执行
- 与 AIPipeline / CharacterRuntime 的集成
"""

from nbot.hooks.models import ConversationHook, HookExecutionLog, RuntimeEvent

__all__ = [
    "ConversationHook",
    "HookExecutionLog",
    "RuntimeEvent",
]
