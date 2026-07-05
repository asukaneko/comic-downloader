"""WebDAV 配置备份/同步模块。

用户只需填写 WebDAV 根地址（如 https://dav.jianguoyun.com/dav/），
本模块会在该地址下自动创建 ``nekobot`` 文件夹，并将加密后的
``config.nbotcfg`` 配置包放置其中，实现多端备份与同步。
"""

import json
import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import requests

from nbot.web.config_transfer import (
    ConfigTransferError,
    apply_bundle,
    decrypt_bundle,
    encrypt_bundle,
)

_log = logging.getLogger(__name__)

# 默认请求超时（秒）
DEFAULT_TIMEOUT = 30
# 视为大文件的上传阈值（50MB）
LARGE_FILE_THRESHOLD = 50 * 1024 * 1024

# 远程文件夹名与配置文件名（用户无需填写）
BACKUP_FOLDER = "nekobot"
BACKUP_FILENAME = "config.nbotcfg"


class WebDAVBackupError(RuntimeError):
    """WebDAV 备份/同步过程中出现的错误"""


def _normalize_base_url(url: str) -> str:
    """规范化 WebDAV 根地址：去除末尾斜杠，校验协议。"""
    url = (url or "").strip()
    if not url:
        raise WebDAVBackupError("WebDAV 根地址不能为空")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise WebDAVBackupError("WebDAV 根地址必须以 http:// 或 https:// 开头")
    return url.rstrip("/")


def _resolve_folder_url(base_url: str) -> str:
    """获取 nekobot 文件夹的完整 URL（带末尾斜杠）。"""
    return f"{_normalize_base_url(base_url)}/{BACKUP_FOLDER}/"


def _resolve_file_url(base_url: str) -> str:
    """获取 cfg 文件的完整 URL。"""
    return f"{_normalize_base_url(base_url)}/{BACKUP_FOLDER}/{BACKUP_FILENAME}"


def _build_auth(config: dict[str, Any]):
    username = str(config.get("username") or "").strip()
    password = str(config.get("password") or "")
    if username:
        return (username, password)
    return None


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def _try_resolve_file_url_safely(base_url: str) -> str:
    """安全版本：base_url 非法时返回空字符串而非抛异常（用于 get_config）。"""
    try:
        return _resolve_file_url(base_url)
    except WebDAVBackupError:
        return ""


def get_config(server) -> dict[str, Any]:
    """读取 WebDAV 备份配置（密码字段会被脱敏）。"""
    raw = (server.settings.get("webdav_backup") or {}) if isinstance(server.settings, dict) else {}
    base_url = str(raw.get("url") or "")
    return {
        "enabled": bool(raw.get("enabled")),
        "url": base_url,
        "resolved_file_url": _try_resolve_file_url_safely(base_url),
        "folder": BACKUP_FOLDER,
        "filename": BACKUP_FILENAME,
        "username": str(raw.get("username") or ""),
        "password": _mask(str(raw.get("password") or "")),
        "encryption_password": _mask(str(raw.get("encryption_password") or "")),
        "has_password": bool(raw.get("password")),
        "has_encryption_password": bool(raw.get("encryption_password")),
        "last_backup_at": str(raw.get("last_backup_at") or ""),
        "last_sync_at": str(raw.get("last_sync_at") or ""),
        "last_error": str(raw.get("last_error") or ""),
        "last_file_size": int(raw.get("last_file_size") or 0),
        "last_modified": str(raw.get("last_modified") or ""),
    }


