"""BotApiAdapter —— 包装 ncatbot BotAPI 实例,内部走 BotBackend 抽象

阶段 2 务实方案:commands.py 中 192 处 `await bot.api.post_private_msg(...)`
等调用**不需要逐个替换**。通过把 `bot.api` 替换为 BackendApiAdapter 实例,
所有调用自动走 get_backend() 抽象:

- text 消息 → backend.send_private_text / send_group_text
  (ncatbot 路径仍触发 BotAPI monkey-patch,消息持久化正常工作)
- rtf 消息 (语音) → ncatbot 原生 (阶段 3 改造)
- 文件消息 → ncatbot 原生 (阶段 3 改造)
- 管理类 API → isinstance(backend, NcatbotAdminBackend) 判断后调 backend

阶段 4 时可以彻底清理,删除此 adapter,直接用 get_backend() 调用。
"""
from __future__ import annotations

import logging
from typing import Any

from nbot.commands_backend import (
    NcatbotAdminBackend,
    get_backend,
)

_log = logging.getLogger(__name__)


class BotApiAdapter:
    """BotAPI 适配器 —— 包装 ncatbot BotAPI 实例,所有方法内部走 backend 抽象

    阶段 2 实施:此 adapter 让 commands.py 中 192 处 bot.api.post_private_msg
    等调用自动走 get_backend().send_*_text,不需要逐个替换。
    """

    def __init__(self, real_api: Any):
        self._real = real_api

    # -------------------- 文本消息(走 backend) --------------------

    async def post_private_msg(self, user_id, **kwargs):
        """私聊消息 —— text 走 backend, rtf 走 ncatbot 原生"""
        if "text" in kwargs:
            backend = get_backend()
            return await backend.send_private_text(user_id, kwargs["text"])
        # rtf 等富媒体: 阶段 3 处理, 暂走 ncatbot 原生
        return await self._real.post_private_msg(user_id, **kwargs)

    async def post_group_msg(self, group_id, **kwargs):
        """群消息 —— text 走 backend, rtf 走 ncatbot 原生"""
        if "text" in kwargs:
            backend = get_backend()
            return await backend.send_group_text(group_id, kwargs["text"])
        # rtf 等富媒体: 阶段 3 处理, 暂走 ncatbot 原生
        return await self._real.post_group_msg(group_id, **kwargs)

    # -------------------- 文件消息(阶段 3 改造) --------------------

    async def post_group_file(self, group_id, **kwargs):
        """群文件 —— 阶段 3: 改用 backend.send_group_file"""
        return await self._real.post_group_file(group_id, **kwargs)

    async def post_private_file(self, user_id, **kwargs):
        """私聊文件 —— 阶段 3 改造"""
        return await self._real.post_private_file(user_id, **kwargs)

    async def upload_private_file(self, user_id, file, name=None, **kwargs):
        """私聊文件上传 —— 阶段 3 改造

        ncatbot 3.8.5 签名: upload_private_file(user_id, file, name)
        """
        if name is not None:
            return await self._real.upload_private_file(
                user_id, file, name, **kwargs
            )
        return await self._real.upload_private_file(user_id, file, **kwargs)

    # -------------------- 管理类 API(走 backend) --------------------

    async def set_qq_profile(self, **kwargs):
        backend = get_backend()
        if isinstance(backend, NcatbotAdminBackend):
            return await backend.set_qq_profile(**kwargs)
        _log.warning("set_qq_profile: 当前后端不支持")
        return False

    async def set_online_status(self, status):
        backend = get_backend()
        if isinstance(backend, NcatbotAdminBackend):
            return await backend.set_online_status(status)
        _log.warning("set_online_status: 当前后端不支持")
        return False

    async def set_qq_avatar(self, url):
        backend = get_backend()
        if isinstance(backend, NcatbotAdminBackend):
            return await backend.set_qq_avatar(url)
        _log.warning("set_qq_avatar: 当前后端不支持")
        return False

    async def send_like(self, user_id, times=1):
        backend = get_backend()
        if isinstance(backend, NcatbotAdminBackend):
            return await backend.send_like(user_id, times=times)
        _log.warning("send_like: 当前后端不支持")
        return False

    async def set_group_admin(self, group_id, user_id, enable):
        backend = get_backend()
        if isinstance(backend, NcatbotAdminBackend):
            return await backend.set_group_admin(group_id, user_id, enable)
        _log.warning("set_group_admin: 当前后端不支持")
        return False

    async def set_friend_add_request(self, flag, approve, remark=""):
        backend = get_backend()
        if isinstance(backend, NcatbotAdminBackend):
            return await backend.set_friend_add_request(flag, approve, remark)
        _log.warning("set_friend_add_request: 当前后端不支持")
        return False

    # -------------------- 查询类 API --------------------

    async def get_friend_list(self):
        backend = get_backend()
        if isinstance(backend, NcatbotAdminBackend):
            return await backend.get_friend_list()
        return []

    async def get_msg(self, message_id):
        backend = get_backend()
        if isinstance(backend, NcatbotAdminBackend):
            return await backend.get_msg(message_id)
        return {}

    async def get_recent_contact(self):
        backend = get_backend()
        if isinstance(backend, NcatbotAdminBackend):
            return await backend.get_recent_contact()
        return []

    async def get_group_msg_history(self, group_id, message_seq=0, count=20, reverse_order=True, **kwargs):
        """get_group_msg_history: ncatbot 签名 (group_id, message_seq, count, reverse_order)"""
        backend = get_backend()
        if isinstance(backend, NcatbotAdminBackend):
            return await backend.get_group_msg_history(
                group_id, count=count, message_seq=message_seq, reverse_order=reverse_order, **kwargs
            )
        return []

    # -------------------- 同步 API(阶段 3 改造) --------------------

    def get_file_sync(self, file_id):
        """同步获取文件 —— message_middleware.py 用"""
        return self._real.get_file_sync(file_id=file_id)

    def download_file_sync(self, thread_count, headers, url=None, name=None):
        """同步下载文件 —— message_middleware.py 用"""
        kwargs = {"thread_count": thread_count, "headers": headers}
        if url is not None:
            kwargs["url"] = url
        if name is not None:
            kwargs["name"] = name
        return self._real.download_file_sync(**kwargs)

    # -------------------- 透传(走 backend) --------------------

    def __getattr__(self, name):
        """未包装的属性 → 透传到真实 bot.api

        例如: bot.api.xxxx (动态属性访问) 直接走 ncatbot
        但 ncatbot 的方法调用是 await,所以此 fallback 不常用
        """
        return getattr(self._real, name)
