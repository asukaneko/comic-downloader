"""WebDAV 备份/同步相关的 HTTP 路由。"""

from flask import jsonify, request

from nbot.web.webdav_backup import (
    WebDAVBackupError,
    get_config,
    get_remote_info,
    pull_backup,
    save_config,
    test_connection,
    upload_backup,
)


def register_webdav_backup_routes(app, server):
    @app.route("/api/webdav/config")
    def webdav_get_config():
        """读取 WebDAV 备份配置（密码字段会被脱敏）。"""
        return jsonify(get_config(server))

    @app.route("/api/webdav/config", methods=["PUT"])
    def webdav_save_config():
        """保存 WebDAV 备份配置。

        密码字段为空字符串或形如 "ab****cd" 时视为不修改；
        想清空密码时需额外传 clear_password=true / clear_encryption_password=true。
        """
        data = request.json or {}
        try:
            config = save_config(server, data)
        except WebDAVBackupError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        return jsonify({"success": True, "config": config})

    @app.route("/api/webdav/test", methods=["POST"])
    def webdav_test():
        """测试 WebDAV 连接。

        请求体可选:
          - url, username, password: 临时覆盖配置进行测试（不持久化）
        """
        data = request.json or {}
        override = None
        if data.get("url") or data.get("username") or data.get("password"):
            current = (
                server.settings.get("webdav_backup") or {}
                if isinstance(server.settings, dict)
                else {}
            )
            override = {
                "url": str(data.get("url") or current.get("url") or ""),
                "username": str(data.get("username") or current.get("username") or ""),
                "password": str(data.get("password") or current.get("password") or ""),
            }
        try:
            result = test_connection(server, config_override=override)
        except WebDAVBackupError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        return jsonify({"success": True, **result})

    @app.route("/api/webdav/info")
    def webdav_info():
        """查询远程备份文件元信息。"""
        try:
            info = get_remote_info(server)
        except WebDAVBackupError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        return jsonify({"success": True, **info})

    @app.route("/api/webdav/backup", methods=["POST"])
    def webdav_backup():
        """构建加密 .nbotcfg 并上传到 WebDAV 服务器。

        请求体可选:
          - password: 临时加密密码（不持久化），优先于配置中的 encryption_password
          - include_portraits: 是否同时上传立绘文件（默认 false）
        """
        data = request.json or {}
        password_override = str(data.get("password") or "").strip() or None
        include_portraits = bool(data.get("include_portraits"))
        try:
            result = upload_backup(
                server,
                password_override=password_override,
                include_portraits=include_portraits,
            )
        except WebDAVBackupError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        return jsonify({"success": True, **result})

    @app.route("/api/webdav/sync", methods=["POST"])
    def webdav_sync():
        """从 WebDAV 拉取 .nbotcfg 并应用到本地。

        请求体可选:
          - password: 临时加密密码（不持久化），优先于配置中的 encryption_password
          - include_portraits: 是否同时拉取立绘文件（默认 false）
        """
        data = request.json or {}
        password_override = str(data.get("password") or "").strip() or None
        include_portraits = bool(data.get("include_portraits"))
        try:
            result = pull_backup(
                server,
                password_override=password_override,
                include_portraits=include_portraits,
            )
        except WebDAVBackupError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        return jsonify({"success": True, **result})
