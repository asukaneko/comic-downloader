"""群聊模式模块"""

from nbot.group.models import (
    GroupConfig,
    GroupConversation,
    InterCharacterRelation,
)
from nbot.group.scheduler import SpeakerScheduler
from nbot.group.narrator import NarratorCharacter
from nbot.group.manager import GroupManager, get_group_manager

__all__ = [
    "GroupConfig",
    "GroupConversation",
    "InterCharacterRelation",
    "SpeakerScheduler",
    "NarratorCharacter",
    "GroupManager",
    "get_group_manager",
]
