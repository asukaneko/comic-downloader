# -*- coding: utf-8 -*-
"""公开会话 API - 生成只读分享链接"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime

from flask import jsonify, render_template, request

from nbot.web.secure_store import read_secure_json, write_secure_json

_log = logging.getLogger(__name__)

# 内存中存储公开会话映射: public_id -> {session_id, created_at, expires_at}
_public_sessions = {}
_public_sessions_loaded = False


def _get_public_sessions_file(data_dir):
    """获取公开会话存储文件路径"""
    return os.path.join(data_dir, "public_sessions.json")


def _load_public_sessions(data_dir):
    """从文件加载公开会话数据"""
    global _public_sessions, _public_sessions_loaded
    if _public_sessions_loaded:
        return

    file_path = _get_public_sessions_file(data_dir)
    if os.path.exists(file_path):
        try:
            data, _ = read_secure_json(file_path, data_dir, {})
            if isinstance(data, dict):
                # 过滤掉已过期的会话
                now = time.time()
                _public_sessions = {
                    k: v for k, v in data.items()
                    if v.get("expires_at", 0) > now
                }
                _log.info("[PublicSession] 已加载 %d 个公开会话", len(_public_sessions))
        except Exception as e:
            _log.error("[PublicSession] 加载公开会话失败: %s", e)
            _public_sessions = {}
    else:
        _public_sessions = {}

    _public_sessions_loaded = True


def _save_public_sessions(data_dir):
    """保存公开会话数据到文件"""
    global _public_sessions
    file_path = _get_public_sessions_file(data_dir)
    try:
        write_secure_json(file_path, data_dir, _public_sessions)
    except Exception as e:
        _log.error("[PublicSession] 保存公开会话失败: %s", e)


def _generate_public_id(session_id):
    """基于会话ID生成固定的公开ID"""
    return hashlib.sha256(f"nbot_public:{session_id}".encode()).hexdigest()[:16]


def _cleanup_expired():
    """清理过期的公开会话"""
    now = time.time()
    expired = [
        pid for pid, info in _public_sessions.items()
        if info.get("expires_at", 0) < now
    ]
    for pid in expired:
        del _public_sessions[pid]
    return len(expired)


def register_public_session_routes(app, server):
    """注册公开会话路由"""

    # 启动时加载公开会话数据
    _load_public_sessions(server.data_dir)

    @app.route("/api/sessions/<session_id>/public", methods=["POST"])
    def make_session_public(session_id):
        """将会话设为公开，生成公开链接"""
        from nbot.core import WebSessionStore
        from nbot.web.persistence import is_web_visible_session
        from nbot.web.sessions_db import get_session as get_session_from_db

        session_store = WebSessionStore(
            server.sessions, save_callback=lambda: server._save_data("sessions")
        )

        session = session_store.get_session(session_id)
        if not session:
            session = get_session_from_db(server.data_dir, session_id)
        if not session or not is_web_visible_session(session_id, session):
            return jsonify({"error": "Session not found"}), 404

        public_id = _generate_public_id(session_id)

        # 提取需要公开的数据（脱敏处理）
        messages = session.get("messages", [])
        public_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                continue
            public_messages.append({
                "id": msg.get("id", ""),
                "role": msg.get("role", ""),
                "content": msg.get("content", ""),
                "timestamp": msg.get("timestamp", ""),
                "sender": msg.get("sender", ""),
            })

        # 存储公开会话数据
        _public_sessions[public_id] = {
            "session_id": session_id,
            "public_id": public_id,
            "created_at": datetime.now().isoformat(),
            "expires_at": time.time() + 30 * 24 * 3600,  # 30天过期
            "session_data": {
                "name": session.get("name", "未命名会话"),
                "sender_name": session.get("sender_name", ""),
                "sender_avatar": session.get("sender_avatar", ""),
                "sender_portrait": session.get("sender_portrait", ""),
                "scenario": session.get("scenario", ""),
                "created_at": session.get("created_at", ""),
                "messages": public_messages,
            }
        }

        # 持久化到文件
        _save_public_sessions(server.data_dir)

        # 构建公开链接
        host_url = request.headers.get("Origin", "")
        if not host_url:
            host_url = request.host_url.rstrip("/")
        public_url = f"{host_url}/public/{public_id}"

        _log.info("[PublicSession] 会话 %s 已公开: %s", session_id[:8], public_id)

        return jsonify({
            "success": True,
            "public_id": public_id,
            "public_url": public_url,
        })

    @app.route("/api/sessions/<session_id>/public", methods=["DELETE"])
    def remove_session_public(session_id):
        """取消会话公开"""
        public_id = _generate_public_id(session_id)
        if public_id in _public_sessions:
            del _public_sessions[public_id]
            # 持久化到文件
            _save_public_sessions(server.data_dir)
            _log.info("[PublicSession] 会话 %s 已取消公开", session_id[:8])
        return jsonify({"success": True})

    @app.route("/api/sessions/<session_id>/public/status", methods=["GET"])
    def get_session_public_status(session_id):
        """获取会话公开状态"""
        public_id = _generate_public_id(session_id)
        is_public = public_id in _public_sessions
        result = {"success": True, "is_public": is_public}
        if is_public:
            info = _public_sessions[public_id]
            host_url = request.headers.get("Origin", "")
            if not host_url:
                host_url = request.host_url.rstrip("/")
            result["public_url"] = f"{host_url}/public/{public_id}"
            result["public_id"] = public_id
        return jsonify(result)

    @app.route("/public/<public_id>")
    def view_public_session(public_id):
        """公开会话只读页面"""
        _cleanup_expired()

        if public_id not in _public_sessions:
            return render_template("public_session.html", error="该公开链接已失效或不存在"), 404

        info = _public_sessions[public_id]
        session_data = info.get("session_data", {})

        return render_template(
            "public_session.html",
            error=None,
            session_name=session_data.get("name", "未命名会话"),
            sender_name=session_data.get("sender_name", ""),
            sender_avatar=session_data.get("sender_avatar", ""),
            sender_portrait=session_data.get("sender_portrait", ""),
            scenario=session_data.get("scenario", ""),
            created_at=session_data.get("created_at", ""),
            messages=session_data.get("messages", []),
        )

    @app.route("/api/public/<public_id>")
    def get_public_session_data(public_id):
        """获取公开会话数据（API）"""
        _cleanup_expired()

        if public_id not in _public_sessions:
            return jsonify({"error": "Public session not found"}), 404

        info = _public_sessions[public_id]
        return jsonify({
            "success": True,
            "session_data": info.get("session_data", {}),
        })
