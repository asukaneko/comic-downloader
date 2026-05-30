import hashlib
import json
import os
import time

from flask import jsonify, request, send_from_directory

from nbot.core import WebSessionStore
from nbot.web.file_gateway import (
    build_file_gateway_urls,
    build_file_metadata,
    register_file_gateway_routes,
)
from nbot.web.sessions_db import get_session as get_session_from_db


def register_file_routes(app, server, workspace_available, workspace_manager):
    register_file_gateway_routes(app, server)

    session_store = WebSessionStore(
        server.sessions, save_callback=lambda: server._save_data("sessions")
    )

    max_file_size = 50 * 1024 * 1024
    preview_text_size_limit = 10 * 1024 * 1024

    @app.route("/static/files/<path:filename>")
    def serve_file(filename):
        files_dir = os.path.join(server.static_folder, "files")
        return send_from_directory(files_dir, filename, as_attachment=True)

    @app.route("/api/files/<path:safe_name>/preview", methods=["GET"])
    def preview_static_file(safe_name):
        from nbot.core.file_parser import FileParser

        files_dir = os.path.join(server.static_folder, "files")
        file_path = os.path.join(files_dir, safe_name)

        if not os.path.exists(file_path):
            return jsonify({"success": False, "error": "File not found"}), 404

        ext = os.path.splitext(safe_name.lower())[1]
        gateway_urls = build_file_gateway_urls(
            server,
            file_path,
            filename=safe_name,
        )
        image_exts = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"]
        if ext in image_exts:
            return jsonify(
                {
                    "success": True,
                    "type": "image",
                    "url": gateway_urls["url"],
                    "download_url": gateway_urls["download_url"],
                    "preview_url": gateway_urls["preview_url"],
                    "safe_name": safe_name,
                }
            )

        frontend_render_exts = [
            ".pdf",
            ".pptx",
            ".ppt",
            ".docx",
            ".doc",
            ".xlsx",
            ".xls",
        ]
        if ext in frontend_render_exts:
            return jsonify(
                {
                    "success": True,
                    "type": ext[1:],
                    "is_blob": True,
                    "url": gateway_urls["url"],
                    "download_url": gateway_urls["download_url"],
                    "preview_url": gateway_urls["preview_url"],
                    "safe_name": safe_name,
                }
            )

        parse_result = FileParser.parse_file(
            file_path,
            safe_name,
            max_chars=preview_text_size_limit,
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
                "filename": safe_name,
                "url": gateway_urls["url"],
                "download_url": gateway_urls["download_url"],
                "preview_url": gateway_urls["preview_url"],
                "safe_name": safe_name,
                "extracted_length": parse_result.get("extracted_length", 0),
                "original_length": parse_result.get("original_length", 0),
                "truncated": parse_result.get("truncated", False),
            }
        )

    @app.route("/static/<path:filename>")
    def serve_static(filename):
        return send_from_directory(server.static_folder, filename)

    @app.route("/api/upload", methods=["POST"])
    def upload_file():
        try:
            if "file" not in request.files:
                return jsonify({"error": "No file provided"}), 400

            file = request.files["file"]
            if file.filename == "":
                return jsonify({"error": "No file selected"}), 400

            file.seek(0, 2)
            file_size = file.tell()
            file.seek(0)

            if file_size > max_file_size:
                return jsonify(
                    {"error": f"File too large, max {max_file_size // (1024 * 1024)}MB"}
                ), 400

            session_id = request.form.get("session_id", "")
            save_to_workspace = False
            file_data = file.read()

            if session_id and workspace_available:
                session_type = "web"
                session = session_store.get_session(session_id)
                if session:
                    session_type = session.get("type", "web")
                else:
                    try:
                        disk_session = get_session_from_db(server.data_dir, session_id)
                        if disk_session:
                            session_type = disk_session.get("type", "web")
                    except Exception as e:
                        server.log_message("warning", f"Load session metadata failed: {e}")

                try:
                    ws_result = workspace_manager.save_uploaded_file(
                        session_id, file_data, file.filename, session_type
                    )
                    if ws_result.get("success"):
                        save_to_workspace = True
                        server.log_message(
                            "info", f"上传文件已保存到工作区: {file.filename}", important=True
                        )
                except Exception as e:
                    server.log_message("error", f"保存文件到工作区失败: {e}", important=True)

            if save_to_workspace:
                content = None
                file_meta = build_file_metadata(
                    server,
                    ws_result.get("path", ""),
                    filename=ws_result.get("filename", file.filename),
                )
                if ws_result.get("mime_type", "").startswith("text/") or any(
                    file.filename.lower().endswith(ext)
                    for ext in [".txt", ".md", ".json", ".xml", ".csv"]
                ):
                    try:
                        ws_file_path = ws_result.get("path", "")
                        if ws_file_path and os.path.exists(ws_file_path):
                            with open(
                                ws_file_path, "r", encoding="utf-8", errors="ignore"
                            ) as f:
                                content = f.read()
                                if (
                                    len(content.encode("utf-8"))
                                    > preview_text_size_limit
                                ):
                                    content = content[:preview_text_size_limit]
                    except Exception as e:
                        server.log_message(
                            "warning", f"Read workspace text preview failed: {e}"
                        )

                # 记录文件上传操作到 Gateway 日志
                try:
                    server.record_operation(
                        module="file",
                        action="upload",
                        description=f"上传文件 → {file.filename}",
                        detail=f"文件大小={file_size}字节, 会话={session_id or '无'}",
                        metadata={"filename": file.filename, "size": file_size, "session_id": session_id},
                    )
                except Exception:
                    pass

                return jsonify(
                    {
                        "success": True,
                        "filename": ws_result.get("filename", file.filename),
                        "path": ws_result.get("path", ""),
                        "url": file_meta["url"],
                        "download_url": file_meta["download_url"],
                        "preview_url": file_meta["preview_url"],
                        "size": ws_result.get("size", file_size),
                        "content": content,
                        "in_workspace": True,
                    }
                )

            import hashlib

            file.seek(0)
            file_ext = os.path.splitext(file.filename)[1]
            unique_name = (
                hashlib.md5(f"{file.filename}{time.time()}".encode()).hexdigest()[:16]
                + file_ext
            )

            upload_dir = os.path.join(server.static_folder, "uploads")
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, unique_name)
            file.save(file_path)
            file_meta = build_file_metadata(server, file_path, filename=file.filename)

            content = None
            try:
                if file_ext.lower() in [".txt", ".md", ".json", ".xml", ".csv"]:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        if len(content.encode("utf-8")) > preview_text_size_limit:
                            content = content[:preview_text_size_limit]
                elif file_ext.lower() in [".docx"]:
                    try:
                        import docx

                        doc = docx.Document(file_path)
                        content = "\n".join([para.text for para in doc.paragraphs])
                        if len(content.encode("utf-8")) > preview_text_size_limit:
                            content = content[:preview_text_size_limit]
                    except ImportError:
                        content = None
            except Exception as e:
                server.log_message("warning", f"Read upload text preview failed: {e}")

            return jsonify(
                {
                    "success": True,
                    "filename": file.filename,
                    "unique_name": unique_name,
                    "path": file_meta["path"],
                    "url": file_meta["url"],
                    "download_url": file_meta["download_url"],
                    "preview_url": file_meta["preview_url"],
                    "size": os.path.getsize(file_path),
                    "content": content,
                    "in_workspace": False,
                }
            )
        except Exception as e:
            server.log_message("error", f"文件上传失败: {e}", important=True)
            return jsonify({"error": str(e)}), 500

    # ── 自定义字体管理 ──────────────────────────────────────────────
    fonts_dir = os.path.join(server.static_folder, "fonts")
    os.makedirs(fonts_dir, exist_ok=True)
    fonts_meta_path = os.path.join(fonts_dir, "_meta.json")
    max_font_size = 15 * 1024 * 1024  # 15MB

    def _load_fonts_meta():
        try:
            if os.path.exists(fonts_meta_path):
                with open(fonts_meta_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_fonts_meta(meta):
        with open(fonts_meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)

    @app.route("/api/fonts/upload", methods=["POST"])
    def upload_font():
        try:
            if "file" not in request.files:
                return jsonify({"error": "No file provided"}), 400
            file = request.files["file"]
            if file.filename == "":
                return jsonify({"error": "No file selected"}), 400

            ext = os.path.splitext(file.filename)[1].lower()
            allowed = [".ttf", ".otf", ".woff", ".woff2"]
            if ext not in allowed:
                return jsonify({"error": "仅支持 TTF、OTF、WOFF、WOFF2 格式"}), 400

            file.seek(0, 2)
            file_size = file.tell()
            file.seek(0)
            if file_size > max_font_size:
                return jsonify({"error": "字体文件大小不能超过15MB"}), 400

            font_name = os.path.splitext(file.filename)[0]
            safe_name = hashlib.md5(f"{font_name}{time.time()}".encode()).hexdigest()[:12]
            saved_name = f"{safe_name}{ext}"
            file_path = os.path.join(fonts_dir, saved_name)
            file.save(file_path)

            # 保存元数据：服务器文件名 → 原始字体名
            meta = _load_fonts_meta()
            meta[saved_name] = font_name
            _save_fonts_meta(meta)

            return jsonify({
                "success": True,
                "name": font_name,
                "filename": saved_name,
                "url": f"/static/fonts/{saved_name}",
                "size": file_size,
            })
        except Exception as e:
            server.log_message("error", f"字体上传失败: {e}", important=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/fonts", methods=["GET"])
    def list_fonts():
        try:
            meta = _load_fonts_meta()
            fonts = []
            if os.path.exists(fonts_dir):
                for f in os.listdir(fonts_dir):
                    if f.startswith("_"):
                        continue
                    fp = os.path.join(fonts_dir, f)
                    if os.path.isfile(fp):
                        ext = os.path.splitext(f)[1].lower()
                        if ext in [".ttf", ".otf", ".woff", ".woff2"]:
                            fonts.append({
                                "name": meta.get(f, os.path.splitext(f)[0]),
                                "filename": f,
                                "url": f"/static/fonts/{f}",
                                "size": os.path.getsize(fp),
                            })
            return jsonify({"success": True, "fonts": fonts})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/fonts/<filename>", methods=["DELETE"])
    def delete_font(filename):
        try:
            file_path = os.path.join(fonts_dir, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
            # 清理元数据
            meta = _load_fonts_meta()
            if filename in meta:
                del meta[filename]
                _save_fonts_meta(meta)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
