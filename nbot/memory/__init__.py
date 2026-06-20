"""
nbot.memory

MemoryFS — 现有记忆系统的上层逻辑视图。

底层：PromptManager（data/memories.json）
上层：MemoryFS 负责把记忆组织成角色可读的逻辑路径

逻辑路径示例：
    characters/{char_id}/general.md
    characters/{char_id}/users/{user_id}.md
    characters/{char_id}/diary/daily.md
    characters/{char_id}/diary/weekly.md
    characters/{char_id}/plot/{conversation_id}.md
    characters/{char_id}/world/events.md
"""

from nbot.memory.models import MemoryFile
from nbot.memory.fs import MemoryFS, get_memory_fs

__all__ = ["MemoryFile", "MemoryFS", "get_memory_fs"]
