import logging
import os
from typing import Any, Dict, List, Optional

import requests

_log = logging.getLogger(__name__)

from nbot.channels.telegram import TelegramChannelAdapter
from nbot.core.ai_pipeline import (
    AIPipeline,
    PipelineContext,
    PipelineCallbacks,
    PipelineResult,
    handle_tool_confirmation,
)

TELEGRAM_API_BASE = "https://api.telegram.org"


def resolve_config_secret(
    config: Dict[str, Any],
    value_key: str,
    env_key: str,
    default_env: str = "",
) -> str:
    env_name = str(config.get(env_key) or default_env or "").strip()
    if env_name:
        value = os.getenv(env_name)
        if value:
            return value.strip()
    return str(config.get(value_key) or "").strip()


def resolve_telegram_token(config: Dict[str, Any]) -> str:
    return resolve_config_secret(
        config,
        "bot_token",
        "bot_token_env",
        default_env="TELEGRAM_BOT_TOKEN",
    )


def send_telegram_message(
    token: str,
    chat_id: str,
    text: str,
    *,
    reply_to_message_id: Optional[int] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text[:4096] if text else "",
        "disable_web_page_preview": True,
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    response = requests.post(
        f"{TELEGRAM_API_BASE}/bot{token}/sendMessage",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def send_telegram_photo(
    token: str,
    chat_id: str,
    photo: str,
    caption: str = "",
    *,
    reply_to_message_id: Optional[int] = None,
) -> Dict[str, Any]:
    """发送图片到 Telegram。photo 支持 file_id、URL 或本地文件路径。"""
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "photo": photo,
    }
    if caption:
        payload["caption"] = caption[:1024]
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    response = requests.post(
        f"{TELEGRAM_API_BASE}/bot{token}/sendPhoto",
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def send_telegram_photo_file(
    token: str,
    chat_id: str,
    file_path: str,
    caption: str = "",
    *,
    reply_to_message_id: Optional[int] = None,
) -> Dict[str, Any]:
    """通过 multipart 上传本地图片文件到 Telegram。"""
    payload: Dict[str, Any] = {"chat_id": chat_id}
    if caption:
        payload["caption"] = caption[:1024]
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    with open(file_path, "rb") as f:
        response = requests.post(
            f"{TELEGRAM_API_BASE}/bot{token}/sendPhoto",
            data=payload,
            files={"photo": f},
            timeout=120,
        )
    response.raise_for_status()
    return response.json()


def send_telegram_document(
    token: str,
    chat_id: str,
    document: str,
    caption: str = "",
    *,
    reply_to_message_id: Optional[int] = None,
) -> Dict[str, Any]:
    """发送文件到 Telegram。document 支持 file_id、URL 或本地文件路径。"""
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "document": document,
    }
    if caption:
        payload["caption"] = caption[:1024]
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    response = requests.post(
        f"{TELEGRAM_API_BASE}/bot{token}/sendDocument",
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def send_telegram_document_file(
    token: str,
    chat_id: str,
    file_path: str,
    caption: str = "",
    filename: str = "",
    *,
    reply_to_message_id: Optional[int] = None,
) -> Dict[str, Any]:
    """通过 multipart 上传本地文件到 Telegram。"""
    payload: Dict[str, Any] = {"chat_id": chat_id}
    if caption:
        payload["caption"] = caption[:1024]
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    with open(file_path, "rb") as f:
        files = {"document": (filename or os.path.basename(file_path), f)}
        response = requests.post(
            f"{TELEGRAM_API_BASE}/bot{token}/sendDocument",
            data=payload,
            files=files,
            timeout=120,
        )
    response.raise_for_status()
    return response.json()


def _send_telegram_attachments(
    token: str,
    chat_id: str,
    attachments: List[Dict[str, Any]],
    caption: str = "",
    *,
    reply_to_message_id: Optional[int] = None,
) -> None:
    """发送附件列表到 Telegram，按类型分发到 sendPhoto / sendDocument。"""
    for i, att in enumerate(attachments):
        att_type = att.get("type", "")
        url = att.get("url") or att.get("data") or att.get("path") or att.get("source_ref", "")
        att_caption = caption if i == 0 else ""

        try:
            if att_type == "image":
                if url.startswith("data:") or url.startswith("http"):
                    send_telegram_photo(token, chat_id, url, att_caption, reply_to_message_id=reply_to_message_id)
                elif os.path.isfile(url):
                    send_telegram_photo_file(token, chat_id, url, att_caption, reply_to_message_id=reply_to_message_id)
                else:
                    send_telegram_photo(token, chat_id, url, att_caption, reply_to_message_id=reply_to_message_id)
            elif att_type in ("file", "video", "audio"):
                if url.startswith("data:") or url.startswith("http"):
                    send_telegram_document(token, chat_id, url, att_caption, reply_to_message_id=reply_to_message_id)
                elif os.path.isfile(url):
                    filename = att.get("name", "")
                    send_telegram_document_file(token, chat_id, url, att_caption, filename, reply_to_message_id=reply_to_message_id)
                else:
                    send_telegram_document(token, chat_id, url, att_caption, reply_to_message_id=reply_to_message_id)

            # 后续附件不再回复原消息
            reply_to_message_id = None
        except Exception as e:
            _log.warning("Failed to send Telegram attachment (type=%s): %s", att_type, e)


def set_telegram_webhook(config: Dict[str, Any], webhook_url: str) -> Dict[str, Any]:
    token = resolve_telegram_token(config)
    if not token:
        raise ValueError("未配置 Telegram bot token，请设置 TELEGRAM_BOT_TOKEN")

    payload: Dict[str, Any] = {"url": webhook_url}
    secret = resolve_config_secret(config, "secret_token", "secret_token_env")
    if (config.get("secret_token") or config.get("secret_token_env")) and not secret:
        raise ValueError("Telegram webhook secret 未配置或环境变量为空")
    if secret:
        payload["secret_token"] = secret

    response = requests.post(
        f"{TELEGRAM_API_BASE}/bot{token}/setWebhook",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


# ============================================================================
# Telegram 管道回调
# ============================================================================


class TelegramCallbacks(PipelineCallbacks):
    """Telegram 频道的管道回调实现。"""

    def __init__(
        self,
        server: Any,
        token: str,
        parsed: Dict[str, Any],
    ):
        self.server = server
        self.token = token
        self.parsed = parsed

    def get_system_prompt(self, ctx: PipelineContext) -> str:
        return str(
            getattr(self.server, "personality", {}).get("systemPrompt") or ""
        ).strip()

    def get_workspace_context(self, ctx: PipelineContext) -> Dict[str, Any]:
        character_name = str(
            getattr(self.server, "personality", {}).get("name") or ""
        ).strip()
        context: Dict[str, Any] = {
            "session_id": f"telegram:{self.parsed['chat_id']}",
            "session_type": "telegram",
        }
        if character_name:
            context["character_name"] = character_name
        target_id = str(
            self.parsed.get("user_id") or self.parsed.get("chat_id") or ""
        ).strip()
        if target_id:
            context["target_id"] = target_id
            context["user_id"] = target_id
        return context

    def get_character_context(self, ctx: PipelineContext):
        """返回 Telegram 频道的角色身份标识"""
        from nbot.character.adapters.nekobot import get_telegram_character_context

        personality_name = str(
            getattr(self.server, "personality", {}).get("name") or "default"
        )
        return get_telegram_character_context(
            user_id=self.parsed.get("user_id", ""),
            chat_id=self.parsed.get("chat_id"),
            thread_id=self.parsed.get("thread_id"),
            personality_name=personality_name,
        )

    def get_character_runtime(self, ctx: PipelineContext):
        """返回角色运行时实例"""
        from nbot.character.adapters.nekobot import get_character_runtime_from_server

        return get_character_runtime_from_server(self.server)

    def send_response(self, ctx: PipelineContext, message: Dict[str, Any]) -> None:
        content = message.get("content", "")
        attachments = message.get("attachments") or []
        chat_id = self.parsed["chat_id"]
        reply_id = self.parsed.get("message_id")

        # 先发送附件（图片/文件）
        if attachments:
            _send_telegram_attachments(
                self.token, chat_id, attachments,
                caption=content[:1024] if content else "",
                reply_to_message_id=reply_id,
            )
            # 如果有附件且有文本，文本单独再发一次（因为 caption 有长度限制）
            if content and len(content) > 1024:
                send_telegram_message(
                    self.token, chat_id, content,
                    reply_to_message_id=None,
                )
        elif content:
            send_telegram_message(
                self.token, chat_id, content,
                reply_to_message_id=reply_id,
            )


# ============================================================================
# 入口函数
# ============================================================================


def answer_telegram_update(
    server: Any, channel: Dict[str, Any], update: Dict[str, Any]
) -> Dict[str, Any]:
    adapter = TelegramChannelAdapter()
    parsed = adapter.parse_update(update or {})
    if not parsed:
        return {"ok": True, "ignored": True}

    config = channel.get("config") or {}
    token = resolve_telegram_token(config)
    if not token:
        raise ValueError("未配置 Telegram bot token，请设置 TELEGRAM_BOT_TOKEN")

    # 确认/拒绝待执行命令
    content = handle_tool_confirmation(
        parsed["content"],
        f"telegram:{parsed['chat_id']}",
        log_prefix="Telegram",
    )

    chat_request = adapter.build_chat_request(
        conversation_id=f"telegram:{parsed['chat_id']}",
        user_id=parsed.get("user_id", ""),
        content=content,
        sender=parsed.get("sender", "telegram_user"),
        metadata=parsed.get("metadata", {}),
    )

    # 注入 bot_token 到附件，供 AttachmentResolver 下载文件使用
    if chat_request.attachments:
        for att in chat_request.attachments:
            att.setdefault("bot_token", token)

    ctx = PipelineContext(chat_request=chat_request, adapter=adapter)
    ctx.metadata["channel_type"] = "telegram"
    ctx.metadata["source"] = "telegram"
    try:
        from nbot.services.ai import refresh_runtime_ai_config
        runtime_ai = refresh_runtime_ai_config()
        ctx.metadata["input_price"] = runtime_ai.get("input_price")
        ctx.metadata["output_price"] = runtime_ai.get("output_price")
    except Exception:
        pass
    callbacks = TelegramCallbacks(server, token, parsed)

    pipeline = AIPipeline()

    hook_runtime = None
    try:
        from nbot.hooks.manager import get_hook_manager
        hook_runtime = get_hook_manager()
    except Exception:
        pass

    result = pipeline.process(ctx, callbacks, hook_runtime=hook_runtime)

    # 返回飞书格式兼容的结果（调用方期望 Dict）
    return {"ok": True, "result": result.final_content}
