"""MCP Servers 管理 API

提供 MCP 服务器的 CRUD、连接/断开、工具列表等接口。
配置存储在 data/web/mcp_servers.json。

MCP 异步操作通过持久化事件循环执行，避免 asyncio.run() 每次创建新循环
导致异步生成器跨 task 清理失败。
"""

import asyncio
import json
import logging
import os
import threading
import uuid
from concurrent.futures import Future
from datetime import datetime

from flask import jsonify, request

_log = logging.getLogger(__name__)

# ---- 持久化 MCP 事件循环 ----

_mcp_loop: asyncio.AbstractEventLoop | None = None
_mcp_thread: threading.Thread | None = None
_mcp_loop_ready = threading.Event()


def _ensure_mcp_loop() -> asyncio.AbstractEventLoop:
    """确保持久化事件循环已启动，返回该 loop"""
    global _mcp_loop, _mcp_thread
    if _mcp_loop is not None and _mcp_loop.is_running():
        return _mcp_loop

    def _run_loop():
        global _mcp_loop
        _mcp_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_mcp_loop)
        _mcp_loop_ready.set()
        _mcp_loop.run_forever()

    _mcp_thread = threading.Thread(target=_run_loop, name="mcp-event-loop", daemon=True)
    _mcp_thread.start()
    _mcp_loop_ready.wait(timeout=10)
    return _mcp_loop


def _run_async(coro, timeout: float = 60):
    """在持久化 MCP 事件循环中运行异步协程，同步等待结果"""
    loop = _ensure_mcp_loop()
    future: Future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


# ---- 配置读写 ----


def _config_path(server) -> str:
    return os.path.join(server.data_dir, "mcp_servers.json")


def _load_config(server) -> list:
    path = _config_path(server)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_config(server, configs: list):
    path = _config_path(server)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(configs, f, ensure_ascii=False, indent=2)


