"""Per-model HTTP/SOCKS proxy helpers."""

from urllib.parse import urlsplit


_SUPPORTED_SCHEMES = {"http", "socks", "socks5", "socks5h"}


def normalize_model_proxy_url(raw_url: str = "") -> str:
    """Validate and normalize a model proxy URL.

    Empty values mean direct connection. URLs without a scheme are treated as
    HTTP proxies to match the Android client behavior.
    """
    raw = str(raw_url or "").strip()
    if not raw:
        return ""

    normalized = raw if "://" in raw else f"http://{raw}"
    try:
        parsed = urlsplit(normalized)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("代理链接格式无效") from exc

    scheme = (parsed.scheme or "").lower()
    if scheme not in _SUPPORTED_SCHEMES:
        raise ValueError("代理仅支持 http:// 或 socks5://")
    if not parsed.hostname:
        raise ValueError("代理链接缺少主机")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("代理端口必须在 1 到 65535 之间")
    if scheme in {"socks", "socks5", "socks5h"} and parsed.username:
        raise ValueError("SOCKS5 代理暂不支持账号密码")

    if scheme == "socks":
        normalized = f"socks5://{normalized.split('://', 1)[1]}"
    return normalized


def model_proxy_request_kwargs(raw_url: str = "") -> dict:
    """Return keyword arguments suitable for ``requests`` calls."""
    normalized = normalize_model_proxy_url(raw_url)
    if not normalized:
        return {}
    return {"proxies": {"http": normalized, "https": normalized}}
