"""通用消息预处理中间件

为所有频道提供统一的附件处理流水线：
1. AttachmentResolver ── 频道特定 → 可访问 URL / data URL
2. MediaDescriber ── 媒体类型 → AI 文字描述
3. MessagePreprocessor ── 编排，注入 content

附件标准格式：
    {
        "type": "image" | "file" | "video" | "audio",
        "url": "https://..." (可选，直接可访问的地址),
        "source": "qq" | "feishu" | ...,
        "source_ref": "频道的引用 key",
        "mime_type": "image/png",
        "name": "文件名",
        ...频道特定字段
    }
"""

import base64
import logging
import mimetypes
import os
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import requests

try:
    from nbot.core.workspace import workspace_manager
    _WORKSPACE_AVAILABLE = True
except ImportError:
    workspace_manager = None
    _WORKSPACE_AVAILABLE = False

_log = logging.getLogger(__name__)


def _normalize_media_type(att_type: str) -> str:
    value = str(att_type or "").lower()
    if "/" in value:
        return value.split("/", 1)[0]
    return value

# 支持描述的标准附件类型
DESCRIBABLE_TYPES = {"image", "video", "audio"}
TYPE_LABELS = {"image": "图片", "video": "视频", "audio": "音频", "file": "文件"}

# 描述失败时的错误标识，匹配到这些前缀的描述不会注入用户消息
_DESC_ERROR_PREFIXES = ("链接失效", "解析失败")


# ---------------------------------------------------------------------------
# AttachmentResolver ── 频道特定附件解析
# ---------------------------------------------------------------------------

class AttachmentResolver:
    """频道附件解析器注册表。

    每个频道注册一个 handler，接收 attachment dict，返回可直接访问的 URL
    （http URL 或 data: URL）。
    """

    _handlers: Dict[str, Callable[[Dict[str, Any]], Optional[str]]] = {}

    @classmethod
    def register(cls, channel: str, handler: Callable[[Dict[str, Any]], Optional[str]]) -> None:
        cls._handlers[channel] = handler

    @classmethod
    def resolve(cls, channel: str, attachment: Dict[str, Any]) -> Optional[str]:
        """解析附件为可访问的 URL。"""
        # 1. 频道特定处理器
        handler = cls._handlers.get(channel)
        if handler:
            result = handler(attachment)
            if result:
                return result
        # 2. 兜底：直接 URL
        return attachment.get("url")


# ---------------------------------------------------------------------------
# MediaDescriber ── AI 媒体描述
# ---------------------------------------------------------------------------

class MediaDescriber:
    """媒体描述器。按类型注册 AI 描述函数。"""

    _describers: Dict[str, Callable[[str], Optional[str]]] = {}

    @classmethod
    def register(cls, media_type: str, func: Callable[[str], Optional[str]]) -> None:
        """注册某种媒体类型的描述函数。func 接收 URL，返回文字描述。"""
        cls._describers[media_type] = func

    @classmethod
    def describe(cls, media_type: str, url: str) -> Optional[str]:
        func = cls._describers.get(media_type)
        if func is None:
            return None
        try:
            return func(url)
        except Exception as e:
            _log.warning(f"Media describe failed [{media_type}]: {e}")
            return None


# ---------------------------------------------------------------------------
# MessagePreprocessor ── 编排
# ---------------------------------------------------------------------------

