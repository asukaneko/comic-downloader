import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

import requests

from nbot.channels.qqbot import QQBotChannelAdapter
from nbot.core.ai_pipeline import (
    AIPipeline,
    PipelineCallbacks,
    PipelineContext,
    handle_tool_confirmation,
)

try:
    import websocket
except Exception:  # pragma: no cover - exercised only when dependency is missing
    websocket = None

_log = logging.getLogger(__name__)

QQBOT_API_BASE = "https://api.sgroup.qq.com"
QQBOT_SANDBOX_API_BASE = "https://sandbox.api.sgroup.qq.com"
QQBOT_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"

OP_DISPATCH = 0
OP_HEARTBEAT = 1
OP_IDENTIFY = 2
OP_HELLO = 10
OP_HEARTBEAT_ACK = 11

INTENTS_PUBLIC_MESSAGES = 1 << 30
INTENTS_PUBLIC_GROUP_MESSAGES = 1 << 25
INTENTS_PUBLIC_C2C_MESSAGES = 1 << 26
DEFAULT_INTENTS = (
    INTENTS_PUBLIC_MESSAGES
    | INTENTS_PUBLIC_GROUP_MESSAGES
    | INTENTS_PUBLIC_C2C_MESSAGES
)


def resolve_config_secret(
    config: Dict[str, Any],
    value_key: str,
    env_key: str,
    default_env: str = "",
) -> str:
    env_name = str(config.get(env_key) or "").strip()
    if env_name:
        value = os.getenv(env_name)
        if value:
            return value.strip()
    direct_value = str(config.get(value_key) or "").strip()
    if direct_value:
        return direct_value
    if default_env:
        value = os.getenv(default_env)
        if value:
            return value.strip()
    return ""


def resolve_qqbot_credentials(config: Dict[str, Any]) -> Dict[str, str]:
    return {
        "app_id": resolve_config_secret(
            config, "app_id", "app_id_env", default_env="QQBOT_APP_ID"
        ),
        "app_secret": resolve_config_secret(
            config, "app_secret", "app_secret_env", default_env="QQBOT_APP_SECRET"
        ),
        "api_base": str(config.get("api_base") or "").strip(),
        "sandbox": str(config.get("sandbox") or "").strip().lower(),
    }


def get_api_base(config: Dict[str, Any]) -> str:
    configured = str(config.get("api_base") or "").strip().rstrip("/")
    if configured:
        return configured
    if bool(config.get("sandbox")):
        return QQBOT_SANDBOX_API_BASE
    return QQBOT_API_BASE


