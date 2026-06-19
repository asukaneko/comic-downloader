"""
nbot.events

标准化事件名常量包。

用法：
    from nbot.events import names as E
    bus.emit(RuntimeEvent(type=E.CHARACTER_TURN_BEFORE, ...))

或直接导入字符串常量：
    from nbot.events.names import CHARACTER_TURN_BEFORE
"""

from nbot.events import names

__all__ = ["names"]
