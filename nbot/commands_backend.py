"""Bot 后端抽象层 —— 屏蔽 ncatbot / qqbot 差异

阶段 1 范围（文本消息链路）：
- IncomingMessage dataclass + 兼容层(__getattr__ fallback 到 ncatbot msg)
- BotBackend Protocol(核心)
- 全局 getter/setter
- MediaBackend / NcatbotAdminBackend / RawApiBackend Protocol 占位(阶段 2/3 补全)

设计要点：
- IncomingMessage 是 dataclass,但通过 __getattr__ 兼容 ncatbot msg 风格访问
- 阶段 1 不需要修改 commands.py 中命令函数体内部的 msg.message / msg.sender.nickname 等访问
- IncomingMessage.reply() 第一版只支持 text,富媒体走 backend 显式方法
- BotBackend 是 Protocol,ncatbot_backend 和 qqbot_backend 不需要显式继承
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

_log = logging.getLogger(__name__)


class Scene(str, Enum):
    """消息场景"""
    GROUP = "group"
    PRIVATE = "private"


# dataclass 字段名集合(用于 __getattr__ 白名单)
_DATACLASS_FIELDS = frozenset({
    "scene", "user_id", "text", "group_id", "sender_name",
    "message_id", "is_mentioned", "raw_message", "backend_name",
    "metadata", "_legacy_msg",
})


@dataclass
class IncomingMessage:
    """统一入站消息格式 —— 阶段 1 兼容 ncatbot msg 风格

    rev. 2 第一版 reply() 只支持 text,富媒体走 backend 显式方法。

    兼容层(__getattr__):
    - 如果 _legacy_msg 存在,访问的字段不在 dataclass 字段中时,fallback 到 _legacy_msg
    - 这样 commands.py 中命令函数体内部的 msg.message / msg.sender.nickname / msg.self_id
      等访问仍能工作(ncatbot 模式下 _legacy_msg 指向 ncatbot 原 msg 对象)
    - 阶段 2/3 逐步替换这些访问为 IncomingMessage 字段
    """
    scene: Scene
    user_id: str
    text: str = ""
    group_id: str = ""
    sender_name: str = ""
    message_id: str = ""
    is_mentioned: bool = False
    raw_message: Any = None
    backend_name: str = "unknown"
    metadata: dict = field(default_factory=dict)
    _legacy_msg: Any = field(default=None, repr=False, compare=False)

    @property
    def is_group(self) -> bool:
        return self.scene == Scene.GROUP

    def __getattr__(self, name: str) -> Any:
        # dataclass 字段(包括 _legacy_msg)优先于 __getattr__
        # 这里的 __getattr__ 只在常规属性查找失败时被调用
        if name in _DATACLASS_FIELDS:
            raise AttributeError(f"IncomingMessage has no attribute {name!r}")
        # 内部字段(以下划线开头)不通过 legacy fallback
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        # fallback 到 _legacy_msg
        legacy = self.__dict__.get("_legacy_msg")
        if legacy is not None and hasattr(legacy, name):
            return getattr(legacy, name)
        raise AttributeError(f"IncomingMessage has no attribute {name!r}")

    async def reply(self, text: str | None = None, **kwargs) -> bool:
        """便捷文本回复 —— 自动选择私聊/群聊路径

        阶段 1: 只支持 text 参数。kwargs 中其他参数被忽略
        (保持与 ncatbot msg.reply(text=...) 签名兼容)。
        """
        if text is None:
            return False
        backend = get_backend()
        if self.is_group:
            return await backend.send_group_text(self.group_id, text)
        return await backend.send_private_text(self.user_id, text)


@runtime_checkable
class BotBackend(Protocol):
    """核心 BotBackend —— 所有后端必须实现

    rev. 2: run_forever() 是同步方法,由 backend 内部决定如何阻塞
            不外层包 asyncio.run(),避免与 ncatbot BotClient 内部事件循环冲突
    """
    name: str
    is_running: bool

    async def start(self) -> None:
        """异步初始化:建立连接、获取 token 等"""
        ...

    def run_forever(self) -> None:
        """同步阻塞入口"""
        ...

    async def stop(self) -> None:
        """异步停止"""
        ...

    async def send_private_text(self, user_id: str, text: str) -> bool: ...
    async def send_group_text(self, group_id: str, text: str) -> bool: ...
    def supports(self, capability: str) -> bool: ...


@runtime_checkable
class MediaBackend(Protocol):
    """富媒体能力(可选) —— 阶段 3 补全

    阶段 1: NcatbotBackend / QQBotBackend 不实现此 Protocol
            isinstance() 判断为 False
    """
    async def send_private_image(self, user_id: str, image_path: str) -> bool: ...
    async def send_group_image(self, group_id: str, image_path: str) -> bool: ...
    async def send_group_voice(self, group_id: str, voice_path: str) -> bool: ...
    async def send_group_file(self, group_id: str, file_path: str) -> bool: ...
    async def send_private_file(self, user_id: str, file_path: str) -> bool: ...
    async def reply_message(self, message_id: str, text: str, *,
                            is_group: bool = False, target_id: str = "") -> bool: ...


@runtime_checkable
class NcatbotAdminBackend(Protocol):
    """ncatbot / OneBot 专属管理能力 —— 阶段 2 补全

    阶段 1: NcatbotBackend / QQBotBackend 不实现此 Protocol
    阶段 2: NcatbotBackend 完整实现,QQBotBackend 不实现
            isinstance() 判断为 False 时降级为"当前后端不支持"提示
    """
    async def set_qq_profile(self, **kwargs) -> bool: ...
    async def set_online_status(self, status: str) -> bool: ...
    async def set_qq_avatar(self, url: str) -> bool: ...
    async def send_like(self, user_id: str, times: int = 1) -> bool: ...
    async def set_group_admin(self, group_id: str, user_id: str, enable: bool) -> bool: ...
    async def set_friend_add_request(self, flag: str, approve: bool, remark: str = "") -> bool: ...
    async def get_group_msg_history(self, group_id, count: int = 20, **kwargs) -> list: ...
    async def get_friend_list(self) -> list: ...
    async def get_msg(self, message_id: str) -> dict: ...
    async def get_recent_contact(self) -> list: ...
    def get_file_sync(self, file_id: str) -> dict: ...
    def download_file_sync(self, thread_count: int, headers: dict, url: str) -> bytes: ...


@runtime_checkable
class RawApiBackend(Protocol):
    """透传原生 API —— 阶段 2 补全"""
    async def call_raw_api(self, func_name: str, **params) -> Any: ...


class Capability:
    """能力字符串常量(用于 supports())"""
    GROUP_TEXT = "group_text"
    PRIVATE_TEXT = "private_text"
    GROUP_IMAGE = "group_image"
    GROUP_VOICE = "group_voice"
    GROUP_FILE = "group_file"
    PRIVATE_IMAGE = "private_image"
    PRIVATE_FILE = "private_file"
    REPLY_MESSAGE = "reply_message"
    SET_QQ_PROFILE = "set_qq_profile"
    SET_QQ_AVATAR = "set_qq_avatar"
    SEND_LIKE = "send_like"
    SET_GROUP_ADMIN = "set_group_admin"
    GET_GROUP_HISTORY = "get_group_history"
    GET_FRIEND_LIST = "get_friend_list"
    GET_MSG = "get_msg"
    GET_RECENT_CONTACT = "get_recent_contact"
    FILE_DOWNLOAD = "file_download"
    RAW_API = "raw_api"


# 全局后端注册
_active_backend: BotBackend | None = None


def set_backend(backend: BotBackend) -> None:
    """由 bot.py 启动时调用,绑定当前激活后端"""
    global _active_backend
    _active_backend = backend
    _log.info("Bot backend set: %s", backend.name)


def get_backend() -> BotBackend:
    """命令系统获取当前后端 —— 启动后必非 None,启动前调用会抛错"""
    if _active_backend is None:
        raise RuntimeError(
            "Bot backend not initialized. Call set_backend() first."
        )
    return _active_backend


def reset_backend() -> None:
    """测试辅助 —— 重置全局后端"""
    global _active_backend
    _active_backend = None
