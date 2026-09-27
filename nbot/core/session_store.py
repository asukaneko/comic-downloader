import json
import logging
import uuid
from typing import Any, Callable, Dict, List, Optional

_log = logging.getLogger(__name__)


def build_qq_session_id(
    user_id: Optional[str] = None,
    group_id: Optional[str] = None,
    group_user_id: Optional[str] = None,
) -> str:
    if user_id:
        return f"qq_private_{user_id}"
    if group_id and group_user_id:
        return f"qq_group_{group_id}_{group_user_id}"
    if group_id:
        return f"qq_group_{group_id}"
    return ""


def build_qq_history_key(
    user_id: Optional[str] = None,
    group_id: Optional[str] = None,
    group_user_id: Optional[str] = None,
) -> str:
    if user_id:
        return str(user_id)
    if group_id and group_user_id:
        return f"{group_id}_{group_user_id}"
    if group_id:
        return str(group_id)
    return ""


def build_cli_session_id() -> str:
    return f"cli_{uuid.uuid4().hex}"


def build_chat_message(
    role: str,
    content: str,
    *,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    message = {"role": role, "content": content}
    if extra:
        message.update(extra)
    return message


def is_message_deleted(message: Any) -> bool:
    """判断消息是否被软删除（保留记录，但所有展示与模型上下文均忽略）。"""
    return bool(isinstance(message, dict) and message.get("deleted"))


def visible_messages(messages: Any) -> List[Dict[str, Any]]:
    """过滤软删除消息，返回可展示/可送入模型的消息列表。"""
    if not isinstance(messages, list):
        return []
    return [msg for msg in messages if isinstance(msg, dict) and not is_message_deleted(msg)]


def deleted_message_ids(messages: Any) -> set:
    """收集消息列表中的软删除消息 id，用于阻止异步回写复活。"""
    if not isinstance(messages, list):
        return set()
    return {
        str(msg.get("id"))
        for msg in messages
        if isinstance(msg, dict) and is_message_deleted(msg) and msg.get("id")
    }


class QQSessionStore:
    def __init__(
        self,
        *,
        user_messages: Dict[str, List[Dict[str, Any]]],
        group_messages: Dict[str, List[Dict[str, Any]]],
        prompt_loader: Callable[..., str],
        max_history: int,
        save_callback: Optional[Callable[[], None]] = None,
    ):
        self.user_messages = user_messages
        self.group_messages = group_messages
        self.prompt_loader = prompt_loader
        self.max_history = max_history
        self.save_callback = save_callback

    def get_history_key(
        self,
        *,
        user_id: Optional[str] = None,
        group_id: Optional[str] = None,
        group_user_id: Optional[str] = None,
    ) -> str:
        return build_qq_history_key(user_id, group_id, group_user_id)

    def get_session_id(
        self,
        *,
        user_id: Optional[str] = None,
        group_id: Optional[str] = None,
        group_user_id: Optional[str] = None,
    ) -> str:
        return build_qq_session_id(user_id, group_id, group_user_id)

    def ensure_history(
        self,
        *,
        user_id: Optional[str] = None,
        group_id: Optional[str] = None,
        group_user_id: Optional[str] = None,
        include_memories: bool = True,
    ) -> List[Dict[str, Any]]:
        if user_id:
            user_id = str(user_id)
            prompt = self.prompt_loader(user_id=user_id, include_memories=include_memories)
            return self._ensure_bucket(self.user_messages, user_id, prompt)

        if group_id:
            group_id = str(group_id)
            prompt = self.prompt_loader(group_id=group_id, include_memories=include_memories)
            history_key = build_qq_history_key(
                group_id=group_id, group_user_id=group_user_id
            )
            return self._ensure_bucket(self.group_messages, history_key, prompt)

        return []

    def append_message(
        self,
        *,
        role: str,
        content: str,
        user_id: Optional[str] = None,
        group_id: Optional[str] = None,
        group_user_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        # 过滤检查
        filtered_content = content
        try:
            from nbot.message_filter import message_filter

            if user_id:
                filter_session_id = f"qq:private:{user_id}"
            elif group_id:
                filter_session_id = f"qq:group:{group_id}"
            else:
                filter_session_id = ""

            message_dict = {"role": role, "content": content}
            result = message_filter.filter_message(
                message_dict,
                channel="qq",
                session_id=filter_session_id,
            )
            if result.get("blocked"):
                messages = self.ensure_history(
                    user_id=user_id, group_id=group_id, group_user_id=group_user_id
                )
                return messages
            if result.get("filtered"):
                filtered_content = result["message"].get("content", content)
        except Exception as e:
            _log.debug("[QQSessionStore] 过滤检查异常: %s", e)

        messages = self.ensure_history(
            user_id=user_id, group_id=group_id, group_user_id=group_user_id
        )
        messages.append(build_chat_message(role, filtered_content, extra=extra))
        self._trim(messages)
        self.save()
        return messages

    def save(self) -> None:
        if self.save_callback:
            self.save_callback()

    def _ensure_bucket(
        self,
        store: Dict[str, List[Dict[str, Any]]],
        key: str,
        prompt: str,
    ) -> List[Dict[str, Any]]:
        if key not in store:
            store[key] = [build_chat_message("system", prompt)]
            return store[key]

        messages = store[key]
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = prompt
        else:
            messages.insert(0, build_chat_message("system", prompt))

        return messages

    def _trim(self, messages: List[Dict[str, Any]]) -> None:
        # 不再按条数裁剪，由 prepare_chat_context 按 token 预算裁剪
        pass


class WebSessionStore:
    def __init__(
        self,
        sessions: Dict[str, Dict[str, Any]],
        save_callback: Optional[Callable[[], None]] = None,
    ):
        self.sessions = sessions
        self.save_callback = save_callback

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.sessions.get(session_id)

    def iter_sessions(self):
        return self.sessions.items()

    def find_session_id(self, predicate: Callable[[str, Dict[str, Any]], bool]) -> Optional[str]:
        for session_id, session in self.sessions.items():
            if predicate(session_id, session):
                return session_id
        return None

    def set_session(self, session_id: str, session: Dict[str, Any]) -> Dict[str, Any]:
        self._filter_session_messages(session_id, session)
        self.sessions[session_id] = session
        if self.save_callback:
            self.save_callback()
        return session

    def delete_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self.sessions.pop(session_id, None)
        if session is not None and self.save_callback:
            self.save_callback()
        return session

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        session = self.get_session(session_id)
        if not session:
            return []
        session.setdefault("messages", [])
        return session["messages"]

    def append_message(self, session_id: str, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        messages = self.get_messages(session_id)
        session = self.get_session(session_id) or {}
        if self._filter_message(session_id, message, session) is None:
            return messages
        # 幂等：若同 id 消息已存在（如流式消息在剥离 [send_image:] 标签后被再次持久化），
        # 更新原条目而非追加，避免出现两个内容相同的气泡。
        msg_id = message.get("id")
        if msg_id:
            for idx, existing in enumerate(messages):
                if existing.get("id") == msg_id:
                    if is_message_deleted(existing):
                        # 已软删除的消息不允许被异步回写复活
                        return messages
                    messages[idx] = message
                    if self.save_callback:
                        self.save_callback()
                    return messages
        messages.append(message)
        if self.save_callback:
            self.save_callback()
        return messages

    def replace_messages(
        self, session_id: str, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        session = self.get_session(session_id)
        if not session:
            return []
        vanished_ids = deleted_message_ids(session.get("messages"))
        if vanished_ids:
            # 传入列表若来自软删除之前的快照，同 id 消息不得复活
            messages = [
                msg
                for msg in messages
                if not (
                    isinstance(msg, dict)
                    and str(msg.get("id") or "") in vanished_ids
                    and not is_message_deleted(msg)
                )
            ]
        session["messages"] = self._filter_messages(session_id, messages, session)
        if self.save_callback:
            self.save_callback()
        return session["messages"]

    def _filter_session_messages(self, session_id: str, session: Dict[str, Any]) -> None:
        if isinstance(session.get("messages"), list):
            session["messages"] = self._filter_messages(
                session_id,
                session["messages"],
                session,
            )

    def _filter_messages(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        session: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        filtered_messages = []
        for message in messages:
            filtered_message = self._filter_message(session_id, message, session)
            if filtered_message is not None:
                filtered_messages.append(filtered_message)
        return filtered_messages

    def _filter_message(
        self,
        session_id: str,
        message: Dict[str, Any],
        session: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            from nbot.message_filter import message_filter

            channel, filter_session_id = self._filter_target(session_id, session)
            result = message_filter.filter_message(
                message,
                channel=channel,
                session_id=filter_session_id,
            )
            if result.get("blocked"):
                return None
        except Exception:
            pass
        return message

    def _filter_target(
        self,
        session_id: str,
        session: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, str]:
        session = session or self.get_session(session_id) or {}
        session_type = str(session.get("type") or "")
        qq_id = str(session.get("qq_id") or "").strip()

        if session_type == "qq_group" and qq_id:
            return "qq", f"qq:group:{qq_id}"
        if session_type == "qq_private" and qq_id:
            return "qq", f"qq:private:{qq_id}"
        if session_id.startswith("qq_group_"):
            group_id = session_id[len("qq_group_"):].split("_", 1)[0]
            return "qq", f"qq:group:{group_id}"
        if session_id.startswith("qq_private_"):
            user_id = session_id[len("qq_private_"):].split("_", 1)[0]
            return "qq", f"qq:private:{user_id}"

        return "web", f"web:{session_id}"


def dump_json(filepath: str, data: Any) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
