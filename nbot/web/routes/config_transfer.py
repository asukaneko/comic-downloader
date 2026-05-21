import json
import zipfile
from datetime import datetime

from flask import Response, jsonify, request, send_file

from nbot.web.config_transfer import (
    ConfigTransferError,
    apply_bundle,
    build_zip_bundle,
    decrypt_bundle,
    extract_zip_bundle,
    restore_portraits_from_zip,
)


def register_config_transfer_routes(app, server):
    @app.route("/api/config-transfer/export", methods=["POST"])
    def export_config_bundle():
        """导出配置为 ZIP 文件（含加密配置 + 角色立绘）"""
        data = request.json or {}
        password = str(data.get("password") or "").strip()
        try:
            zip_buffer = build_zip_bundle(server, password)
        except ConfigTransferError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

        filename = f"nbot-config-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=filename,
        )

    @app.route("/api/config-transfer/import", methods=["POST"])
    def import_config_bundle():
        """导入配置，支持 .nbotcfg（JSON）和 .zip 两种格式"""
        password = ""
        overwrite = True

        if request.files:
            upload = request.files.get("file")
            password = str(request.form.get("password") or "").strip()
            overwrite = str(request.form.get("overwrite", "true")).lower() != "false"
            if not upload:
                return jsonify({"success": False, "error": "未选择配置包文件"}), 400

            raw_bytes = upload.read()
            filename = (upload.filename or "").lower()

            # 判断文件格式并分别处理
            if filename.endswith(".zip"):
                # ZIP 格式：包含配置 + 立绘
                return _handle_zip_import(server, raw_bytes, password, overwrite)
            else:
                # JSON 格式：纯配置（向后兼容旧版 .nbotcfg）
                return _handle_json_import(server, raw_bytes, password, overwrite)
        else:
            data = request.json or {}
            password = str(data.get("password") or "").strip()
            overwrite = bool(data.get("overwrite", True))
            raw_bundle = data.get("bundle")
            try:
                bundle = decrypt_bundle(raw_bundle, password)
                result = apply_bundle(server, bundle, overwrite=overwrite)
                server.log_message(
                    "info",
                    f"已导入配置包，配置项 {len(result['imported'])} 个",
                    important=True,
                )
                return jsonify({"success": True, **result})
            except ConfigTransferError as exc:
                return jsonify({"success": False, "error": str(exc)}), 400
            except Exception as exc:
                return jsonify({"success": False, "error": f"导入失败: {exc}"}), 500


def _handle_json_import(server, raw_bytes: bytes, password: str, overwrite: bool):
    """处理旧版 JSON 格式的配置导入"""
    try:
        raw_bundle = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        return jsonify({"success": False, "error": f"配置包 JSON 无效: {exc}"}), 400

    try:
        bundle = decrypt_bundle(raw_bundle, password)
        result = apply_bundle(server, bundle, overwrite=overwrite)
        server.log_message(
            "info",
            f"已导入配置包 (JSON)，配置项 {len(result['imported'])} 个",
            important=True,
        )
        return jsonify({"success": True, **result})
    except ConfigTransferError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"导入失败: {exc}"}), 500


def _handle_zip_import(server, raw_bytes: bytes, password: str, overwrite: bool):
    """处理 ZIP 格式的配置导入（含立绘恢复）"""
    try:
        bundle, portraits = extract_zip_bundle(raw_bytes, password)
    except ConfigTransferError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except zipfile.BadZipFile:
        return jsonify({"success": False, "error": "ZIP 文件损坏或格式不正确"}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"解析 ZIP 失败: {exc}"}), 400

    # 恢复立绘到本地（会修改 bundle 中的 URL 引用）
    restored_count = 0
    if portraits:
        try:
            restored_count = restore_portraits_from_zip(server, portraits, bundle)
        except Exception as exc:
            server.log_message("warning", f"立绘恢复部分失败: {exc}")

    # 应用配置
    try:
        result = apply_bundle(server, bundle, overwrite=overwrite)
    except ConfigTransferError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"导入失败: {exc}"}), 500

    server.log_message(
        "info",
        f"已导入配置包 (ZIP)，配置项 {len(result['imported'])} 个，立绘 {restored_count} 张",
        important=True,
    )

    resp_data = {"success": True, **result}
    if restored_count > 0:
        resp_data["portraits_restored"] = restored_count
    return jsonify(resp_data)