class MessagePreprocessor:
    """消息预处理流水线：工作区保存 → 解析 → 描述 → 注入内容。"""

    @staticmethod
    def process(chat_request: Any, workspace_context: Optional[Dict[str, Any]] = None) -> None:
        """处理 ChatRequest.attachments，将媒体描述注入 content。

        Args:
            chat_request: 聊天请求对象
            workspace_context: 可选的工作区上下文，提供时会将附件保存到会话工作区
        """
        attachments = getattr(chat_request, "attachments", None)
        if not attachments:
            return

        descriptions = []
        processed_indices = []

        for i, att in enumerate(attachments):
            att_type = _normalize_media_type(att.get("type", ""))
            if att_type not in DESCRIBABLE_TYPES:
                continue

            channel = att.get("source", getattr(chat_request, "channel", "unknown"))
            url = AttachmentResolver.resolve(channel, att)
            if not url:
                _log.warning(f"Preprocessor: cannot resolve {att_type} attachment, source={channel}")
                continue

            # 尝试保存到会话工作区
            if workspace_context and _WORKSPACE_AVAILABLE:
                ws_file = MessagePreprocessor._save_to_workspace(
                    url, att, workspace_context
                )
                if ws_file:
                    att["_workspace_path"] = ws_file
                    # 用本地文件路径生成 data URL 供视觉模型使用
                    try:
                        mime_type, _ = mimetypes.guess_type(ws_file)
                        mime_type = mime_type or "application/octet-stream"
                        with open(ws_file, "rb") as f:
                            b64 = base64.b64encode(f.read()).decode("utf-8")
                        url = f"data:{mime_type};base64,{b64}"
                    except Exception as e:
                        _log.warning(f"Preprocessor: failed to read workspace file for AI: {e}")

            desc = MediaDescriber.describe(att_type, url)
            if desc:
                # 过滤描述失败时的错误提示，避免将"链接失效"等注入用户消息
                if any(desc.startswith(p) for p in _DESC_ERROR_PREFIXES):
                    _log.warning(
                        f"Preprocessor: describe returned error for {att_type}: {desc}"
                    )
                    continue
                label = TYPE_LABELS.get(att_type, att_type)
                descriptions.append(f"[{label}{len(descriptions)+1}描述]: {desc}")
                processed_indices.append(i)
            else:
                _log.warning(f"Preprocessor: describe failed for {att_type} attachment")

        if descriptions:
            desc_block = "\n".join(descriptions)
            original = chat_request.content or ""
            if original.strip():
                chat_request.content = f"{desc_block}\n\n用户消息: {original}"
            else:
                chat_request.content = desc_block
            _log.info(f"Preprocessor: {len(descriptions)} attachment(s) described and injected")

            remaining = [a for idx, a in enumerate(attachments) if idx not in processed_indices]
            attachments.clear()
            attachments.extend(remaining)

    @staticmethod
    def _save_to_workspace(
        url: str,
        attachment: Dict[str, Any],
        workspace_context: Dict[str, Any],
    ) -> Optional[str]:
        """尝试将附件保存到会话工作区。

        Args:
            url: 附件的可访问 URL（http/https 或 data: URL）
            attachment: 附件元数据字典
            workspace_context: 工作区上下文（含 session_id, session_type）

        Returns:
            保存成功返回文件绝对路径，失败返回 None
        """
        if not workspace_context or not _WORKSPACE_AVAILABLE or not workspace_manager:
            return None

        session_id = workspace_context.get("session_id", "")
        session_type = workspace_context.get("session_type", "unknown")
        if not session_id:
            return None

        # 确定文件名
        filename = (
            attachment.get("name")
            or attachment.get("filename")
            or attachment.get("file", "")
        )
        if not filename:
            # 从 URL 或 mime 推断
            att_type = _normalize_media_type(attachment.get("type", "file"))
            ext_map = {"image": ".png", "video": ".mp4", "audio": ".mp3", "file": ".bin"}
            filename = f"attachment{ext_map.get(att_type, '.bin')}"

        # 文件名添加时间戳前缀，避免同名文件覆盖
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name, ext = os.path.splitext(filename)
        filename = f"{timestamp}_{name}{ext}"

        # 检查工作区是否已有同名文件（去重）
        try:
            ws_path = workspace_manager.get_or_create(session_id, session_type)
            safe_name = workspace_manager._safe_filename(filename)
            existing_path = os.path.join(ws_path, safe_name)
            if os.path.exists(existing_path):
                _log.info(f"Preprocessor: file already in workspace, skip download: {safe_name}")
                return existing_path
        except Exception:
            pass

        # 下载文件内容
        file_data = None
        try:
            if url.startswith("data:"):
                # data: URL，提取 base64 内容
                _, encoded = url.split(",", 1)
                file_data = base64.b64decode(encoded)
            elif url.startswith(("http://", "https://")):
                # HTTP URL，下载文件
                resp = requests.get(url, timeout=60, stream=True)
                if resp.status_code == 200:
                    file_data = resp.content
                else:
                    _log.warning(f"Preprocessor: download failed HTTP {resp.status_code}")
                    return None
            elif os.path.isfile(url):
                # 本地文件路径
                with open(url, "rb") as f:
                    file_data = f.read()
            else:
                return None
        except Exception as e:
            _log.warning(f"Preprocessor: download attachment failed: {e}")
            return None

        if not file_data:
            return None

        # 保存到工作区
        try:
            result = workspace_manager.save_uploaded_file(
                session_id, file_data, filename, session_type
            )
            if result.get("success"):
                saved_path = result["path"]
                _log.info(f"Preprocessor: attachment saved to workspace: {os.path.basename(saved_path)}")
                return saved_path
        except Exception as e:
            _log.warning(f"Preprocessor: save to workspace failed: {e}")

        return None


# ---------------------------------------------------------------------------
# 内置频道解析器
# ---------------------------------------------------------------------------

TELEGRAM_API_BASE = "https://api.telegram.org"


