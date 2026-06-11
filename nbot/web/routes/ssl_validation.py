# -*- coding: utf-8 -*-
"""SSL 证书文件验证路由

支持用户上传 fileauth.txt 或自定义验证文件，
通过 /.well-known/pki-validation/<filename> 路径对外提供服务，
用于 SSL 证书的文件所有权验证（如 Let's Encrypt、Sectigo 等 CA 的 DCV 流程）。
"""

import json
import logging
import os
import time

from flask import jsonify, request, send_from_directory

_log = logging.getLogger(__name__)

# 存储目录（在 data/web/ssl_validation/ 下）
_SSL_VALIDATION_DIR_NAME = "ssl_validation"
# 元数据文件
_SSL_VALIDATION_META_NAME = "_meta.json"
# 最大文件大小 1MB（CA 验证文件通常很小）
_MAX_FILE_SIZE = 1 * 1024 * 1024


def _get_validation_dir(server) -> str:
    """获取 SSL 验证文件存储目录"""
    base = os.path.join(server.data_dir, "web", _SSL_VALIDATION_DIR_NAME)
    os.makedirs(base, exist_ok=True)
    return base


def _get_meta_path(server) -> str:
    return os.path.join(_get_validation_dir(server), _SSL_VALIDATION_META_NAME)


