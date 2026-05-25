from flask import jsonify, request


def register_config_legacy_routes(app, server):
    @app.route("/api/config")
    def get_config():
        try:
            with open("config.ini", "r", encoding="utf-8") as f:
                content = f.read()
            return jsonify({"content": content})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/config", methods=["POST"])
    def save_config():
        data = request.json or {}
        try:
            with open("config.ini", "w", encoding="utf-8") as f:
                f.write(data.get("content", ""))

            # 记录配置保存操作到 Gateway 日志
            try:
                server.record_operation(
                    module="config",
                    action="update",
                    description="保存系统配置",
                    detail=f"配置文件大小: {len(data.get('content', ''))} 字符",
                )
            except Exception:
                pass

            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
