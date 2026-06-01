"""Gateway 日志脱敏

对日志中的敏感字段进行脱敏处理，
确保写入 Gateway Log 的数据不包含 token、密码等敏感信息。
"""

import json
from typing import Any

# 默认脱敏字段（不区分大小写匹配）
_SENSITIVE_KEYS = frozenset({
    "token", "secret", "password", "authorization",
    "api_key", "api-key", "apikey",
    "access_token", "refresh_token",
    "private_key", "client_secret",
})

# 完整脱敏字段（值替换为 ***）
_FULL_REDACT_KEYS = _SENSITIVE_KEYS | {"headers", "raw_event"}


def redact_sensitive(data: dict[str, Any]) -> dict[str, Any]:
    """脱敏敏感字段

    对已知敏感字段的值替换为 ***。
    对 headers 和 raw_event 做完整脱敏。
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        lower_key = key.lower()
        if lower_key in _FULL_REDACT_KEYS:
            result[key] = "***"
        elif isinstance(value, dict):
            result[key] = redact_sensitive(value)
        else:
            result[key] = value
    return result


def redact_content(content: str, max_preview: int = 100) -> dict[str, Any]:
    """脱敏消息内容

    不保存完整内容，只保留预览和长度。

    Returns:
        {"content_preview": "前N个字符...", "content_length": 总长度}
    """
    preview = content[:max_preview] if content else ""
    if len(content) > max_preview:
        preview = preview + "..."
    return {
        "content_preview": preview,
        "content_length": len(content),
    }


def redact_raw_event(raw_event: dict[str, Any]) -> dict[str, Any]:
    """脱敏原始事件

    不保存完整原始事件，只保留 key 列表和大小。

    Returns:
        {"raw_event_keys": [...], "raw_event_size": 字节数}
    """
    try:
        size = len(json.dumps(raw_event, ensure_ascii=False))
    except (TypeError, ValueError):
        size = 0
    return {
        "raw_event_keys": list(raw_event.keys()),
        "raw_event_size": size,
    }


def redact_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """脱敏 metadata 字段

    对 metadata 中的敏感字段进行脱敏，
    对 content 和 raw_event 子字段做摘要处理。
    """
    if not metadata:
        return None

    result: dict[str, Any] = {}
    for key, value in metadata.items():
        lower_key = key.lower()
        if lower_key in _SENSITIVE_KEYS:
            result[key] = "***"
        elif lower_key == "content" and isinstance(value, str):
            result[key] = redact_content(value)
        elif lower_key == "raw_event" and isinstance(value, dict):
            result[key] = redact_raw_event(value)
        elif lower_key == "headers":
            result[key] = "***"
        elif isinstance(value, dict):
            result[key] = redact_sensitive(value)
        else:
            result[key] = value
    return result
