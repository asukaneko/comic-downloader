"""
Review Pipeline Web API

提供 Review 结果查询、MemoryFS 路径浏览等接口。

路由：
    GET  /api/review/logs               — 查询 Review 事件历史
    GET  /api/review/memory-fs          — 查询 MemoryFS 逻辑文件列表
    GET  /api/review/memory-fs/<path>   — 读取指定路径的逻辑文件
    GET  /api/review/event-stream       — 查询标准化事件流
    POST /api/review/run                — 手动触发一次 Review（调试用）
"""

import logging

from flask import jsonify, request

_log = logging.getLogger(__name__)


def _get_event_bus(server):
    """获取 event_bus，优先从 server.hook_runtime 读取，fallback 到全局 HookManager。"""
    hook_runtime = getattr(server, "hook_runtime", None)
    if hook_runtime:
        bus = getattr(hook_runtime, "_event_bus", None)
        if bus:
            return bus
    # fallback: 从全局 HookManager 获取
    try:
        data_dir = getattr(server, "data_dir", "data/web")
        from nbot.hooks.manager import get_hook_manager
        hm = get_hook_manager(data_dir=data_dir)
        return getattr(hm, "_event_bus", None)
    except Exception:
        return None


def _short_id(value, *, length=8):
    value = str(value or "").strip()
    if not value:
        return ""
    return value[-length:] if len(value) > length else value


def _get_session(server, conversation_id):
    sessions = getattr(server, "sessions", {}) or {}
    if not isinstance(sessions, dict):
        return {}
    session = sessions.get(conversation_id)
    return session if isinstance(session, dict) else {}


def _session_display_name(session, conversation_id):
    for key in ("name", "title", "display_name"):
        value = str((session or {}).get(key) or "").strip()
        if value:
            return value
    return f"会话 {_short_id(conversation_id)}" if conversation_id else ""


def _character_display_name(session, event):
    for key in ("sender_name", "character_name", "character_id"):
        value = str((session or {}).get(key) or "").strip()
        if value:
            return value
    return str((event or {}).get("character_id") or "").strip()


def _enrich_event_for_display(server, event):
    enriched = dict(event or {})
    conversation_id = enriched.get("conversation_id", "")
    session = _get_session(server, conversation_id)
    conversation_name = _session_display_name(session, conversation_id)
    character_name = _character_display_name(session, enriched)

    enriched["conversation_name"] = conversation_name
    enriched["conversation_label"] = conversation_name or _short_id(conversation_id)
    enriched["conversation_short_id"] = _short_id(conversation_id)
    enriched["character_label"] = character_name
    enriched["source_label"] = str(enriched.get("source") or "").strip()
    return enriched


def register_review_routes(app, server):

    # ------------------------------------------------------------------
    # Review 事件历史（来自 Hook event bus 历史）
    # ------------------------------------------------------------------

    @app.route("/api/review/logs")
    def get_review_logs():
        """查询 review.started / review.finished 事件历史。"""
        limit = int(request.args.get("limit", 50))
        conversation_id = request.args.get("conversation_id", "")

        try:
            bus = _get_event_bus(server)
            if not bus:
                return jsonify({"logs": [], "total": 0})

            history = bus.get_history(limit=200)
            review_events = [
                e for e in history
                if e.get("type", "").startswith("review.")
                and (not conversation_id or e.get("conversation_id") == conversation_id)
            ]
            logs = [_enrich_event_for_display(server, e) for e in review_events[-limit:]]
            return jsonify({"logs": logs, "total": len(review_events)})
        except Exception as exc:
            _log.error("[ReviewRoutes] get_review_logs failed: %s", exc)
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # MemoryFS 路径浏览
    # ------------------------------------------------------------------

    @app.route("/api/review/memory-fs")
    def list_memory_fs():
        """列出指定角色的所有 MemoryFS 逻辑文件。"""
        character_id = request.args.get("character_id", "")
        try:
            from nbot.memory.fs import describe_memory_path, get_memory_fs
            mfs = get_memory_fs()
            if character_id:
                files = mfs.list_for_character(character_id)
            else:
                files = list(mfs._index.values())
            items = []
            for mf in files:
                item = mf.to_dict()
                item.update(describe_memory_path(mf.path))
                items.append(item)
            items.sort(key=lambda item: (
                item.get("category_order", 99),
                -float(item.get("importance") or 0),
                item.get("path", ""),
            ))
            return jsonify({
                "files": items,
                "total": len(files),
            })
        except Exception as exc:
            _log.error("[ReviewRoutes] list_memory_fs failed: %s", exc)
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/review/memory-fs/read")
    def read_memory_fs():
        """读取指定逻辑路径的 MemoryFile。"""
        path = request.args.get("path", "")
        if not path:
            return jsonify({"error": "path is required"}), 400
        try:
            from nbot.memory.fs import get_memory_fs
            mfs = get_memory_fs()
            mf = mfs.read(path)
            if mf is None:
                return jsonify({"error": "not found"}), 404
            return jsonify(mf.to_dict())
        except Exception as exc:
            _log.error("[ReviewRoutes] read_memory_fs failed: %s", exc)
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # Hook 事件流（按新标准事件名筛选）
    # ------------------------------------------------------------------

    @app.route("/api/review/event-stream")
    def get_event_stream():
        """查询 Hook 事件流，支持按新标准事件域筛选。

        参数：
            domain   — 事件域前缀，如 character / plot / group / review
            limit    — 最大返回数量（默认 100）
            conversation_id — 按会话过滤
        """
        domain = request.args.get("domain", "")
        limit = int(request.args.get("limit", 100))
        conversation_id = request.args.get("conversation_id", "")

        try:
            bus = _get_event_bus(server)
            if not bus:
                return jsonify({"events": [], "total": 0})

            history = bus.get_history(limit=500)
            filtered = [
                e for e in history
                if (not domain or e.get("type", "").startswith(domain + "."))
                and (not conversation_id or e.get("conversation_id") == conversation_id)
            ]
            events = [_enrich_event_for_display(server, e) for e in filtered[-limit:]]
            return jsonify({"events": events, "total": len(filtered)})
        except Exception as exc:
            _log.error("[ReviewRoutes] get_event_stream failed: %s", exc)
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # 手动触发 Review（调试用）
    # ------------------------------------------------------------------

    @app.route("/api/review/run", methods=["POST"])
    def run_review():
        """手动触发一次规则版 Review，返回结构化输出。"""
        data = request.json or {}
        try:
            from nbot.review.models import ReviewInput
            from nbot.review.pipeline import ReviewPipeline

            inp = ReviewInput(
                conversation_id=data.get("conversation_id", ""),
                character_id=data.get("character_id", ""),
                user_id=data.get("user_id", ""),
                user_message=data.get("user_message", ""),
                assistant_message=data.get("assistant_message", ""),
                selected_choice=data.get("selected_choice"),
                relationship_state=data.get("relationship_state", {}),
            )
            pipeline = ReviewPipeline()
            output = pipeline.run(inp)
            return jsonify(output.to_dict())
        except Exception as exc:
            _log.error("[ReviewRoutes] run_review failed: %s", exc)
            return jsonify({"error": str(exc)}), 500