def save_config(server, payload: dict[str, Any]) -> dict[str, Any]:
    """保存 WebDAV 备份配置。

    密码字段为空字符串或形如 "****" 时视为不修改，保留原值。
    """
    if not isinstance(server.settings, dict):
        server.settings = {}
    current = dict(server.settings.get("webdav_backup") or {})

    if "enabled" in payload:
        current["enabled"] = bool(payload.get("enabled"))
    if "url" in payload:
        current["url"] = str(payload.get("url") or "")
    if "username" in payload:
        current["username"] = str(payload.get("username") or "")

    # 密码字段：空字符串或掩码字符串视为不修改
    new_password = payload.get("password")
    if new_password is None:
        pass
    elif new_password == "" and payload.get("clear_password"):
        current["password"] = ""
    elif isinstance(new_password, str) and new_password and "*" not in new_password:
        current["password"] = new_password

    new_enc = payload.get("encryption_password")
    if new_enc is None:
        pass
    elif new_enc == "" and payload.get("clear_encryption_password"):
        current["encryption_password"] = ""
    elif isinstance(new_enc, str) and new_enc and "*" not in new_enc:
        current["encryption_password"] = new_enc

    # 重置状态字段
    for key in (
        "last_backup_at",
        "last_sync_at",
        "last_error",
        "last_file_size",
        "last_modified",
    ):
        if key not in current:
            current[key] = "" if key != "last_file_size" else 0

    server.settings["webdav_backup"] = current
    server._save_data("settings")
    return get_config(server)


def _resolve_raw_config(server) -> dict[str, Any]:
    """读取未脱敏的配置（仅用于内部调用）。"""
    raw = (server.settings.get("webdav_backup") or {}) if isinstance(server.settings, dict) else {}
    return {
        "enabled": bool(raw.get("enabled")),
        "url": str(raw.get("url") or ""),
        "username": str(raw.get("username") or ""),
        "password": str(raw.get("password") or ""),
        "encryption_password": str(raw.get("encryption_password") or ""),
    }


def _update_status(server, **fields) -> None:
    if not isinstance(server.settings, dict):
        server.settings = {}
    wd = dict(server.settings.get("webdav_backup") or {})
    wd.update(fields)
    server.settings["webdav_backup"] = wd
    server._save_data("settings")


