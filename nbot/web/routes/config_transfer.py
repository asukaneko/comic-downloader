import json
from datetime import datetime

from flask import Response, jsonify, request

from nbot.web.config_transfer import (
    ConfigTransferError,
    apply_bundle,
    decrypt_bundle,
    encrypt_bundle,
)


def register_config_transfer_routes(app, server):
    @app.route("/api/config-transfer/export", methods=["POST"])
    def export_config_bundle():
        data = request.json or {}
        password = str(data.get("password") or "").strip()
        try:
            bundle = encrypt_bundle(server, password)
        except ConfigTransferError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

        content = json.dumps(bundle, ensure_ascii=False, indent=2)
        filename = f"nbot-config-{datetime.now().strftime('%Y%m%d-%H%M%S')}.nbotcfg"
        return Response(
            content,
            mimetype="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Config-Encrypted": "true",
            },
        )

    @app.route("/api/config-transfer/import", methods=["POST"])
    def import_config_bundle():
        password = ""
        overwrite = True
        raw_bundle = None

        if request.files:
            upload = request.files.get("file")
            password = str(request.form.get("password") or "").strip()
            overwrite = str(request.form.get("overwrite", "true")).lower() != "false"
            if not upload:
                return jsonify({"success": False, "error": "未选择配置包文件"}), 400
            try:
                raw_bundle = json.loads(upload.read().decode("utf-8"))
            except Exception as exc:
                return jsonify({"success": False, "error": f"配置包 JSON 无效: {exc}"}), 400
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
