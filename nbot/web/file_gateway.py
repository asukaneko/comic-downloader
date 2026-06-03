"""Signed file delivery helpers for Web, QQ, and other channels."""

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import time
from typing import Any, Dict, Iterable, Optional

from flask import jsonify, request, send_file


DEFAULT_EXPIRES_IN = 24 * 60 * 60


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _safe_commonpath(root: str, candidate: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(root), os.path.abspath(candidate)]) == os.path.abspath(root)
    except (OSError, ValueError):
        return False


def _get_secret(server) -> bytes:
    env_secret = os.getenv("NBOT_FILE_GATEWAY_SECRET")
    if env_secret:
        return env_secret.encode("utf-8")

    data_dir = os.path.abspath(getattr(server, "data_dir", "") or os.path.join("data", "web"))
    os.makedirs(data_dir, exist_ok=True)
    secret_file = os.path.join(data_dir, "file_gateway_secret.txt")
    try:
        if os.path.exists(secret_file):
            with open(secret_file, "r", encoding="utf-8") as f:
                secret = f.read().strip()
                if secret:
                    return secret.encode("utf-8")
        secret = secrets.token_urlsafe(48)
        with open(secret_file, "w", encoding="utf-8") as f:
            f.write(secret)
        return secret.encode("utf-8")
    except Exception:
        return str(getattr(server.app, "secret_key", "") or "nbot-file-gateway").encode("utf-8")


def _allowed_roots(server) -> Iterable[str]:
    base_dir = os.path.abspath(getattr(server, "base_dir", "") or os.getcwd())
    static_folder = os.path.abspath(getattr(server, "static_folder", "") or "")

    roots = [
        os.path.join(base_dir, "data", "workspaces"),
        os.path.join(base_dir, "data", "workspace"),
        os.path.join(base_dir, "data", "web"),
        os.path.join(base_dir, "data", "cache"),
        os.path.join(base_dir, "cache"),
        os.path.join(base_dir, "nbot", "cache"),
    ]
    if static_folder:
        roots.extend(
            [
                os.path.join(static_folder, "files"),
                os.path.join(static_folder, "uploads"),
            ]
        )

    workspace_manager = getattr(server, "workspace_manager", None)
    for attr in ("workspaces_dir", "shared_workspace_dir"):
        value = getattr(workspace_manager, attr, None)
        if value:
            roots.append(value)

    seen = set()
    for root in roots:
        if not root:
            continue
        abs_root = os.path.abspath(root)
        if abs_root in seen:
            continue
        seen.add(abs_root)
        yield abs_root


def is_allowed_file_path(server, file_path: str) -> bool:
    candidate = os.path.abspath(file_path or "")
    return bool(candidate) and any(_safe_commonpath(root, candidate) for root in _allowed_roots(server))


def sign_file_token(
    server,
    file_path: str,
    *,
    filename: Optional[str] = None,
    expires_in: int = DEFAULT_EXPIRES_IN,
) -> str:
    abs_path = os.path.abspath(file_path)
    if not is_allowed_file_path(server, abs_path):
        raise ValueError("File path is outside allowed roots")

    payload = {
        "path": abs_path,
        "filename": filename or os.path.basename(abs_path),
        "exp": int(time.time()) + max(60, int(expires_in or DEFAULT_EXPIRES_IN)),
    }
    payload_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64_encode(payload_bytes)
    signature = hmac.new(_get_secret(server), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_b64}.{_b64_encode(signature)}"


def verify_file_token(server, token: str) -> Dict[str, Any]:
    if not token or "." not in token:
        raise ValueError("Invalid file token")
    payload_b64, sig_b64 = token.split(".", 1)
    expected = hmac.new(_get_secret(server), payload_b64.encode("ascii"), hashlib.sha256).digest()
    provided = _b64_decode(sig_b64)
    if not hmac.compare_digest(expected, provided):
        raise ValueError("Invalid file token signature")

    payload = json.loads(_b64_decode(payload_b64).decode("utf-8"))
    if int(payload.get("exp") or 0) < int(time.time()):
        raise ValueError("File token expired")

    file_path = os.path.abspath(str(payload.get("path") or ""))
    if not is_allowed_file_path(server, file_path):
        raise ValueError("File path is outside allowed roots")
    if not os.path.isfile(file_path):
        raise FileNotFoundError("File not found")

    payload["path"] = file_path
    payload["filename"] = payload.get("filename") or os.path.basename(file_path)
    return payload


def get_public_base_url(server) -> str:
    configured = (
        os.getenv("NBOT_PUBLIC_BASE_URL")
        or os.getenv("WEB_PUBLIC_BASE_URL")
        or str((getattr(server, "settings", {}) or {}).get("public_base_url") or "")
    ).strip()
    if configured:
        return configured.rstrip("/")

    try:
        origin = request.headers.get("Origin", "")
        if origin:
            return origin.rstrip("/")
        return request.host_url.rstrip("/")
    except RuntimeError:
        return ""


def _with_base(url: str, base_url: str) -> str:
    if not base_url:
        return url
    return f"{base_url.rstrip('/')}{url}"