def _ensure_folder_exists(base_url: str, auth, headers) -> dict[str, Any]:
    """确保 nekobot 文件夹存在，不存在则通过 MKCOL 创建。

    返回 {ok, exists, created, message, status_code}。

    注意：某些 WebDAV 服务器（如坚果云）对 PROPFIND 返回 403，
    但 MKCOL/PUT 仍然可用，因此 PROPFIND 403 时不直接判定失败，
    会继续尝试 MKCOL。只有 MKCOL 返回 401/403 才视为真正的权限失败。
    """
    folder_url = _resolve_folder_url(base_url)
    result = {"ok": False, "exists": False, "created": False, "message": "", "status_code": None}

    # 1. 先用 PROPFIND 检查文件夹是否已存在
    try:
        resp = requests.request(
            "PROPFIND",
            folder_url,
            auth=auth,
            headers={**headers, "Depth": "0"},
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
        result["status_code"] = resp.status_code
        if resp.status_code in (207, 200):
            result["ok"] = True
            result["exists"] = True
            result["message"] = f"文件夹 {BACKUP_FOLDER}/ 已存在"
            return result
        if resp.status_code == 401:
            # 401 是明确的认证失败
            result["message"] = "认证失败 (HTTP 401)"
            return result
        # 403 / 404 / 其他状态码都继续尝试 MKCOL
        # （403 可能是因为服务器不允许 PROPFIND，但 MKCOL 仍可能成功）
        _log.debug(f"[WebDAV] PROPFIND 返回 {resp.status_code}, 继续 MKCOL 尝试")
    except requests.exceptions.ConnectionError as exc:
        result["message"] = f"无法连接到 WebDAV 服务器: {exc}"
        return result
    except requests.exceptions.Timeout:
        result["message"] = "连接超时"
        return result
    except Exception as exc:  # noqa: BLE001
        result["message"] = f"检查文件夹失败: {exc}"
        return result

    # 2. 文件夹不存在或 PROPFIND 被拒绝，尝试 MKCOL 创建
    try:
        mkcol_resp = requests.request(
            "MKCOL",
            folder_url,
            auth=auth,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
        result["status_code"] = mkcol_resp.status_code
        if mkcol_resp.status_code in (200, 201):
            result["ok"] = True
            result["exists"] = True
            result["created"] = True
            result["message"] = f"文件夹 {BACKUP_FOLDER}/ 已创建"
            return result
        if mkcol_resp.status_code == 405:
            # Method Not Allowed 通常表示文件夹已存在
            result["ok"] = True
            result["exists"] = True
            result["message"] = f"文件夹 {BACKUP_FOLDER}/ 已存在"
            return result
        if mkcol_resp.status_code == 409:
            result["message"] = "父目录不存在，请检查 WebDAV 根地址是否正确"
            return result
        if mkcol_resp.status_code in (401, 403):
            result["message"] = f"无权限创建文件夹 (HTTP {mkcol_resp.status_code})"
            return result
        result["message"] = f"创建文件夹失败 (HTTP {mkcol_resp.status_code})"
        return result
    except requests.exceptions.ConnectionError as exc:
        result["message"] = f"无法连接到 WebDAV 服务器: {exc}"
        return result
    except requests.exceptions.Timeout:
        result["message"] = "创建文件夹超时"
        return result
    except Exception as exc:  # noqa: BLE001
        result["message"] = f"创建文件夹失败: {exc}"
        return result


def test_connection(server, config_override: dict[str, Any] | None = None) -> dict[str, Any]:
    """测试 WebDAV 连接。

    流程：
      1. 校验根地址格式
      2. 对根地址执行 HEAD 请求，验证连通性（403 不视为失败，因为某些
         WebDAV 服务器不允许 HEAD 根目录，但子路径操作可用）
      3. 检查/创建 nekobot 文件夹
      4. 对 cfg 文件执行 HEAD，检查文件是否存在

    返回 {ok, status_code, exists, message, last_modified, content_length,
          folder_exists, folder_created, resolved_file_url}
    """
    cfg = config_override if config_override is not None else _resolve_raw_config(server)
    base_url = _normalize_base_url(cfg.get("url"))
    file_url = _resolve_file_url(base_url)
    auth = _build_auth(cfg)
    headers = {"User-Agent": "NekoBot-WebDAV/1.0"}

    result = {
        "ok": False,
        "status_code": None,
        "exists": False,
        "message": "",
        "last_modified": "",
        "content_length": 0,
        "folder_exists": False,
        "folder_created": False,
        "resolved_file_url": file_url,
    }

    # 1. 对根地址执行 HEAD 请求验证连通性
    #    某些 WebDAV 服务器（如坚果云）对根目录 HEAD 返回 403，
    #    但子路径仍然可用，因此 403 不直接判定失败，继续后续测试。
    try:
        root_resp = requests.request(
            "HEAD",
            base_url,
            auth=auth,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
        if root_resp.status_code == 401:
            # 401 是明确的认证失败
            result["message"] = "认证失败 (HTTP 401)"
            return result
        # 403 / 200 / 404 都继续后续测试
    except requests.exceptions.ConnectionError as exc:
        result["message"] = f"无法连接到 WebDAV 服务器: {exc}"
        return result
    except requests.exceptions.Timeout:
        result["message"] = "连接超时，请检查地址或网络"
        return result
    except Exception as exc:  # noqa: BLE001
        result["message"] = f"测试失败: {exc}"
        return result

    # 2. 确保 nekobot 文件夹存在
    folder_result = _ensure_folder_exists(base_url, auth, headers)
    result["folder_exists"] = folder_result.get("exists", False)
    result["folder_created"] = folder_result.get("created", False)
    if not folder_result.get("ok"):
        result["message"] = folder_result.get("message") or "文件夹创建失败"
        return result

    # 3. 对 cfg 文件执行 HEAD 请求
    try:
        resp = requests.request(
            "HEAD",
            file_url,
            auth=auth,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
        result["status_code"] = resp.status_code
        if resp.status_code == 200:
            result["exists"] = True
            result["last_modified"] = resp.headers.get("Last-Modified", "")
            try:
                result["content_length"] = int(resp.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                result["content_length"] = 0
            result["message"] = "连接成功，远程配置文件已存在"
            result["ok"] = True
            return result
        if resp.status_code == 404:
            result["message"] = (
                f"连接成功，{BACKUP_FOLDER}/ 文件夹已就绪，配置文件尚未创建（备份后会自动生成）"
            )
            result["ok"] = True
            return result
        if resp.status_code == 401:
            result["message"] = "认证失败 (HTTP 401)"
            return result
        if resp.status_code == 403:
            # 403 可能是因为服务器不允许 HEAD 文件（如坚果云），
            # 但 PUT/GET 可能仍然可用。给出警告但判定为连接 OK。
            result["message"] = (
                "连接可达，但服务器拒绝 HEAD 请求 (HTTP 403)。"
                "备份/同步操作可能仍然可用，建议直接尝试备份。"
            )
            result["ok"] = True
            return result
        result["message"] = f"服务器返回异常状态码: HTTP {resp.status_code}"
        return result
    except requests.exceptions.ConnectionError as exc:
        result["message"] = f"无法连接到 WebDAV 服务器: {exc}"
        return result
    except requests.exceptions.Timeout:
        result["message"] = "连接超时"
        return result
    except Exception as exc:  # noqa: BLE001
        result["message"] = f"测试失败: {exc}"
        return result


def upload_backup(server, password_override: str | None = None) -> dict[str, Any]:
    """构建加密 .nbotcfg 配置包并上传到 WebDAV 服务器。

    password_override 优先于配置中保存的 encryption_password。
    """
    cfg = _resolve_raw_config(server)
    base_url = _normalize_base_url(cfg.get("url"))
    file_url = _resolve_file_url(base_url)
    auth = _build_auth(cfg)
    headers = {"User-Agent": "NekoBot-WebDAV/1.0"}

    enc_password = (password_override or cfg.get("encryption_password") or "").strip()
    if not enc_password:
        raise WebDAVBackupError("未设置加密密码，请先在配置中填写或本次提供")

    # 1. 确保 nekobot 文件夹存在
    folder_result = _ensure_folder_exists(base_url, auth, headers)
    if not folder_result.get("ok"):
        msg = folder_result.get("message") or "文件夹创建失败"
        _update_status(server, last_error=msg)
        raise WebDAVBackupError(msg)

    # 2. 构建加密包
    try:
        encrypted = encrypt_bundle(server, enc_password)
    except ConfigTransferError as exc:
        raise WebDAVBackupError(str(exc)) from exc

    payload_bytes = json.dumps(encrypted, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    payload_size = len(payload_bytes)
    _log.info(f"[WebDAV] 上传备份到 {file_url}, 加密包大小 {payload_size} bytes")

    # 3. PUT 上传
    put_headers = {
        "User-Agent": "NekoBot-WebDAV/1.0",
        "Content-Type": "application/octet-stream",
    }
    try:
        resp = requests.request(
            "PUT",
            file_url,
            auth=auth,
            headers=put_headers,
            data=payload_bytes,
            timeout=DEFAULT_TIMEOUT * 2 if payload_size > LARGE_FILE_THRESHOLD else DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
    except requests.exceptions.ConnectionError as exc:
        _update_status(server, last_error=f"上传失败: {exc}")
        raise WebDAVBackupError(f"无法连接到 WebDAV 服务器: {exc}") from exc
    except requests.exceptions.Timeout:
        _update_status(server, last_error="上传超时")
        raise WebDAVBackupError("上传超时，请检查网络或减小配置体积") from None
    except Exception as exc:  # noqa: BLE001
        _update_status(server, last_error=f"上传失败: {exc}")
        raise WebDAVBackupError(f"上传失败: {exc}") from exc

    if resp.status_code not in (200, 201, 204):
        msg = f"WebDAV 服务器拒绝上传 (HTTP {resp.status_code})"
        _update_status(server, last_error=msg)
        raise WebDAVBackupError(msg)

    now = datetime.now().isoformat()
    last_modified = resp.headers.get("Last-Modified", "")
    _update_status(
        server,
        last_backup_at=now,
        last_error="",
        last_file_size=payload_size,
        last_modified=last_modified,
    )

    # 触发内部日志
    try:
        server.log_message(
            "info",
            f"WebDAV 备份已上传 ({payload_size} bytes)",
            important=False,
        )
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "size": payload_size,
        "uploaded_at": now,
        "status_code": resp.status_code,
        "last_modified": last_modified,
        "file_url": file_url,
    }


def pull_backup(server, password_override: str | None = None) -> dict[str, Any]:
    """从 WebDAV 服务器拉取 .nbotcfg 文件，解密并应用到本地。

    password_override 优先于配置中保存的 encryption_password。
    返回应用结果（imported/skipped 等）。
    """
    cfg = _resolve_raw_config(server)
    base_url = _normalize_base_url(cfg.get("url"))
    file_url = _resolve_file_url(base_url)
    auth = _build_auth(cfg)

    enc_password = (password_override or cfg.get("encryption_password") or "").strip()
    if not enc_password:
        raise WebDAVBackupError("未设置加密密码，请先在配置中填写或本次提供")

    headers = {"User-Agent": "NekoBot-WebDAV/1.0"}
    try:
        resp = requests.request(
            "GET",
            file_url,
            auth=auth,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
    except requests.exceptions.ConnectionError as exc:
        _update_status(server, last_error=f"拉取失败: {exc}")
        raise WebDAVBackupError(f"无法连接到 WebDAV 服务器: {exc}") from exc
    except requests.exceptions.Timeout:
        _update_status(server, last_error="拉取超时")
        raise WebDAVBackupError("拉取超时，请检查网络或 WebDAV 服务器") from None
    except Exception as exc:  # noqa: BLE001
        _update_status(server, last_error=f"拉取失败: {exc}")
        raise WebDAVBackupError(f"拉取失败: {exc}") from exc

    if resp.status_code == 404:
        msg = "远程备份文件不存在，请先执行备份"
        _update_status(server, last_error=msg)
        raise WebDAVBackupError(msg)
    if resp.status_code != 200:
        msg = f"WebDAV 服务器返回异常 (HTTP {resp.status_code})"
        _update_status(server, last_error=msg)
        raise WebDAVBackupError(msg)

    raw_bytes = resp.content
    if not raw_bytes:
        msg = "远程备份文件内容为空"
        _update_status(server, last_error=msg)
        raise WebDAVBackupError(msg)

    # 解析 JSON 配置包
    try:
        raw_bundle = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        msg = f"远程备份文件不是有效的 JSON: {exc}"
        _update_status(server, last_error=msg)
        raise WebDAVBackupError(msg) from exc

    # 解密并应用
    try:
        bundle = decrypt_bundle(raw_bundle, enc_password)
    except ConfigTransferError as exc:
        _update_status(server, last_error=str(exc))
        raise WebDAVBackupError(str(exc)) from exc

    try:
        result = apply_bundle(server, bundle, overwrite=True)
    except ConfigTransferError as exc:
        _update_status(server, last_error=str(exc))
        raise WebDAVBackupError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        _update_status(server, last_error=f"应用配置失败: {exc}")
        raise WebDAVBackupError(f"应用配置失败: {exc}") from exc

    now = datetime.now().isoformat()
    last_modified = resp.headers.get("Last-Modified", "")
    _update_status(
        server,
        last_sync_at=now,
        last_error="",
        last_file_size=len(raw_bytes),
        last_modified=last_modified,
    )

    try:
        server.log_message(
            "info",
            f"WebDAV 同步完成，已导入配置项 {len(result.get('imported', []))} 个",
            important=True,
        )
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "size": len(raw_bytes),
        "synced_at": now,
        "last_modified": last_modified,
        "imported": result.get("imported", []),
        "skipped": result.get("skipped", []),
        "exported_at": result.get("exported_at"),
        "file_url": file_url,
    }


def _parse_propfind_size(resp) -> int:
    """从 PROPFIND 响应中提取 getcontentlength 属性值。

    WebDAV PROPFIND 返回多状态 XML，包含 getcontentlength 等属性。
    某些服务器（如坚果云）HEAD 不返回 Content-Length，但 PROPFIND 会返回。
    """
    try:
        import xml.etree.ElementTree as ET

        text = resp.text or ""
        root = ET.fromstring(text)
        # 查找所有 propstat/prop/getcontentlength
        for prop in root.iter():
            tag = prop.tag
            if tag.endswith("getcontentlength"):
                if prop.text:
                    return int(prop.text.strip())
        return 0
    except Exception:  # noqa: BLE001
        return 0


def _parse_propfind_last_modified(resp) -> str:
    """从 PROPFIND 响应中提取 getlastmodified 属性值。"""
    try:
        import xml.etree.ElementTree as ET

        text = resp.text or ""
        root = ET.fromstring(text)
        for prop in root.iter():
            tag = prop.tag
            if tag.endswith("getlastmodified"):
                if prop.text:
                    return prop.text.strip()
        return ""
    except Exception:  # noqa: BLE001
        return ""


def get_remote_info(server) -> dict[str, Any]:
    """查询远程备份文件的元信息。

    优先用 PROPFIND（可获取真实 Content-Length 和 Last-Modified），
    某些 WebDAV 服务器（如坚果云）HEAD 不返回这些字段。
    PROPFIND 不可用时回退到 HEAD。
    """
    cfg = _resolve_raw_config(server)
    base_url = _normalize_base_url(cfg.get("url"))
    file_url = _resolve_file_url(base_url)
    auth = _build_auth(cfg)
    headers = {"User-Agent": "NekoBot-WebDAV/1.0"}

    info = {
        "ok": False,
        "exists": False,
        "size": 0,
        "last_modified": "",
        "status_code": None,
        "message": "",
        "file_url": file_url,
    }

    # 1. 优先尝试 PROPFIND（更可靠地获取大小）
    try:
        propfind_body = """<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:getcontentlength/>
    <D:getlastmodified/>
    <D:resourcetype/>
  </D:prop>
</D:propfind>"""
        resp = requests.request(
            "PROPFIND",
            file_url,
            auth=auth,
            headers={**headers, "Depth": "0", "Content-Type": "application/xml"},
            data=propfind_body,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
        info["status_code"] = resp.status_code
        if resp.status_code in (207, 200):
            info["ok"] = True
            info["exists"] = True
            info["size"] = _parse_propfind_size(resp)
            info["last_modified"] = _parse_propfind_last_modified(resp)
            if not info["last_modified"]:
                info["last_modified"] = resp.headers.get("Last-Modified", "")
            return info
        if resp.status_code == 404:
            info["ok"] = True
            info["exists"] = False
            info["message"] = "远程备份文件尚未创建"
            return info
        # PROPFIND 失败（如 403），继续尝试 HEAD
        _log.debug(f"[WebDAV] PROPFIND 返回 {resp.status_code}, 回退到 HEAD")
    except requests.exceptions.ConnectionError as exc:
        info["message"] = f"无法连接: {exc}"
        return info
    except requests.exceptions.Timeout:
        info["message"] = "查询超时"
        return info
    except Exception as exc:  # noqa: BLE001
        _log.debug(f"[WebDAV] PROPFIND 异常: {exc}, 回退到 HEAD")

    # 2. 回退到 HEAD 请求
    try:
        resp = requests.request(
            "HEAD",
            file_url,
            auth=auth,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
        info["status_code"] = resp.status_code
        if resp.status_code == 200:
            info["ok"] = True
            info["exists"] = True
            info["last_modified"] = resp.headers.get("Last-Modified", "")
            try:
                info["size"] = int(resp.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                info["size"] = 0
        elif resp.status_code == 404:
            info["ok"] = True
            info["exists"] = False
            info["message"] = "远程备份文件尚未创建"
        elif resp.status_code == 403:
            # HEAD 被拒绝但文件可能存在
            info["ok"] = True
            info["exists"] = True
            info["message"] = "服务器拒绝 HEAD 请求，文件大小未知（备份/同步仍可使用）"
        else:
            info["message"] = f"HTTP {resp.status_code}"
    except requests.exceptions.ConnectionError as exc:
        info["message"] = f"无法连接: {exc}"
    except Exception as exc:  # noqa: BLE001
        info["message"] = f"查询失败: {exc}"

    return info


def host_from_url(url: str) -> str:
    """从 URL 中提取 host，用于显示提示信息。"""
    try:
        parsed = urlparse(url)
        return parsed.hostname or ""
    except Exception:  # noqa: BLE001
        return ""


__all__ = [
    "WebDAVBackupError",
    "BACKUP_FOLDER",
    "BACKUP_FILENAME",
    "get_config",
    "save_config",
    "test_connection",
    "upload_backup",
    "pull_backup",
    "get_remote_info",
    "host_from_url",
]
