"""QQBotBackend —— 包装 QQ Bot 官方服务实现 BotBackend

阶段 1: 仅实现 BotBackend 核心(start / run_forever / stop / send_*_text / supports)
阶段 2/3: 暂不补全其他 Protocol(QQBot 官方能力限制)

rev. 2 关键修正:
- run_forever() 是同步方法,不外层包 asyncio.run()
- WebSocket 线程回调使用 asyncio.run_coroutine_threadsafe 跨线程调度,
  避免 RuntimeError: no running event loop
- start() 中通过 asyncio.get_running_loop() 捕获主 loop 引用
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

from nbot.commands_backend import (
    Capability,
    IncomingMessage,
    Scene,
)

_log = logging.getLogger(__name__)

try:
    import websocket  # websocket-client
except ImportError:
    websocket = None  # type: ignore


class QQBotBackend:
    """包装 QQ Bot 官方 OpenAPI v2 服务

    协议: WebSocket 长连接(OpenAPI v2)
    鉴权: app_id + app_secret → access_token
    事件: OP_HELLO / OP_HEARTBEAT / OP_IDENTIFY / OP_DISPATCH
    """

    name = "qqbot"
    is_running = False

    def __init__(self, app_id: str, app_secret: str,
                 sandbox: bool = False, api_base: str = ""):
        self._creds = {
            "app_id": app_id,
            "app_secret": app_secret,
            "sandbox": sandbox,
            "api_base": api_base,
        }
        self._ws_app: Any | None = None
        self._ws_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._dispatch_callback = None
        self._token: str | None = None
        self._api_base = api_base or (
            "https://sandbox.api.sgroup.qq.com" if sandbox
            else "https://api.sgroup.qq.com"
        )
        # rev. 2: 在 start() 中获取主 asyncio loop,供 run_coroutine_threadsafe 使用
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_dispatcher(self, callback):
        self._dispatch_callback = callback

    # -------------------- BotBackend 核心 --------------------

    async def start(self) -> None:
        """异步初始化:获取 token + 启动 WebSocket 线程 + 保存主 loop

        rev. 2: 在异步上下文中获取主 event loop 引用,供跨线程调度使用
        """
        from nbot.services.qqbot_service import (
            get_app_access_token,
            get_gateway,
        )

        # rev. 2 关键:在 async 上下文中捕获主 loop
        self._loop = asyncio.get_running_loop()

        if websocket is None:
            _log.error(
                "QQBotBackend: 缺少 websocket-client 依赖,"
                "请先安装 requirements.txt"
            )
            return

        self._token = get_app_access_token(
            self._creds["app_id"],
            self._creds["app_secret"],
            self._api_base,
        )
        if not self._token:
            _log.error("QQBotBackend: 获取 access_token 失败")
            return

        gateway_url = get_gateway(self._token, self._api_base)
        self._stop_event.clear()

        # 在独立线程中跑 WebSocketApp
        self._ws_thread = threading.Thread(
            target=self._ws_run_loop,
            args=(gateway_url,),
            name="qqbot-ws",
            daemon=True,
        )
        self._ws_thread.start()
        self.is_running = True
        _log.info(
            "QQBotBackend started (sandbox=%s, api_base=%s)",
            self._creds["sandbox"],
            self._api_base,
        )

    def _ws_run_loop(self, gateway_url: str) -> None:
        """独立线程:运行 WebSocketApp.run_forever()"""
        try:
            self._ws_app = websocket.WebSocketApp(
                gateway_url,
                on_open=self._on_ws_open,
                on_message=self._on_ws_message,
                on_error=self._on_ws_error,
                on_close=self._on_ws_close,
            )
            self._ws_app.run_forever()
        except Exception as e:
            _log.exception("QQBot websocket loop error: %s", e)

    def _on_ws_open(self, ws) -> None:
        _log.info("QQBot websocket opened")

    def _on_ws_message(self, ws, message: str) -> None:
        """WebSocket 收到消息 —— rev. 2 关键:跨线程调度到主 event loop"""
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return
        op = payload.get("op")
        if op == 10:  # OP_HELLO
            self._on_hello(ws, payload)
        elif op == 0:  # OP_DISPATCH
            self._on_dispatch_safe(payload)
        # 忽略 OP_HEARTHEAT_ACK 等

    def _on_hello(self, ws, payload: dict) -> None:
        """OP_HELLO:启动心跳 + 发送 OP_IDENTIFY"""
        import os
        heartbeat_interval = (
            (payload.get("d") or {}).get("heartbeat_interval") or 45000
        )
        # 启动心跳线程
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(ws, int(heartbeat_interval) / 1000.0),
            name="qqbot-heartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()
        # 发送 IDENTIFY
        ws.send(json.dumps({
            "op": 2,  # OP_IDENTIFY
            "d": {
                "token": f"QQBot {self._token}",
                "intents": (1 << 30) | (1 << 25) | (1 << 26),
                "shard": [0, 1],
                "properties": {
                    "os": os.name,
                    "browser": "nekobot",
                    "device": "nekobot",
                },
            },
        }, ensure_ascii=False))

    def _heartbeat_loop(self, ws, interval: float) -> None:
        """心跳线程"""
        while not self._stop_event.is_set():
            try:
                ws.send(json.dumps({"op": 1, "d": None}))
            except Exception:
                break
            self._stop_event.wait(interval)

    def _on_ws_error(self, ws, error) -> None:
        _log.warning("QQBot websocket error: %s", error)

    def _on_ws_close(self, ws, close_status_code, close_msg) -> None:
        _log.info("QQBot websocket closed: %s %s", close_status_code, close_msg)

    def run_forever(self) -> None:
        """同步阻塞入口 —— 等待 WebSocket 线程结束

        rev. 2: 同步方法,直接阻塞,不外层包 asyncio.run()
        """
        if self._ws_thread is not None:
            self._ws_thread.join()
        else:
            _log.warning(
                "QQBotBackend.run_forever called but ws_thread is None"
            )

    async def stop(self) -> None:
        """异步停止"""
        self.is_running = False
        self._stop_event.set()
        if self._ws_app is not None:
            try:
                self._ws_app.close()
            except Exception:
                pass

    async def send_private_text(self, user_id: str, text: str) -> bool:
        """QQBot 私聊消息发送 (C2C)"""
        if not self._token:
            _log.warning("QQBot send_private_text: token not initialized")
            return False
        from nbot.services.qqbot_service import send_qqbot_message
        try:
            payload = {
                "metadata": {
                    "qqbot_scene": "private",
                    "qqbot_user_openid": user_id,
                },
                "user_id": user_id,
                "message_id": "",
            }
            send_qqbot_message(
                self._token, self._api_base, payload, text
            )
            return True
        except Exception as e:
            _log.exception("qqbot send_private_text error: %s", e)
            return False

    async def send_group_text(self, group_id: str, text: str) -> bool:
        """QQBot 群消息发送 (Group)"""
        if not self._token:
            _log.warning("QQBot send_group_text: token not initialized")
            return False
        from nbot.services.qqbot_service import send_qqbot_message
        try:
            payload = {
                "metadata": {
                    "qqbot_scene": "group",
                    "qqbot_group_openid": group_id,
                },
                "message_id": "",
            }
            send_qqbot_message(
                self._token, self._api_base, payload, text
            )
            return True
        except Exception as e:
            _log.exception("qqbot send_group_text error: %s", e)
            return False

    def supports(self, capability: str) -> bool:
        """rev. 2: QQBot 第一版只支持核心文本能力"""
        return capability in (Capability.GROUP_TEXT, Capability.PRIVATE_TEXT)

    # -------------------- 事件转换 --------------------

    def _on_dispatch_safe(self, payload: dict) -> None:
        """WebSocket 线程回调 —— rev. 2 关键修复

        rev. 2: 不能直接 asyncio.create_task()(该线程可能没有运行中的 event loop)
        必须用 asyncio.run_coroutine_threadsafe 把协程调度到主 event loop
        """
        if self._loop is None or self._dispatch_callback is None:
            _log.debug("qqbot dispatch skipped: loop or callback not ready")
            return
        try:
            incoming = self._parse_to_incoming(payload)
            if incoming is None:
                return
            future = asyncio.run_coroutine_threadsafe(
                self._dispatch_callback(incoming),
                self._loop,
            )

            def _on_done(fut):
                try:
                    fut.result()
                except Exception as e:
                    _log.exception("qqbot dispatch callback error: %s", e)

            future.add_done_callback(_on_done)
        except Exception as e:
            _log.exception("qqbot _on_dispatch_safe error: %s", e)

    def _parse_to_incoming(self, payload: dict) -> IncomingMessage | None:
        """OpenAPI v2 dispatch event → IncomingMessage

        payload 格式: {t, d, s, op=0}
        """
        try:
            from nbot.channels.qqbot import QQBotChannelAdapter
            adapter = QQBotChannelAdapter(bot_appid=self._creds["app_id"])
            # QQBotChannelAdapter.parse_event 接受 {t, d, ...} 或 {event_type, event, ...}
            raw_event = payload
            parsed = adapter.parse_event(raw_event)
            if parsed is None:
                return None
            metadata = parsed.get("metadata", {}) or {}
            scene_str = metadata.get("qqbot_scene", "private")
            scene = Scene.GROUP if scene_str == "group" else Scene.PRIVATE
            return IncomingMessage(
                scene=scene,
                user_id=parsed.get("user_id", ""),
                group_id=metadata.get("qqbot_group_openid", ""),
                text=parsed.get("content", ""),
                raw_message=parsed.get("content", ""),
                sender_name=parsed.get("sender", ""),
                message_id=parsed.get("message_id", ""),
                is_mentioned=bool(metadata.get("is_mentioned", False)),
                backend_name="qqbot",
                metadata=metadata,
            )
        except Exception as e:
            _log.exception("qqbot _parse_to_incoming error: %s", e)
            return None
