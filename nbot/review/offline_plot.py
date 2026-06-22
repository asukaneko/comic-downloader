"""One-shot prompt cache for real-time synchronized plot updates."""

from __future__ import annotations

import logging

from nbot.review.models import OfflinePlotUpdate

_log = logging.getLogger(__name__)

_MAX_CACHE = 200
_UPDATE_CACHE: dict[str, OfflinePlotUpdate] = {}


def _key(character_id: str, user_id: str, conversation_id: str) -> str:
    return ":".join(str(part or "") for part in (character_id, user_id, conversation_id))


def store_update(
    character_id: str,
    user_id: str,
    conversation_id: str,
    update: OfflinePlotUpdate | None,
) -> None:
    """Store the next-turn offline plot update. Empty updates clear existing cache."""
    if not character_id:
        return
    key = _key(character_id, user_id, conversation_id)
    if not update or not update.should_inject or not (update.prompt_text or update.summary):
        _UPDATE_CACHE.pop(key, None)
        return
    if len(_UPDATE_CACHE) >= _MAX_CACHE and key not in _UPDATE_CACHE:
        _UPDATE_CACHE.pop(next(iter(_UPDATE_CACHE)), None)
    _UPDATE_CACHE[key] = update
    _log.debug("[OfflinePlot] stored update for %s", key)


def consume_update(
    character_id: str,
    user_id: str,
    conversation_id: str,
) -> OfflinePlotUpdate | None:
    """Read and clear the next-turn offline plot update."""
    if not character_id:
        return None
    return _UPDATE_CACHE.pop(_key(character_id, user_id, conversation_id), None)