def _resolve_telegram_attachment(attachment: Dict[str, Any]) -> Optional[str]:
    """Telegram：通过 getFile API 获取文件路径，下载后返回 base64 data URL。"""
    file_id = attachment.get("source_ref") or attachment.get("file_id")
    bot_token = attachment.get("bot_token")

    if not file_id or not bot_token:
        return None

    try:
        # 1. 获取文件路径
        resp = requests.get(
            f"{TELEGRAM_API_BASE}/bot{bot_token}/getFile",
            params={"file_id": file_id},
            timeout=30,
        )
        if resp.status_code != 200:
            _log.warning("Telegram getFile failed: HTTP %d — %s", resp.status_code, resp.text[:200])
            return None

        result = resp.json().get("result", {})
        file_path = result.get("file_path")
        if not file_path:
            return None

        # 2. 下载文件内容
        dl_resp = requests.get(
            f"{TELEGRAM_API_BASE}/file/bot{bot_token}/{file_path}",
            timeout=120,
        )
        if dl_resp.status_code != 200:
            _log.warning("Telegram file download failed: HTTP %d", dl_resp.status_code)
            return None

        mime = attachment.get("mime_type") or dl_resp.headers.get("Content-Type", "application/octet-stream")
        b64 = base64.b64encode(dl_resp.content).decode("utf-8")
        return f"data:{mime};base64,{b64}"
    except Exception as e:
        _log.warning("Failed to resolve Telegram attachment %s: %s", file_id, e)
        return None


def _resolve_feishu_attachment(attachment: Dict[str, Any]) -> Optional[str]:
    """飞书：通过 API 下载消息中的附件，返回 base64 data URL。"""
    ref = attachment.get("source_ref") or attachment.get("image_key") or attachment.get("file_key")
    message_id = attachment.get("message_id", "")
    app_id = attachment.get("app_id")
    app_secret = attachment.get("app_secret")

    if not ref:
        return None

    token = None
    if app_id and app_secret:
        try:
            from nbot.services.feishu_service import get_tenant_access_token
            token = get_tenant_access_token(app_id, app_secret)
        except Exception as e:
            _log.warning(f"Failed to get Feishu token: {e}")

    if not token:
        _log.warning("Feishu token is None, cannot download attachment")
        return None

    att_type = attachment.get("type", "image")
    if att_type == "image":
        resource_type = "image"
    else:
        resource_type = "file"

    if message_id:
        url = (f"https://open.feishu.cn/open-apis/im/v1/messages/"
               f"{message_id}/resources/{ref}?type={resource_type}")
    else:
        api_path = "images" if att_type == "image" else "files"
        url = f"https://open.feishu.cn/open-apis/im/v1/{api_path}/{ref}"

    try:
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
        if resp.status_code != 200:
            _log.warning(f"Feishu download failed: HTTP {resp.status_code} — {resp.text[:200]}")
            return None
        mime = resp.headers.get("Content-Type", "application/octet-stream")
        b64 = base64.b64encode(resp.content).decode("utf-8")
        return f"data:{mime};base64,{b64}"
    except Exception as e:
        _log.warning(f"Failed to download Feishu attachment {ref}: {e}")
        return None


def _resolve_direct_attachment(attachment: Dict[str, Any]) -> Optional[str]:
    return (
        attachment.get("data")
        or attachment.get("url")
        or attachment.get("download_url")
        or attachment.get("path")
    )


def _resolve_web_attachment(attachment: Dict[str, Any]) -> Optional[str]:
    """Web 频道专用附件解析：将本地路径/相对 URL 转为视觉模型可访问的地址。"""
    data = attachment.get("data")
    if data:
        return data

    path = attachment.get("path")
    if path and os.path.isfile(path):
        try:
            mime_type, _ = mimetypes.guess_type(path)
            mime_type = mime_type or "application/octet-stream"
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            return f"data:{mime_type};base64,{b64}"
        except Exception as exc:
            _log.warning("Failed to read web attachment %r as data URL: %s", path, exc)

    url = attachment.get("url") or attachment.get("download_url")
    if url:
        if url.startswith("/"):
            try:
                from nbot.web.file_gateway import get_public_base_url
                from nbot.web.server import WebChatServer

                server = WebChatServer.get_instance()
                if server:
                    base_url = get_public_base_url(server)
                    if base_url:
                        return f"{base_url.rstrip('/')}{url}"
            except Exception as exc:
                _log.warning("Failed to resolve base URL for web attachment: %s", exc)
        return url

    return None


AttachmentResolver.register("web", _resolve_web_attachment)
AttachmentResolver.register("qq", _resolve_direct_attachment)
AttachmentResolver.register("qq_private", _resolve_direct_attachment)
AttachmentResolver.register("qq_group", _resolve_direct_attachment)
AttachmentResolver.register("telegram", _resolve_telegram_attachment)
AttachmentResolver.register("feishu", _resolve_feishu_attachment)
AttachmentResolver.register("feishu_ws", _resolve_feishu_attachment)
