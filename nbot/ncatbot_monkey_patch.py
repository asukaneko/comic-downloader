"""Ncatbot monkey-patch 模块 —— 阶段 5 抽出

将 commands.py 顶层的 ncatbot BotAPI / GroupMessage / PrivateMessage
类方法 monkey-patch 逻辑封装到此模块。

rev. 5: 阶段 5 实施 —— 彻底迁移 ncatbot 依赖
- commands.py 顶部无 ncatbot import
- 由 NcatbotBackend.start() 显式调用 apply_patches()
- QQBot 路径不调用 apply_patches() (monkey-patch 仅对 ncatbot 有效)

monkey-patch 目的:
- BotAPI.post_private_msg: 自动写入消息持久化日志
- BotAPI.post_group_msg: 自动写入消息持久化日志 + 处理群回复上下文
- GroupMessage.reply: 记录群回复时的 user_id 上下文(供 group_msg 关联)
"""
from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

# 模块级状态:防止重复应用补丁
_applied = False
# 群回复上下文(供 wrapped_group_reply 和 wrapped_post_group_msg 共享)
_pending_group_reply_context: dict = {}


def _strip_markers(content: str) -> str:
    """剥离 <||> 标记(MessageFilter.strip_default_markers 的简化包装)"""
    try:
        from nbot.message_filter import MessageFilter
        return MessageFilter.strip_default_markers(content)
    except Exception:
        return content


def _record_assistant(content: str, **kwargs) -> None:
    """记录 assistant 消息到历史(失败不抛)"""
    try:
        from nbot.services.chat_service import record_assistant_message
        record_assistant_message(content, **kwargs)
    except Exception:
        pass


def _log_to_group_full_file(group_id, bot_id, sender, content) -> None:
    """写入群聊全量日志(失败不抛)"""
    try:
        from nbot.services.chat_service import log_to_group_full_file
        log_to_group_full_file(group_id, bot_id, sender, content)
    except Exception:
        pass


def apply_patches() -> bool:
    """应用 ncatbot 类级别 monkey-patch

    Returns:
        True=新应用成功, False=已应用过(幂等)

    rev. 5 关键: 此函数由 NcatbotBackend.start() 显式调用。
    QQBot 路径不调用此函数。
    """
    global _applied
    if _applied:
        return False

    try:
        from ncatbot.core import BotAPI, GroupMessage
    except ImportError:
        _log.warning("ncatbot not installed, monkey-patch skipped")
        return False

    if hasattr(BotAPI, "_nbot_patched"):
        return False

    original_post_private_msg = BotAPI.post_private_msg
    original_post_group_msg = BotAPI.post_group_msg
    original_group_reply = GroupMessage.reply
    # PrivateMessage.reply 没有 wrapped 版本(无人调用),保留原始

    async def wrapped_post_private_msg(self, user_id, **kwargs):
        content = kwargs.get("text", "")
        if content and isinstance(content, str):
            stripped = _strip_markers(content)
            if stripped != content:
                kwargs["text"] = stripped
                content = stripped
            _record_assistant(content, user_id=user_id)
        return await original_post_private_msg(self, user_id, **kwargs)

    async def wrapped_post_group_msg(self, group_id, **kwargs):
        content = kwargs.get("text", "")
        if content and isinstance(content, str):
            stripped = _strip_markers(content)
            if stripped != content:
                kwargs["text"] = stripped
                content = stripped
            try:
                context_key = (str(group_id), content)
                pending_users = _pending_group_reply_context.get(context_key, [])
                group_user_id = (
                    pending_users.pop(0) if pending_users
                    else kwargs.get("group_user_id")
                )
                if pending_users:
                    _pending_group_reply_context[context_key] = pending_users
                else:
                    _pending_group_reply_context.pop(context_key, None)
                _record_assistant(
                    content,
                    group_id=group_id,
                    group_user_id=group_user_id,
                )
                # 写入群聊全量日志(需要 bot_id,从 commands 模块读取)
                from nbot import commands
                bot_id = getattr(commands, "bot_id", "bot")
                _log_to_group_full_file(group_id, bot_id, "机器人", content)
            except Exception:
                pass
        return await original_post_group_msg(self, group_id, **kwargs)

    async def wrapped_group_reply(self, text=None, **kwargs):
        content = text if isinstance(text, str) else kwargs.get("text", "")
        if content and isinstance(content, str):
            stripped = _strip_markers(content)
            if stripped != content:
                text = stripped
                kwargs["text"] = stripped
            context_key = (
                str(self.group_id),
                stripped if stripped != content else content,
            )
            _pending_group_reply_context.setdefault(
                context_key, []
            ).append(str(self.user_id))
        return await original_group_reply(self, text=text, **kwargs)

    # 应用补丁到类级别
    BotAPI.post_private_msg = wrapped_post_private_msg
    BotAPI.post_group_msg = wrapped_post_group_msg
    GroupMessage.reply = wrapped_group_reply
    BotAPI._nbot_patched = True

    _applied = True
    _log.info("ncatbot monkey-patch applied successfully")
    return True


def is_applied() -> bool:
    """检查 monkey-patch 是否已应用"""
    return _applied