def get_app_access_token(app_id: str, app_secret: str, api_base: str) -> Optional[str]:
    if not app_id or not app_secret:
        return None
    response = requests.post(
        QQBOT_TOKEN_URL,
        json={"appId": app_id, "clientSecret": app_secret},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    token = data.get("access_token") or data.get("accessToken")
    return str(token).strip() if token else None


def get_gateway(token: str, api_base: str) -> str:
    response = requests.get(
        f"{api_base.rstrip('/')}/gateway/bot",
        headers={"Authorization": f"QQBot {token}"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    gateway = str(data.get("url") or "").strip()
    if not gateway:
        raise ValueError("QQ Bot gateway response missing url")
    return gateway


def send_qqbot_message(
    token: str,
    api_base: str,
    parsed: Dict[str, Any],
    text: str,
) -> Dict[str, Any]:
    scene = (parsed.get("metadata") or {}).get("qqbot_scene")
    msg_id = parsed.get("message_id") or (parsed.get("metadata") or {}).get("qqbot_message_id")
    if scene == "group":
        group_id = (parsed.get("metadata") or {}).get("qqbot_group_openid")
        url = f"{api_base.rstrip('/')}/v2/groups/{group_id}/messages"
    else:
        user_id = (parsed.get("metadata") or {}).get("qqbot_user_openid") or parsed.get("user_id")
        url = f"{api_base.rstrip('/')}/v2/users/{user_id}/messages"

    payload: Dict[str, Any] = {
        "msg_type": 0,
        "content": (text or "")[:2000],
        "msg_seq": 1,
    }
    if msg_id:
        payload["msg_id"] = msg_id

    response = requests.post(
        url,
        headers={
            "Authorization": f"QQBot {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _ensure_qqbot_workspace(
    server: Any,
    session_id: str,
    parsed: Dict[str, Any],
    *,
    session_name: str = "",
) -> None:
    workspace_manager = getattr(server, "workspace_manager", None)
    if not getattr(server, "WORKSPACE_AVAILABLE", False) or not workspace_manager:
        return
    metadata = parsed.get("metadata") or {}
    session_type = (
        "qqbot_group"
        if metadata.get("qqbot_scene") == "group"
        else "qqbot_private"
    )
    if not session_name:
        session = getattr(server, "sessions", {}).get(session_id, {})
        session_name = str(session.get("name") or "")
    try:
        workspace_manager.get_or_create(session_id, session_type, session_name)
    except TypeError:
        workspace_manager.get_or_create(session_id, session_type)


def _get_or_create_qqbot_session(
    server: Any,
    session_id: str,
    parsed: Dict[str, Any],
    channel_id: str = "",
) -> str:
    """Create a visible Web session and workspace for QQBot messages."""
    if not server or not hasattr(server, "sessions"):
        return session_id
    if session_id in server.sessions:
        _ensure_qqbot_workspace(server, session_id, parsed)
        return session_id

    metadata = parsed.get("metadata") or {}
    scene = metadata.get("qqbot_scene", "")
    user_id = parsed.get("user_id", "")
    group_id = metadata.get("qqbot_group_openid", "")
    if scene == "group":
        name = f"QQBot group {group_id[:8]}"
        session_type = "qqbot_group"
    else:
        name = f"QQBot private {user_id[:8]}"
        session_type = "qqbot_private"

    now = datetime.now().isoformat()
    server.sessions[session_id] = {
        "id": session_id,
        "name": name,
        "type": session_type,
        "channel": "qqbot",
        "channel_id": channel_id,
        "qqbot_user_id": user_id,
        "qqbot_group_id": group_id,
        "qqbot_scene": scene,
        "created_at": now,
        "updated_at": now,
        "messages": [],
        "metadata": {
            "source": "qqbot",
            "user_id": user_id,
            "group_id": group_id,
            "scene": scene,
        },
    }
    try:
        server._save_data("sessions")
    except Exception:
        pass
    _ensure_qqbot_workspace(server, session_id, parsed, session_name=name)
    return session_id


class QQBotCallbacks(PipelineCallbacks):
    def __init__(
        self,
        server: Any,
        token: str,
        api_base: str,
        parsed: Dict[str, Any],
        session_id: str = "",
    ):
        self.server = server
        self.token = token
        self.api_base = api_base
        self.parsed = parsed
        self.session_id = session_id

    def get_system_prompt(self, ctx: PipelineContext) -> str:
        return str(
            getattr(self.server, "personality", {}).get("systemPrompt") or ""
        ).strip()

    def load_messages(self, ctx: PipelineContext) -> list[Dict[str, Any]]:
        session_id = self.session_id or self.parsed.get("conversation_id", "")
        session = getattr(self.server, "sessions", {}).get(session_id, {}) if self.server else {}
        messages: list[Dict[str, Any]] = []
        system_prompt = str(session.get("system_prompt") or "").strip()
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            fallback_system = self.get_system_prompt(ctx)
            if fallback_system:
                messages.append({"role": "system", "content": fallback_system})

        for item in (session.get("messages") or [])[-20:]:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": ctx.chat_request.content})
        return messages

    def get_workspace_context(self, ctx: PipelineContext) -> Dict[str, Any]:
        character_name = str(
            getattr(self.server, "personality", {}).get("name") or ""
        ).strip()
        context: Dict[str, Any] = {
            "session_id": self.session_id or self.parsed.get("conversation_id", ""),
            "session_type": (
                "qqbot_group"
                if (self.parsed.get("metadata") or {}).get("qqbot_scene") == "group"
                else "qqbot_private"
            ),
        }
        if character_name:
            context["character_name"] = character_name
        target_id = str(self.parsed.get("user_id") or "").strip()
        if target_id:
            context["target_id"] = target_id
            context["user_id"] = target_id
        return context

    def get_character_context(self, ctx: PipelineContext):
        """返回 QQ Bot 官方接口的角色身份标识"""
        from nbot.character.adapters.nekobot import get_qqbot_character_context

        personality_name = str(
            getattr(self.server, "personality", {}).get("name") or "default"
        ).strip() or "default"
        metadata = self.parsed.get("metadata") or {}
        scene = metadata.get("qqbot_scene", "")
        group_openid = metadata.get("qqbot_group_openid", "") if scene == "group" else ""
        user_id = str(self.parsed.get("user_id") or "").strip()

        return get_qqbot_character_context(
            user_id=user_id,
            group_openid=group_openid,
            personality_name=personality_name,
        )

    def get_character_runtime(self, ctx: PipelineContext):
        from nbot.character.adapters.nekobot import get_character_runtime_from_server

        return get_character_runtime_from_server(self.server)

    def send_response(self, ctx: PipelineContext, message: Dict[str, Any]) -> None:
        content = message.get("content", "")
        if content:
            send_qqbot_message(self.token, self.api_base, self.parsed, content)

    def save_assistant_message(self, ctx: PipelineContext, message: Dict[str, Any]) -> None:
        """保存 AI 回复到 server.sessions，使 Web UI 可见。"""
        if not self.session_id or not self.server:
            return
        try:
            from nbot.core.session_store import WebSessionStore

            session_store = WebSessionStore(
                self.server.sessions,
                save_callback=lambda: self.server._save_data("sessions"),
            )
            session_store.append_message(self.session_id, message)
        except Exception as e:
            _log.warning("QQBot save_assistant_message failed: %s", e)


class QQBotMessageAdapter:
    """QQBot 消息适配器 - 模拟 msg 对象供命令系统使用"""

    def __init__(
        self,
        content: str,
        parsed: Dict[str, Any],
        token: str,
        api_base: str,
        server: Any = None,
    ):
        self.content = content
        self.raw_message = content
        self.user_id = parsed.get("user_id", "")
        metadata = parsed.get("metadata") or {}
        self.message_id = parsed.get("message_id") or metadata.get("qqbot_message_id", "")
        scene = metadata.get("qqbot_scene", "")
        self.group_id = metadata.get("qqbot_group_openid", "") if scene == "group" else ""

        # 会话 / 工作区支持：复用 conversation_id 作为 session_id
        self.conversation_id = parsed.get("conversation_id", "")
        self.session_id = self.conversation_id
        self.chat_id = self.group_id or self.conversation_id
        self.server = server

        self.bot = QQBotBotMock(token, api_base, parsed)

    async def reply(self, text: str = None, **kwargs):
        if text:
            return self.bot._send_sync(text)
        return None


class QQBotBotMock:
    """QQBot Bot 模拟器 - 提供与 QQ Bot 兼容的 api 接口"""

    def __init__(self, token: str, api_base: str, parsed: Dict[str, Any]):
        self.token = token
        self.api_base = api_base
        self.parsed = parsed
        self.api = self._create_mock_api()

    def _send_sync(self, text: str) -> Dict[str, Any]:
        return send_qqbot_message(self.token, self.api_base, self.parsed, text)

    def _create_mock_api(self):
        mock = self

        class MockAPI:
            async def post_group_msg(self, group_id, text=None, **kwargs):
                return mock._send_sync(text or "")

            async def post_private_msg(self, user_id, text=None, **kwargs):
                return mock._send_sync(text or "")

            async def post_group_file(self, group_id, file=None, **kwargs):
                _log.warning("QQBot mock: post_group_file not supported")
                return True

            async def upload_private_file(self, user_id, file=None, **kwargs):
                _log.warning("QQBot mock: upload_private_file not supported")
                return True

        return MockAPI()


def _handle_qqbot_command(
    token: str,
    api_base: str,
    parsed: Dict[str, Any],
    handler: Any,
    content: str,
    server: Any = None,
) -> None:
    """执行 QQBot 命令"""
    metadata = parsed.get("metadata") or {}
    scene = metadata.get("qqbot_scene", "")
    is_group = scene == "group"

    adapter = QQBotMessageAdapter(content, parsed, token, api_base, server=server)

    def run_command():
        original_bot = None
        original_ai_bot = None
        try:
            import nbot.commands as cmd_module
            import nbot.ai_commands as ai_module

            original_bot = getattr(cmd_module, "bot", None)
            original_ai_bot = getattr(ai_module, "_bot_instance", None)
            cmd_module.bot = adapter.bot
            ai_module._bot_instance = adapter.bot

            asyncio.run(handler(adapter, is_group=is_group))
        except Exception as e:
            _log.error("QQBot command execution failed: %s", e, exc_info=True)
            try:
                send_qqbot_message(token, api_base, parsed, f"命令执行失败: {e}")
            except Exception:
                pass
        finally:
            if original_bot is not None:
                import nbot.commands as cmd_module
                cmd_module.bot = original_bot
            if original_ai_bot is not None:
                import nbot.ai_commands as ai_module
                ai_module._bot_instance = original_ai_bot

    threading.Thread(target=run_command, name="qqbot-cmd", daemon=True).start()


def answer_qqbot_event(
    server: Any,
    channel: Dict[str, Any],
    raw_event: Dict[str, Any],
) -> Dict[str, Any]:
    config = channel.get("config") or {}
    credentials = resolve_qqbot_credentials(config)
    app_id = credentials["app_id"]
    app_secret = credentials["app_secret"]
    if not app_id or not app_secret:
        raise ValueError("未配置 QQ Bot AppID 或 AppSecret")

    adapter = QQBotChannelAdapter(bot_appid=app_id)
    parsed = adapter.parse_event(raw_event or {})
    if not parsed:
        return {"ok": True, "ignored": True}

    api_base = get_api_base(config)
    token = get_app_access_token(app_id, app_secret, api_base)
    if not token:
        raise ValueError("获取 QQ Bot app_access_token 失败")

    _qqbot_session_type = (
        "qqbot_group"
        if (parsed.get("metadata") or {}).get("qqbot_scene") == "group"
        else "qqbot_private"
    )
    content = handle_tool_confirmation(
        parsed["content"],
        parsed["conversation_id"],
        log_prefix="QQBot",
        session_type=_qqbot_session_type,
    )
    session_id = parsed["conversation_id"]
    channel_id = channel.get("id", "")
    _get_or_create_qqbot_session(server, session_id, parsed, channel_id)

    if content and content.startswith("/"):
        try:
            from nbot.commands import match_command

            handler, cmd = match_command(content)
            if handler:
                _log.info("QQBot matched command: %s", cmd)
                _handle_qqbot_command(token, api_base, parsed, handler, content, server=server)
                return {"ok": True, "command": cmd}
        except Exception as e:
            _log.warning("QQBot command matching failed: %s", e)

    # 保存用户消息到会话
    try:
        session_available = bool(server and hasattr(server, "sessions"))
        if not session_available:
            raise RuntimeError("QQBot session store unavailable")
        from nbot.core.session_store import WebSessionStore

        session_store = WebSessionStore(
            server.sessions,
            save_callback=lambda: server._save_data("sessions"),
        )
        user_message = adapter.build_message(
            role="user",
            content=content,
            sender=parsed.get("sender", "qqbot_user"),
            conversation_id=session_id,
            source="qqbot",
            metadata={
                "qqbot_message_id": parsed.get("message_id", ""),
                "qqbot_scene": (parsed.get("metadata") or {}).get("qqbot_scene", ""),
            },
        )
        session_store.append_message(session_id, user_message)
    except Exception as e:
        _log.warning("QQBot save user message failed: %s", e)

    chat_request = adapter.build_chat_request(
        conversation_id=session_id,
        user_id=parsed.get("user_id", ""),
        content=content,
        sender=parsed.get("sender", "qqbot_user"),
        attachments=parsed.get("attachments", []),
        metadata=parsed.get("metadata", {}),
    )

    ctx = PipelineContext(chat_request=chat_request, adapter=adapter)
    ctx.metadata["channel_type"] = "qqbot"
    ctx.metadata["source"] = "qqbot"
    try:
        from nbot.services.ai import refresh_runtime_ai_config

        runtime_ai = refresh_runtime_ai_config()
        ctx.metadata["input_price"] = runtime_ai.get("input_price")
        ctx.metadata["output_price"] = runtime_ai.get("output_price")
    except Exception:
        pass

    hook_runtime = None
    try:
        from nbot.hooks.manager import get_hook_manager

        hook_runtime = get_hook_manager()
    except Exception:
        pass

    result = AIPipeline().process(
        ctx,
        QQBotCallbacks(server, token, api_base, parsed, session_id=session_id),
        hook_runtime=hook_runtime,
    )
    return {"ok": True, "result": result.final_content}


class QQBotWebSocketService:
    def __init__(self):
        self._clients: Dict[str, Any] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._server: Optional[Any] = None
        self._lock = threading.Lock()

    def set_server(self, server: Any) -> None:
        self._server = server

    def is_running(self, channel_id: str) -> bool:
        return channel_id in self._clients

    def list_running_clients(self) -> list[str]:
        return sorted(self._clients.keys())

    def start_client(self, channel_id: str, channel: Dict[str, Any]) -> bool:
        if websocket is None:
            raise RuntimeError("缺少 websocket-client 依赖，请先安装 requirements.txt")
        if not self._server:
            raise RuntimeError("QQ Bot WebSocket service server is not set")

        with self._lock:
            if channel_id in self._clients:
                return True

        config = channel.get("config") or {}
        credentials = resolve_qqbot_credentials(config)
        app_id = credentials["app_id"]
        app_secret = credentials["app_secret"]
        if not app_id or not app_secret:
            return False

        api_base = get_api_base(config)
        token = get_app_access_token(app_id, app_secret, api_base)
        if not token:
            return False
        gateway = get_gateway(token, api_base)
        intents = int(config.get("intents") or DEFAULT_INTENTS)

        state = {"seq": None, "heartbeat_interval": 45000}

        def on_open(ws):
            _log.info("QQBot websocket opened for channel %s", channel_id)

        def on_message(ws, message):
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                return
            op = payload.get("op")
            if payload.get("s") is not None:
                state["seq"] = payload.get("s")
            if op == OP_HELLO:
                heartbeat_interval = (
                    (payload.get("d") or {}).get("heartbeat_interval")
                    or state["heartbeat_interval"]
                )
                state["heartbeat_interval"] = int(heartbeat_interval)
                self._start_heartbeat(channel_id, ws, state)
                ws.send(
                    json.dumps(
                        {
                            "op": OP_IDENTIFY,
                            "d": {
                                "token": f"QQBot {token}",
                                "intents": intents,
                                "shard": [0, 1],
                                "properties": {
                                    "os": os.name,
                                    "browser": "nekobot",
                                    "device": "nekobot",
                                },
                            },
                        },
                        ensure_ascii=False,
                    )
                )
                return
            if op == OP_DISPATCH:
                self._handle_dispatch(channel, payload)
            elif op == OP_HEARTBEAT_ACK:
                _log.debug("QQBot heartbeat ack for channel %s", channel_id)

        def on_error(ws, error):
            _log.warning("QQBot websocket error for channel %s: %s", channel_id, error)

        def on_close(ws, close_status_code, close_msg):
            _log.info(
                "QQBot websocket closed for channel %s: %s %s",
                channel_id,
                close_status_code,
                close_msg,
            )
            with self._lock:
                self._clients.pop(channel_id, None)
                self._threads.pop(channel_id, None)

        ws = websocket.WebSocketApp(
            gateway,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        thread = threading.Thread(
            target=lambda: ws.run_forever(ping_interval=0),
            name=f"qqbot-ws-{channel_id}",
            daemon=True,
        )
        with self._lock:
            self._clients[channel_id] = ws
            self._threads[channel_id] = thread
        thread.start()
        return True

    def stop_client(self, channel_id: str) -> bool:
        with self._lock:
            ws = self._clients.pop(channel_id, None)
            self._threads.pop(channel_id, None)
        if not ws:
            return False
        ws.close()
        return True

    def _start_heartbeat(self, channel_id: str, ws: Any, state: Dict[str, Any]) -> None:
        def run():
            while self.is_running(channel_id):
                time.sleep(max(float(state["heartbeat_interval"]) / 1000.0, 1.0))
                try:
                    ws.send(json.dumps({"op": OP_HEARTBEAT, "d": state["seq"]}))
                except Exception:
                    break

        threading.Thread(target=run, name=f"qqbot-hb-{channel_id}", daemon=True).start()

    def _handle_dispatch(self, channel: Dict[str, Any], payload: Dict[str, Any]) -> None:
        if not self._server:
            return

        def process():
            try:
                answer_qqbot_event(self._server, channel, payload)
            except Exception:
                _log.exception("Failed to answer QQBot event")

        threading.Thread(target=process, daemon=True).start()


qqbot_ws_service = QQBotWebSocketService()
