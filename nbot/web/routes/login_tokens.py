import logging

from flask import g, jsonify, request

_log = logging.getLogger(__name__)


def register_login_token_routes(app, server):
    """登录令牌管理路由"""

    @app.route("/api/login-tokens", methods=["GET"])
    def list_login_tokens():
        """列出所有活跃的登录令牌"""
        try:
            tokens = []
            for token_hash, info in server.login_tokens.items():
                tokens.append({
                    "token_prefix": info.get("token_prefix", token_hash[:8]),
                    "hash_full": token_hash,
                    "username": info.get("username", ""),
                    "created_at": info.get("created_at", ""),
                    "expires_at": info.get("expires_at", ""),
                    "ip_address": info.get("ip_address", ""),
                })
            # 按创建时间倒序
            tokens.sort(key=lambda t: t.get("created_at", ""), reverse=True)
            return jsonify({"success": True, "tokens": tokens})
        except Exception as e:
            _log.error(f"[LoginTokens] 列出令牌失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/login-tokens", methods=["POST"])
    def create_login_token():
        """创建新的登录令牌"""
        try:
            data = request.get_json(silent=True) or {}
            username = str(data.get("username", "")).strip() or "admin"
            expires_days = int(data.get("expires_days", 30))
            expires_days = max(1, min(expires_days, 365))

            # 临时修改过期天数
            client_ip = request.remote_addr or ""
            original_days = server.token_expire_days
            server.token_expire_days = expires_days
            token = server._generate_login_token(username, ip_address=client_ip)
            server.token_expire_days = original_days

            _log.info(f"[LoginTokens] 手动创建令牌: username={username}, expires_days={expires_days}")
            return jsonify({
                "success": True,
                "token": token,
                "username": username,
                "expires_days": expires_days,
                "message": "请妥善保存此令牌，仅显示一次",
            })
        except Exception as e:
            _log.error(f"[LoginTokens] 创建令牌失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/login-tokens/<token_hash>", methods=["DELETE"])
    def revoke_login_token(token_hash):
        """撤销指定的登录令牌"""
        try:
            if token_hash in server.login_tokens:
                info = server.login_tokens.pop(token_hash)
                server._save_login_tokens()
                _log.info(f"[LoginTokens] 撤销令牌: username={info.get('username')}")
                return jsonify({"success": True, "message": "令牌已撤销"})
            return jsonify({"success": False, "error": "令牌不存在"}), 404
        except Exception as e:
            _log.error(f"[LoginTokens] 撤销令牌失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/login-tokens", methods=["DELETE"])
    def revoke_all_login_tokens():
        """撤销全部登录令牌（保留当前请求所用的令牌）"""
        try:
            current_token = getattr(g, "auth_token", None)
            current_hash = server._hash_token(current_token) if current_token else None

            removed = 0
            hashes_to_remove = []
            for token_hash in server.login_tokens:
                if token_hash != current_hash:
                    hashes_to_remove.append(token_hash)

            for token_hash in hashes_to_remove:
                del server.login_tokens[token_hash]
                removed += 1

            server._save_login_tokens()
            _log.info(f"[LoginTokens] 撤销全部令牌: removed={removed}")
            return jsonify({
                "success": True,
                "message": f"已撤销 {removed} 个令牌",
                "removed": removed,
            })
        except Exception as e:
            _log.error(f"[LoginTokens] 撤销全部令牌失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
