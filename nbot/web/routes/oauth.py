"""OAuth Flask 路由模块。

路由清单：
- GET  /api/oauth/providers                 列出所有支持的 OAuth provider spec
- GET  /api/oauth/accounts                  列出已登录账号（不返回 encrypted_credentials）
- POST /api/oauth/login                     启动登录
- POST /api/oauth/poll                      轮询登录
- POST /api/oauth/anthropic-code            Anthropic PKCE 提交授权码
- POST /api/oauth/qwen-import               导入 Qwen 凭证
- POST /api/oauth/api-key                   OpenCode API Key 登录
- GET  /api/oauth/accounts/<id>/models      获取该账号已缓存模型 + 已选模型
- POST /api/oauth/accounts/<id>/models      拉取/刷新远端模型列表
- PUT  /api/oauth/accounts/<id>/models      同步选中模型
- DELETE /api/oauth/accounts/<id>           删除账号 + 关联 ai_models
"""

from __future__ import annotations

from flask import jsonify, request

from nbot.core.oauth import (
    LocalOAuthProviders,
    OAuthLoginSession,
    OAuthManager,
)
from nbot.core.oauth.models import (
    OAuthPollConnected,
    OAuthPollFailed,
    OAuthPollPending,
)


def register_oauth_routes(app, server):
    """注册 OAuth 相关 Flask 路由"""

    def _get_manager() -> OAuthManager:
        return server.oauth_manager

    @app.route("/api/oauth/providers", methods=["GET"])
    def list_oauth_providers():
        try:
            specs = [spec.to_dict() for spec in LocalOAuthProviders.all]
            return jsonify({"success": True, "providers": specs})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/oauth/accounts", methods=["GET"])
    def list_oauth_accounts():
        try:
            manager = _get_manager()
            accounts = manager.list_accounts()
            # 脱敏：不返回 encrypted_credentials
            safe = []
            for acc in accounts:
                d = acc.to_dict()
                d.pop("encrypted_credentials", None)
                safe.append(d)
            return jsonify({"success": True, "accounts": safe})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/oauth/login", methods=["POST"])
    def oauth_login():
        try:
            data = request.json or {}
            provider = (data.get("provider") or "").strip()
            if not provider:
                return jsonify({"error": "provider is required"}), 400
            manager = _get_manager()
            session = manager.start_login(provider)
            return jsonify({"success": True, "session": session.to_dict()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/oauth/poll", methods=["POST"])
    def oauth_poll():
        try:
            data = request.json or {}
            session_data = data.get("session") or {}
            if not session_data:
                return jsonify({"error": "session is required"}), 400
            session = OAuthLoginSession.from_dict(session_data)
            manager = _get_manager()
            result = manager.poll_login(session)
            return jsonify({"success": True, "result": result.to_dict()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/oauth/anthropic-code", methods=["POST"])
    def oauth_anthropic_code():
        try:
            data = request.json or {}
            session_data = data.get("session") or {}
            code_input = data.get("code_input") or data.get("code") or ""
            if not session_data:
                return jsonify({"error": "session is required"}), 400
            session = OAuthLoginSession.from_dict(session_data)
            manager = _get_manager()
            result = manager.submit_anthropic_code(session, code_input)
            return jsonify({"success": True, "result": result.to_dict()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/oauth/qwen-import", methods=["POST"])
    def oauth_qwen_import():
        try:
            data = request.json or {}
            raw_json = data.get("raw_json") or ""
            if not raw_json:
                return jsonify({"error": "raw_json is required"}), 400
            manager = _get_manager()
            result = manager.import_qwen_credentials(raw_json)
            return jsonify({"success": True, "result": result.to_dict()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/oauth/api-key", methods=["POST"])
    def oauth_api_key():
        try:
            data = request.json or {}
            provider = (data.get("provider") or "").strip()
            api_key = data.get("api_key") or ""
            if not provider:
                return jsonify({"error": "provider is required"}), 400
            manager = _get_manager()
            result = manager.import_api_key(provider, api_key)
            return jsonify({"success": True, "result": result.to_dict()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/oauth/accounts/<account_id>/models", methods=["GET"])
    def get_oauth_account_models(account_id):
        try:
            manager = _get_manager()
            available = manager.available_models(account_id, refresh=False)
            selected = manager.selected_models(account_id, server.ai_models)
            return jsonify({
                "success": True,
                "available": available,
                "selected": selected,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/oauth/accounts/<account_id>/models", methods=["POST"])
    def refresh_oauth_account_models(account_id):
        try:
            data = request.json or {}
            refresh = bool(data.get("refresh", False))
            manager = _get_manager()
            available = manager.available_models(account_id, refresh=refresh)
            return jsonify({"success": True, "available": available})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/oauth/accounts/<account_id>/models", methods=["PUT"])
    def sync_oauth_account_models(account_id):
        try:
            data = request.json or {}
            selected = data.get("selected") or []
            if not isinstance(selected, list):
                return jsonify({"error": "selected must be a list"}), 400
            manager = _get_manager()
            server.ai_models = manager.sync_selected_models(
                account_id, selected, server.ai_models
            )
            server._save_data("ai_models")
            return jsonify({
                "success": True,
                "selected": manager.selected_models(account_id, server.ai_models),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/oauth/accounts/<account_id>", methods=["DELETE"])
    def delete_oauth_account(account_id):
        try:
            manager = _get_manager()
            server.ai_models = manager.delete_account(account_id, server.ai_models)
            server._save_data("ai_models")
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
