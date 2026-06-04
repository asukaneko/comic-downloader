"""
NekoBot 适配器

将 NekoBot 现有的 personality / session 系统桥接到角色运行时引擎。
提供 WebCallbacks 和 QQ 频道的角色身份解析。
"""

import logging
from typing import Any, Dict, Optional

from nbot.character.models import CharacterIdentity
from nbot.character.repository import ProfileRepository

_log = logging.getLogger(__name__)


def _get_base_dir(server) -> str:
    base_dir = getattr(server, "base_dir", None)
    if base_dir:
        return base_dir

    import os

    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )


def _resolve_web_character_id(
    server,
    session: Dict[str, Any],
    session_id: str = "",
) -> str:
    runtime_snapshot = session.get("character_runtime_snapshot")
    timeline = session.get("character_runtime_timeline")
    timeline_snapshot = timeline[-1] if isinstance(timeline, list) and timeline else {}
    runtime_candidates = [
        runtime_snapshot.get("character_id") if isinstance(runtime_snapshot, dict) else None,
        timeline_snapshot.get("character_id") if isinstance(timeline_snapshot, dict) else None,
    ]
    session_candidates = [
        session.get("character_id"),
        session.get("sender_name"),
    ]

    repo = ProfileRepository(_get_base_dir(server))
    for candidate in runtime_candidates:
        candidate = str(candidate or "").strip()
        if candidate and repo.get(candidate):
            return candidate

    for candidate in runtime_candidates:
        candidate = str(candidate or "").strip()
        if candidate:
            return candidate

    if session_id:
        try:
            from nbot.character.repository import RelationshipRepository

            relationship = RelationshipRepository(_get_base_dir(server)).get_by_target(
                f"web:{session_id}"
            )
            if relationship and relationship.character_id:
                return str(relationship.character_id)
        except Exception:
            pass

    for candidate in session_candidates:
        candidate = str(candidate or "").strip()
        if candidate and repo.get(candidate):
            return candidate

    for candidate in session_candidates:
        candidate = str(candidate or "").strip()
        if candidate:
            return candidate

    personality = getattr(server, "personality", {}) or {}
    for candidate in (personality.get("id"), personality.get("name")):
        candidate = str(candidate or "").strip()
        if candidate:
            return candidate
    return "default"


def get_web_character_context(
    server,
    session_store,
    session_id: str,
) -> Optional[CharacterIdentity]:
    """从 Web 会话中解析角色身份

    Args:
        server: NBotWebServer 实例
        session_store: Web 会话存储
        session_id: 会话 ID

    Returns:
        CharacterIdentity 或 None
    """
    session = session_store.get_session(session_id) if session_store else {}
    if not session:
        session = {}

    # 角色ID：优先从会话中获取，避免全局当前角色切换后污染旧会话
    character_id = _resolve_web_character_id(server, session, session_id=session_id)

    # 目标ID：Web 会话标识。关系状态需要按会话隔离，避免新会话继承旧会话的六维进行时。
    target_id = f"web:{session_id}"

    return CharacterIdentity(
        character_id=str(character_id),
        target_id=target_id,
        scope_id=f"web:{session_id}",
        channel="web",
    )


def get_qq_character_context(
    user_id: str,
    group_id: Optional[str] = None,
    personality_name: str = "default",
) -> CharacterIdentity:
    """从 QQ 消息中解析角色身份

    Args:
        user_id: QQ 用户 ID
        group_id: 群组 ID（私聊为 None）
        personality_name: 当前角色名称

    Returns:
        CharacterIdentity
    """
    if group_id:
        # 群聊：每个用户独立关系
        scope_id = f"qq_group:{group_id}:{user_id}"
    else:
        # 私聊
        scope_id = f"qq_private:{user_id}"

    return CharacterIdentity(
        character_id=personality_name,
        target_id=str(user_id),
        scope_id=scope_id,
        channel="qq",
    )