def _load_meta(server) -> dict:
    meta_path = _get_meta_path(server)
    try:
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_meta(server, meta: dict):
    meta_path = _get_meta_path(server)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def register_ssl_validation_routes(app, server):
    """注册 SSL 证书文件验证路由"""

    # ── 公开访问路由（无需认证）──────────────────────────────────
    # CA 验证服务器会直接访问此路径获取验证文件
    @app.route("/.well-known/pki-validation/<path:filename>")
    def serve_ssl_validation_file(filename):
        """提供 SSL 证书验证文件

        CA（证书颁发机构）在验证域名所有权时会访问：
        http://域名/.well-known/pki-validation/fileauth.txt
        """
        validation_dir = _get_validation_dir(server)
        file_path = os.path.join(validation_dir, filename)

        # 安全检查：防止路径遍历攻击
        real_dir = os.path.realpath(validation_dir)
        real_file = os.path.realpath(file_path)
        if not real_file.startswith(real_dir + os.sep) and real_file != real_dir:
            return "Forbidden", 403

        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return "Not Found", 404

        # 验证文件通常为纯文本，设置正确的 Content-Type
        return send_from_directory(
            validation_dir,
            filename,
            mimetype="text/plain",
            as_attachment=False,
        )

    # ── 管理 API（需要认证）────────────────────────────────────

    @app.route("/api/ssl-validation", methods=["GET"])
    def list_ssl_validation_files():
        """列出所有 SSL 验证文件"""
        try:
            validation_dir = _get_validation_dir(server)
            meta = _load_meta(server)
            files = []

            for f in os.listdir(validation_dir):
                if f.startswith("_"):
                    continue
                fp = os.path.join(validation_dir, f)
                if os.path.isfile(fp):
                    files.append({
                        "filename": f,
                        "original_name": meta.get(f, {}).get("original_name", f),
                        "url": f"/.well-known/pki-validation/{f}",
                        "size": os.path.getsize(fp),
                        "uploaded_at": meta.get(f, {}).get("uploaded_at"),
                    })

            return jsonify({"success": True, "files": files})
        except Exception as e:
            _log.error("[SSL-Validation] 列出文件失败: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/ssl-validation/upload", methods=["POST"])
    def upload_ssl_validation_file():
        """上传 SSL 验证文件

        支持 fileauth.txt 或自定义文件名。
        表单字段：
        - file: 验证文件（必填）
        - custom_filename: 自定义文件名（可选，默认保留原文件名）
        """
        try:
            if "file" not in request.files:
                return jsonify({"success": False, "error": "未提供文件"}), 400

            file = request.files["file"]
            if file.filename == "":
                return jsonify({"success": False, "error": "未选择文件"}), 400

            # 检查文件大小
            file.seek(0, 2)
            file_size = file.tell()
            file.seek(0)

            if file_size > _MAX_FILE_SIZE:
                return jsonify({
                    "success": False,
                    "error": f"文件过大，最大允许 {_MAX_FILE_SIZE // 1024}KB",
                }), 400

            # 确定保存的文件名
            custom_filename = request.form.get("custom_filename", "").strip()
            if custom_filename:
                # 清理自定义文件名，只保留安全字符
                safe_name = "".join(
                    c for c in custom_filename
                    if c.isalnum() or c in ".-_"
                )
                if not safe_name:
                    safe_name = file.filename
            else:
                safe_name = file.filename

            # 确保文件名安全
            safe_name = os.path.basename(safe_name)
            if not safe_name:
                safe_name = "fileauth.txt"

            validation_dir = _get_validation_dir(server)
            file_path = os.path.join(validation_dir, safe_name)

            # 保存文件
            file.save(file_path)

            # 保存元数据
            meta = _load_meta(server)
            meta[safe_name] = {
                "original_name": file.filename,
                "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "size": file_size,
            }
            _save_meta(server, meta)

            # 读取文件内容用于预览
            content = None
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                pass

            server.log_message(
                "info",
                f"SSL 验证文件已上传: {safe_name}",
                important=True,
            )

            try:
                server.record_operation(
                    module="ssl_validation",
                    action="upload",
                    description=f"上传 SSL 验证文件 → {safe_name}",
                    detail=f"原始文件名={file.filename}, 大小={file_size}字节",
                    metadata={"filename": safe_name, "size": file_size},
                )
            except Exception:
                pass

            return jsonify({
                "success": True,
                "filename": safe_name,
                "original_name": file.filename,
                "url": f"/.well-known/pki-validation/{safe_name}",
                "size": file_size,
                "content": content,
            })
        except Exception as e:
            _log.error("[SSL-Validation] 上传失败: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/ssl-validation/<filename>", methods=["DELETE"])
    def delete_ssl_validation_file(filename):
        """删除 SSL 验证文件"""
        try:
            validation_dir = _get_validation_dir(server)
            file_path = os.path.join(validation_dir, filename)

            # 安全检查
            real_dir = os.path.realpath(validation_dir)
            real_file = os.path.realpath(file_path)
            if not real_file.startswith(real_dir + os.sep) and real_file != real_dir:
                return jsonify({"success": False, "error": "禁止访问"}), 403

            if not os.path.exists(file_path):
                return jsonify({"success": False, "error": "文件不存在"}), 404

            os.remove(file_path)

            # 清理元数据
            meta = _load_meta(server)
            if filename in meta:
                del meta[filename]
                _save_meta(server, meta)

            server.log_message("info", f"SSL 验证文件已删除: {filename}")

            return jsonify({"success": True})
        except Exception as e:
            _log.error("[SSL-Validation] 删除失败: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/ssl-validation/content/<filename>", methods=["GET"])
    def get_ssl_validation_content(filename):
        """获取验证文件内容（用于编辑）"""
        try:
            validation_dir = _get_validation_dir(server)
            file_path = os.path.join(validation_dir, filename)

            # 安全检查
            real_dir = os.path.realpath(validation_dir)
            real_file = os.path.realpath(file_path)
            if not real_file.startswith(real_dir + os.sep) and real_file != real_dir:
                return jsonify({"success": False, "error": "禁止访问"}), 403

            if not os.path.exists(file_path):
                return jsonify({"success": False, "error": "文件不存在"}), 404

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            return jsonify({
                "success": True,
                "filename": filename,
                "content": content,
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/ssl-validation/content/<filename>", methods=["PUT"])
    def update_ssl_validation_content(filename):
        """更新验证文件内容"""
        try:
            validation_dir = _get_validation_dir(server)
            file_path = os.path.join(validation_dir, filename)

            # 安全检查
            real_dir = os.path.realpath(validation_dir)
            real_file = os.path.realpath(file_path)
            if not real_file.startswith(real_dir + os.sep) and real_file != real_dir:
                return jsonify({"success": False, "error": "禁止访问"}), 403

            if not os.path.exists(file_path):
                return jsonify({"success": False, "error": "文件不存在"}), 404

            data = request.json or {}
            content = data.get("content", "")

            if len(content.encode("utf-8")) > _MAX_FILE_SIZE:
                return jsonify({
                    "success": False,
                    "error": f"内容过大，最大允许 {_MAX_FILE_SIZE // 1024}KB",
                }), 400

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            # 更新元数据中的大小
            meta = _load_meta(server)
            if filename in meta:
                meta[filename]["size"] = len(content.encode("utf-8"))
                _save_meta(server, meta)

            server.log_message("info", f"SSL 验证文件内容已更新: {filename}")

            return jsonify({"success": True, "filename": filename})
        except Exception as e:
            _log.error("[SSL-Validation] 更新内容失败: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500