def build_file_gateway_urls(
    server,
    file_path: str,
    *,
    filename: Optional[str] = None,
    expires_in: int = DEFAULT_EXPIRES_IN,
    absolute: bool = False,
) -> Dict[str, Any]:
    token = sign_file_token(server, file_path, filename=filename, expires_in=expires_in)
    relative_download = f"/api/files/gateway/{token}"
    relative_inline = f"{relative_download}?inline=1"
    relative_preview = f"/api/files/gateway/{token}/preview"
    base_url = get_public_base_url(server) if absolute else ""
    expires_at = int(time.time()) + max(60, int(expires_in or DEFAULT_EXPIRES_IN))
    return {
        "token": token,
        "expires_in": max(60, int(expires_in or DEFAULT_EXPIRES_IN)),
        "expires_at": expires_at,
        "url": _with_base(relative_inline, base_url),
        "download_url": _with_base(relative_download, base_url),
        "preview_url": _with_base(relative_preview, base_url),
        "relative_url": relative_inline,
        "relative_download_url": relative_download,
        "relative_preview_url": relative_preview,
    }


def build_file_metadata(
    server,
    file_path: str,
    *,
    filename: Optional[str] = None,
    expires_in: int = DEFAULT_EXPIRES_IN,
    absolute: bool = False,
) -> Dict[str, Any]:
    abs_path = os.path.abspath(file_path)
    name = filename or os.path.basename(abs_path)
    mime_type, _ = mimetypes.guess_type(abs_path)
    mime_type = mime_type or "application/octet-stream"
    ext = os.path.splitext(name)[1].lower()
    size = os.path.getsize(abs_path)
    urls = build_file_gateway_urls(
        server,
        abs_path,
        filename=name,
        expires_in=expires_in,
        absolute=absolute,
    )
    return {
        "name": name,
        "type": mime_type,
        "size": size,
        "is_image": mime_type.startswith("image/"),
        "is_text": mime_type.startswith("text/") or mime_type in {
            "application/json",
            "application/xml",
            "application/yaml",
        },
        "is_video": mime_type.startswith("video/"),
        "is_audio": mime_type.startswith("audio/"),
        "extension": ext,
        "path": abs_path,
        "url": urls["url"],
        "download_url": urls["download_url"],
        "preview_url": urls["preview_url"],
        "relative_url": urls["relative_url"],
        "relative_download_url": urls["relative_download_url"],
        "relative_preview_url": urls["relative_preview_url"],
        "gateway_token": urls["token"],
        "expires_at": urls["expires_at"],
        "expires_in": urls["expires_in"],
    }


def register_file_gateway_routes(app, server):
    @app.route("/api/files/gateway/<token>", methods=["GET"])
    def serve_gateway_file(token):
        try:
            payload = verify_file_token(server, token)
            file_path = payload["path"]
            filename = payload["filename"]
            # TOCTOU 防护：在 send_file 前再次确认文件存在
            if not os.path.isfile(file_path):
                return jsonify({"success": False, "error": "File not found"}), 404
            mime_type, _ = mimetypes.guess_type(file_path)
            inline = request.args.get("inline") in {"1", "true", "yes"}
            return send_file(
                file_path,
                mimetype=mime_type,
                as_attachment=not inline,
                download_name=os.path.basename(filename),
            )
        except FileNotFoundError:
            return jsonify({"success": False, "error": "File not found"}), 404
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 403
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/files/gateway/<token>/preview", methods=["GET"])
    def preview_gateway_file(token):
        try:
            payload = verify_file_token(server, token)
            file_path = payload["path"]
            filename = payload["filename"]
            metadata = build_file_metadata(server, file_path, filename=filename)

            ext = os.path.splitext(filename.lower())[1]
            image_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"}
            frontend_render_exts = {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".xls"}
            if ext in image_exts:
                return jsonify(
                    {
                        "success": True,
                        "type": "image",
                        "url": metadata["url"],
                        "download_url": metadata["download_url"],
                        "preview_url": metadata["preview_url"],
                        "safe_name": filename,
                    }
                )
            if ext in frontend_render_exts:
                return jsonify(
                    {
                        "success": True,
                        "type": ext[1:],
                        "is_blob": True,
                        "url": metadata["url"],
                        "download_url": metadata["download_url"],
                        "preview_url": metadata["preview_url"],
                        "safe_name": filename,
                    }
                )

            from nbot.core.file_parser import FileParser

            parse_result = FileParser.parse_file(
                file_path,
                filename,
                max_chars=10 * 1024 * 1024,
            )
            if not parse_result or not parse_result.get("success"):
                return jsonify(
                    {
                        "success": False,
                        "error": parse_result.get("error", "Failed to parse file")
                        if parse_result
                        else "File not found",
                    }
                ), 400

            return jsonify(
                {
                    "success": True,
                    "type": parse_result.get("type", "text"),
                    "content": parse_result.get("content", ""),
                    "filename": filename,
                    "url": metadata["url"],
                    "download_url": metadata["download_url"],
                    "preview_url": metadata["preview_url"],
                    "safe_name": filename,
                    "extracted_length": parse_result.get("extracted_length", 0),
                    "original_length": parse_result.get("original_length", 0),
                    "truncated": parse_result.get("truncated", False),
                }
            )
        except FileNotFoundError:
            return jsonify({"success": False, "error": "File not found"}), 404
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 403
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 500