def get_feishu_character_context(
    user_id: str,
    chat_id: Optional[str] = None,
    open_id: Optional[str] = None,
    personality_name: str = "default",
) -> CharacterIdentity:
    """从飞书消息中解析角色身份

    Args:
        user_id: 用户 ID
        chat_id: 会话 ID（群聊或私聊）
        open_id: 用户 open_id
        personality_name: 当前角色名称

    Returns:
        CharacterIdentity
    """
    if chat_id:
        # 群聊或私聊会话
        scope_id = f"feishu_chat:{chat_id}:{user_id}"
    else:
        # 仅用户维度
        scope_id = f"feishu_user:{user_id}"

    return CharacterIdentity(
        character_id=personality_name,
        target_id=str(user_id),
        scope_id=scope_id,
        channel="feishu",
    )


def get_telegram_character_context(
    user_id: str,
    chat_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    personality_name: str = "default",
) -> CharacterIdentity:
    """从 Telegram 消息中解析角色身份

    Args:
        user_id: 用户 ID
        chat_id: 会话 ID（群组或私聊）
        thread_id: 话题 ID
        personality_name: 当前角色名称

    Returns:
        CharacterIdentity
    """
    if chat_id and thread_id:
        # 话题模式
        scope_id = f"tg_thread:{chat_id}:{thread_id}:{user_id}"
    elif chat_id:
        # 群组或私聊
        scope_id = f"tg_chat:{chat_id}:{user_id}"
    else:
        # 仅用户维度
        scope_id = f"tg_user:{user_id}"

    return CharacterIdentity(
        character_id=personality_name,
        target_id=str(user_id),
        scope_id=scope_id,
        channel="telegram",
    )


def get_character_runtime_from_server(server):
    """从 NBotWebServer 获取 CharacterRuntime 实例

    Args:
        server: NBotWebServer 实例

    Returns:
        CharacterRuntime 实例或 None
    """
    runtime = getattr(server, "character_runtime", None)

    try:
        from nbot.character.memory import PromptManagerMemoryAdapter
        from nbot.character.planner import ReactionPlanner
        from nbot.character.policies import SignalAnalyzer
        from nbot.character.repository import (
            CharacterStateRepository,
            ProfileRepository,
            RelationshipRepository,
        )
        from nbot.character.runtime import CharacterRuntime
        from nbot.character.state_machine import StateMachine

        base_dir = _get_base_dir(server)

        profile_repo = ProfileRepository(base_dir)
        personality = getattr(server, "personality", {}) or {}
        if isinstance(personality, dict) and personality:
            # 始终同步最新的 personality 到 profiles.json，确保 initial_state 是最新的
            from nbot.character.models import CharacterProfile
            profile = CharacterProfile.from_personality_dict(personality)
            if not profile.id:
                profile.id = profile.name or "default"
            profile_repo.save(profile)

        if runtime:
            # runtime 已存在，更新所有 repo 引用，确保数据同步
            runtime.profile_repo = profile_repo
            # 同时刷新 relationship_repo 和 state_repo，避免缓存旧数据
            runtime.relationship_repo = RelationshipRepository(base_dir)
            runtime.state_repo = CharacterStateRepository(base_dir)
            if not getattr(runtime, '_world_book_store', None):
                from nbot.character.storage.world_book_store import WorldBookStore
                runtime._world_book_store = WorldBookStore(base_dir)
            _log.debug("[CharacterRuntime] refreshed repos for character=%s",
                       getattr(server, "personality", {}).get("name", "unknown"))
            return runtime

        from nbot.character.storage.world_book_store import WorldBookStore

        runtime = CharacterRuntime(
            profile_repo=profile_repo,
            state_repo=CharacterStateRepository(base_dir),
            relationship_repo=RelationshipRepository(base_dir),
            memory_service=PromptManagerMemoryAdapter(),
            signal_analyzer=SignalAnalyzer(),
            planner=ReactionPlanner(),
            state_machine=StateMachine(),
            world_book_store=WorldBookStore(base_dir),
        )
        server.character_runtime = runtime
        _log.info("[CharacterRuntime] initialized lazily from Web adapter")
        return runtime
    except Exception as exc:
        _log.warning(
            "[CharacterRuntime] lazy initialization failed: %s",
            exc,
            exc_info=True,
        )
        return None
