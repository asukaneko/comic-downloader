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

    # -------------------- NcatbotAdminBackend (阶段 2 补全) --------------------
    # 阶段 2 实施:实现所有 NcatbotAdminBackend Protocol 方法。
    # QQBotBackend 不实现这些方法,isinstance() 判断为 False 时降级为提示。

    async def set_qq_profile(self, **kwargs) -> bool:
        """设置 QQ 资料(昵称/性别/年龄等)"""
        try:
            return await self.bot.api.set_qq_profile(**kwargs)
        except Exception as e:
            _log.exception("set_qq_profile error: %s", e)
            return False

    async def set_online_status(self, status: str) -> bool:
        """设置在线状态"""
        try:
            return await self.bot.api.set_online_status(status)
        except Exception as e:
            _log.exception("set_online_status error: %s", e)
            return False

    async def set_qq_avatar(self, url: str) -> bool:
        """设置 QQ 头像"""
        try:
            return await self.bot.api.set_qq_avatar(url)
        except Exception as e:
            _log.exception("set_qq_avatar error: %s", e)
            return False

    async def send_like(self, user_id: str, times: int = 1) -> bool:
        """给用户点赞"""
        try:
            return await self.bot.api.send_like(user_id=user_id, times=times)
        except Exception as e:
            _log.exception("send_like error: %s", e)
            return False

    async def set_group_admin(
        self, group_id: str, user_id: str, enable: bool
    ) -> bool:
        """设置群管理员"""
        try:
            return await self.bot.api.set_group_admin(
                group_id=group_id, user_id=user_id, enable=enable
            )
        except Exception as e:
            _log.exception("set_group_admin error: %s", e)
            return False

    async def set_friend_add_request(
        self, flag: str, approve: bool, remark: str = ""
    ) -> bool:
        """处理好友添加请求"""
        try:
            return await self.bot.api.set_friend_add_request(
                flag=flag, approve=approve, remark=remark
            )
        except Exception as e:
            _log.exception("set_friend_add_request error: %s", e)
            return False

    async def get_group_msg_history(
        self, group_id, count: int = 20, **kwargs
    ) -> list:
        """获取群历史消息

        ncatbot 签名: get_group_msg_history(group_id, message_seq, count, reverse_order)
        兼容 ncatbot 风格: 接受 **kwargs 透传 message_seq / reverse_order
        """
        try:
            message_seq = kwargs.get("message_seq", 0)
            reverse_order = kwargs.get("reverse_order", True)
            result = await self.bot.api.get_group_msg_history(
                group_id=group_id,
                message_seq=message_seq,
                count=count,
                reverse_order=reverse_order,
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            _log.exception("get_group_msg_history error: %s", e)
            return []

    async def get_friend_list(self) -> list:
        """获取好友列表"""
        try:
            result = await self.bot.api.get_friend_list()
            return result if isinstance(result, list) else []
        except Exception as e:
            _log.exception("get_friend_list error: %s", e)
            return []

    async def get_msg(self, message_id: str) -> dict:
        """获取消息详情"""
        try:
            result = await self.bot.api.get_msg(message_id=message_id)
            return result if isinstance(result, dict) else {}
        except Exception as e:
            _log.exception("get_msg error: %s", e)
            return {}

    async def get_recent_contact(self) -> list:
        """获取最近联系人"""
        try:
            result = await self.bot.api.get_recent_contact()
            return result if isinstance(result, list) else []
        except Exception as e:
            _log.exception("get_recent_contact error: %s", e)
            return []

    async def get_file_sync(self, file_id: str) -> dict:
        """同步获取文件信息(包装 ncatbot 同步 API)

        阶段 3 实施:message_middleware.py 中用
        """
        try:
            return self.bot.api.get_file_sync(file_id=file_id)
        except Exception as e:
            _log.exception("get_file_sync error: %s", e)
            return {}

    async def download_file_sync(
        self, thread_count: int, headers, url: str
    ) -> bytes:
        """同步下载文件(包装 ncatbot 同步 API)

        阶段 3 实施:message_middleware.py 中用
        """
        try:
            return self.bot.api.download_file_sync(
                thread_count=thread_count, headers=headers, url=url
            )
        except Exception as e:
            _log.exception("download_file_sync error: %s", e)
            return b""

    # -------------------- RawApiBackend (阶段 2 补全) --------------------

    async def call_raw_api(self, func_name: str, **params):
        """透传 ncatbot 原生 API(用于 /bot 动态命令)

        rev. 2 关键:ncatbot 路径直接 getattr 调原生 API
        """
        try:
            method = getattr(self.bot.api, func_name, None)
            if method is None:
                _log.warning("call_raw_api: bot.api has no method %s", func_name)
                return None
            return await method(**params)
        except Exception as e:
            _log.exception("call_raw_api error: %s", e)
            return None