def register_mcp_server_routes(app, server):
    @app.route("/api/mcp-servers")
    def get_mcp_servers():
        configs = _load_config(server)

        # 补充运行时状态
        try:
            from nbot.services.mcp_bridge import get_mcp_bridge

            bridge = get_mcp_bridge()
            for cfg in configs:
                sid = cfg.get("id", "")
                cfg["connected"] = bridge.is_connected(sid)
                tools = bridge.get_server_tools(sid)
                cfg["tool_count"] = len(tools)
        except Exception:
            pass

        return jsonify(configs)

    @app.route("/api/mcp-servers", methods=["POST"])
    def create_mcp_server():
        data = request.json or {}
        name = data.get("name", "").strip()
        transport = data.get("transport", "streamable-http")

        if not name:
            return jsonify({"error": "name is required"}), 400

        entry = {
            "id": str(uuid.uuid4()),
            "name": name,
            "transport": transport,
            "description": data.get("description", ""),
            "enabled": data.get("enabled", True),
            "auto_connect": data.get("auto_connect", False),
            "connected": False,
            "tool_count": 0,
            "created_at": datetime.now().isoformat(),
            "last_connected_at": None,
        }

        if transport == "stdio":
            entry["command"] = data.get("command", "")
            entry["args"] = data.get("args", [])
            if data.get("env"):
                entry["env"] = data["env"]
            if not entry["command"]:
                return jsonify({"error": "stdio 模式需要 command 参数"}), 400
        else:
            entry["url"] = data.get("url", "")
            if not entry["url"]:
                return jsonify({"error": "HTTP 模式需要 url 参数"}), 400

        configs = _load_config(server)
        configs.append(entry)
        _save_config(server, configs)
        return jsonify({"success": True, "server": entry})

    @app.route("/api/mcp-servers/<server_id>", methods=["PUT"])
    def update_mcp_server(server_id):
        data = request.json or {}
        configs = _load_config(server)
        for cfg in configs:
            if cfg["id"] == server_id:
                cfg["name"] = data.get("name", cfg["name"])
                cfg["url"] = data.get("url", cfg["url"])
                cfg["description"] = data.get("description", cfg.get("description", ""))
                cfg["enabled"] = data.get("enabled", cfg.get("enabled", True))
                cfg["auto_connect"] = data.get("auto_connect", cfg.get("auto_connect", False))
                _save_config(server, configs)
                return jsonify({"success": True, "server": cfg})
        return jsonify({"error": "MCP server not found"}), 404

    @app.route("/api/mcp-servers/<server_id>", methods=["DELETE"])
    def delete_mcp_server(server_id):
        configs = _load_config(server)
        target = next((c for c in configs if c["id"] == server_id), None)
        if not target:
            return jsonify({"error": "MCP server not found"}), 404
        if target.get("_builtin"):
            return jsonify({"error": "Cannot delete built-in MCP server"}), 400
        new_configs = [c for c in configs if c["id"] != server_id]
        _save_config(server, new_configs)

        # 异步断开连接
        try:
            from nbot.services.mcp_bridge import get_mcp_bridge

            bridge = get_mcp_bridge()
            bridge.run_async(bridge.disconnect_server(server_id))
        except Exception:
            pass

        return jsonify({"success": True})

    @app.route("/api/mcp-servers/<server_id>/connect", methods=["POST"])
    def connect_mcp_server(server_id):
        configs = _load_config(server)
        cfg = next((c for c in configs if c["id"] == server_id), None)
        if not cfg:
            return jsonify({"error": "MCP server not found"}), 404

        transport = cfg.get("transport", "streamable-http")
        if transport == "stdio":
            if not cfg.get("command"):
                return jsonify({"error": "stdio 模式需要 command 参数"}), 400
        else:
            if not cfg.get("url"):
                return jsonify({"error": "HTTP 模式需要 url 参数"}), 400

        try:
            from nbot.services.mcp_bridge import get_mcp_bridge

            bridge = get_mcp_bridge()
            result = bridge.run_async(bridge.connect_server(server_id, cfg))

            if result.get("ok"):
                cfg["connected"] = True
                cfg["tool_count"] = result.get("tool_count", 0)
                cfg["last_connected_at"] = datetime.now().isoformat()
                _save_config(server, configs)
                return jsonify({"success": True, "tool_count": cfg["tool_count"]})
            else:
                return jsonify({"error": result.get("error", "Connection failed")}), 500
        except Exception as e:
            _log.error("[MCP API] 连接失败: %s (%s)", e, type(e).__name__, exc_info=True)
            return jsonify({"error": str(e) or type(e).__name__}), 500

    @app.route("/api/mcp-servers/<server_id>/disconnect", methods=["POST"])
    def disconnect_mcp_server(server_id):
        configs = _load_config(server)
        cfg = next((c for c in configs if c["id"] == server_id), None)
        if not cfg:
            return jsonify({"error": "MCP server not found"}), 404

        try:
            from nbot.services.mcp_bridge import get_mcp_bridge

            bridge = get_mcp_bridge()
            bridge.run_async(bridge.disconnect_server(server_id))

            cfg["connected"] = False
            cfg["tool_count"] = 0
            _save_config(server, configs)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/mcp-servers/<server_id>/tools")
    def get_mcp_server_tools(server_id):
        try:
            from nbot.services.mcp_bridge import get_mcp_bridge

            bridge = get_mcp_bridge()
            tools = bridge.get_server_tools(server_id)
            return jsonify({"tools": tools, "count": len(tools)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/mcp-servers/<server_id>/test", methods=["POST"])
    def test_mcp_server(server_id):
        configs = _load_config(server)
        cfg = next((c for c in configs if c["id"] == server_id), None)
        if not cfg:
            return jsonify({"error": "MCP server not found"}), 404

        transport = cfg.get("transport", "streamable-http")
        if transport == "stdio":
            if not cfg.get("command"):
                return jsonify({"error": "stdio 模式需要 command 参数"}), 400
        else:
            if not cfg.get("url"):
                return jsonify({"error": "HTTP 模式需要 url 参数"}), 400

        try:
            from nbot.services.mcp_bridge import get_mcp_bridge

            bridge = get_mcp_bridge()
            temp_id = f"_test_{server_id}"
            result = bridge.run_async(bridge.connect_server(temp_id, cfg))

            if result.get("ok"):
                tools = bridge.get_server_tools(temp_id)
                tool_names = [t["name"] for t in tools]
                bridge.run_async(bridge.disconnect_server(temp_id))
                return jsonify({
                    "success": True,
                    "tool_count": len(tools),
                    "tools": tool_names,
                })
            else:
                return jsonify({"error": result.get("error", "Connection failed")}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500
