"""NcatbotBackend —— 包装 ncatbot BotClient 实现 BotBackend

阶段 1: 仅实现 BotBackend 核心(start / run_forever / stop / send_*_text / supports)
阶段 2: 补全 NcatbotAdminBackend + RawApiBackend
阶段 3: 补全 MediaBackend

rev. 2 关键修正:
- run_forever() 是同步方法,不外层包 asyncio.run()
- 保留 ncatbot BotAPI / GroupMessage / PrivateMessage 的 monkey-patch(消息持久化)
"""
from __future__ import annotations

import logging

from nbot.commands_backend import (
    IncomingMessage,
    Scene,
)

_log = logging.getLogger(__name__)


class NcatbotBackend:
    """包装 ncatbot BotClient"""

    name = "ncatbot"
    is_running = False

    def __init__(self):
        # 延迟导入:ncatbot 模块只在 ncatbot 模式下需要
        from ncatbot.core import BotClient
        self.bot = BotClient()
        self._dispatch_callback = None

    def set_dispatcher(self, callback):
        """注入事件分发函数 —— 由 bot.py 启动时调用"""
        self._dispatch_callback = callback

    # -------------------- BotBackend 核心 --------------------

    async def start(self) -> None:
        """异步初始化:注册 ncatbot event handler"""
        # 延迟导入:避免循环

        self.bot.add_group_event_handler(self._wrap_group)
        self.bot.add_private_event_handler(self._wrap_private)
        self.is_running = True
        _log.info("NcatbotBackend started")

    def run_forever(self) -> None:
        """同步阻塞入口 —— ncatbot BotClient.run() 内部管理事件循环

        rev. 2: 同步方法,直接阻塞,不外层包 asyncio.run()
        """
        self.bot.run(enable_webui_interaction=False)

    async def stop(self) -> None:
        """异步停止"""
        self.is_running = False

    async def send_private_text(self, user_id: str, text: str) -> bool:
        return await self.bot.api.post_private_msg(user_id=user_id, text=text)

    async def send_group_text(self, group_id: str, text: str) -> bool:
        return await self.bot.api.post_group_msg(group_id=group_id, text=text)

    def supports(self, capability: str) -> bool:
        # ncatbot 实现所有能力
        return True

    # -------------------- 事件转换 --------------------

    async def _wrap_group(self, msg):
        """ncatbot group event handler 包装 → IncomingMessage → dispatcher"""
        if not self._dispatch_callback:
            return
        incoming = self._to_incoming(msg, Scene.GROUP)
        try:
            await self._dispatch_callback(incoming)
        except Exception as e:
            _log.exception("dispatch group message error: %s", e)

    async def _wrap_private(self, msg):
        """ncatbot private event handler 包装 → IncomingMessage → dispatcher"""
        if not self._dispatch_callback:
            return
        incoming = self._to_incoming(msg, Scene.PRIVATE)
        try:
            await self._dispatch_callback(incoming)
        except Exception as e:
            _log.exception("dispatch private message error: %s", e)

    def _to_incoming(self, msg, scene: Scene) -> IncomingMessage:
        """ncatbot GroupMessage/PrivateMessage → IncomingMessage

        保留 _legacy_msg 引用,使 commands.py 中命令函数体内部的
        msg.message / msg.sender.nickname / msg.self_id 等访问通过
        IncomingMessage.__getattr__ 仍能工作。
        """
        text = getattr(msg, "raw_message", "") or ""
        sender_name = ""
        sender = getattr(msg, "sender", None)
        if sender is not None:
            sender_name = getattr(sender, "nickname", "") or ""

        return IncomingMessage(
            scene=scene,
            user_id=str(getattr(msg, "user_id", "")),
            group_id=str(getattr(msg, "group_id", "")) if scene == Scene.GROUP else "",
            text=text,
            raw_message=text,
            sender_name=sender_name,
            message_id=str(getattr(msg, "message_id", "")),
            is_mentioned=self._detect_mention(msg),
            backend_name="ncatbot",
            _legacy_msg=msg,
        )

    def _detect_mention(self, msg) -> bool:
        """检测消息是否 @机器人"""
        try:
            self_id = str(getattr(msg, "self_id", "") or "")
            if not self_id:
                return False
            # 检查 message 段中的 at 元素
            message = getattr(msg, "message", None) or []
            for seg in message:
                seg_type = None
                if isinstance(seg, dict):
                    seg_type = seg.get("type")
                    data = seg.get("data") or {}
                    at_qq = str(data.get("qq", ""))
                else:
                    seg_type = getattr(seg, "type", None)
                    data = getattr(seg, "data", None) or {}
                    at_qq = str(getattr(data, "qq", "") if not isinstance(data, dict) else data.get("qq", ""))
                if seg_type == "at" and at_qq == self_id:
                    return True
        except Exception:
            pass
        return False
