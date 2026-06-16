"""
Hook Runtime Web API

Provides CRUD, testing, and log query endpoints for hooks.
Follows the project register_*_routes(app, server) pattern.
"""

import logging
from flask import request, jsonify

_log = logging.getLogger(__name__)


def register_hook_routes(app, server):
    """Register Hook Runtime API routes."""

    def _get_hook_manager():
        from nbot.hooks.manager import get_hook_manager
        data_dir = getattr(server, "data_dir", "data/web")
        return get_hook_manager(data_dir=data_dir)

    # -- Hook CRUD --

    @app.route("/api/hooks", methods=["GET"])
    def list_hooks():
        manager = _get_hook_manager()
        scope = request.args.get("scope", "")
        event = request.args.get("event", "")
        enabled_only = request.args.get("enabled", "").lower() == "true"
        hooks = manager.list_hooks(scope=scope, event=event, enabled_only=enabled_only)
        return jsonify({"hooks": [h.to_dict() for h in hooks], "total": len(hooks)})

    @app.route("/api/hooks", methods=["POST"])
    def create_hook():
        from nbot.hooks.models import ConversationHook
        data = request.get_json(silent=True) or {}
        if not data.get("name") or not data.get("event"):
            return jsonify({"error": "name and event are required"}), 400
        hook = ConversationHook.from_dict(data)
        manager = _get_hook_manager()
        manager.add_hook(hook)
        return jsonify({"hook": hook.to_dict()}), 201

    @app.route("/api/hooks/<hook_id>", methods=["GET"])
    def get_hook(hook_id):
        manager = _get_hook_manager()
        hook = manager.get_hook(hook_id)
        if not hook:
            return jsonify({"error": "Hook not found"}), 404
        return jsonify({"hook": hook.to_dict()})

    @app.route("/api/hooks/<hook_id>", methods=["PUT"])
    def update_hook(hook_id):
        data = request.get_json(silent=True) or {}
        manager = _get_hook_manager()
        if not manager.update_hook(hook_id, **data):
            return jsonify({"error": "Hook not found"}), 404
        hook = manager.get_hook(hook_id)
        return jsonify({"hook": hook.to_dict()})

    @app.route("/api/hooks/<hook_id>", methods=["DELETE"])
    def delete_hook(hook_id):
        manager = _get_hook_manager()
        if not manager.remove_hook(hook_id):
            return jsonify({"error": "Hook not found"}), 404
        return jsonify({"success": True})

    @app.route("/api/hooks/<hook_id>/toggle", methods=["POST"])
    def toggle_hook(hook_id):
        manager = _get_hook_manager()
        hook = manager.get_hook(hook_id)
        if not hook:
            return jsonify({"error": "Hook not found"}), 404
        data = request.get_json(silent=True) or {}
        new_enabled = data.get("enabled", not hook.enabled)
        manager.toggle_hook(hook_id, new_enabled)
        hook = manager.get_hook(hook_id)
        return jsonify({"hook": hook.to_dict()})

    # -- Hook Test --

    @app.route("/api/hooks/test", methods=["POST"])
    async def test_hook():
        from nbot.hooks.models import RuntimeEvent
        data = request.get_json(silent=True) or {}
        event_type = data.get("event_type", "test.ping")
        payload = data.get("payload", {})
        context = data.get("context", {})

        event = RuntimeEvent(
            type=event_type,
            source="api_test",
            conversation_id=data.get("conversation_id", ""),
            character_id=data.get("character_id", ""),
            user_id=data.get("user_id", ""),
            payload=payload,
        )

        manager = _get_hook_manager()
        logs = await manager.emit_event(event, context=context)
        return jsonify({
            "event": event.to_dict(),
            "hooks_triggered": len(logs),
            "logs": [l.to_dict() for l in logs],
        })

    # -- Execution Logs --

    @app.route("/api/hooks/logs", methods=["GET"])
    def get_hook_logs():
        manager = _get_hook_manager()
        hook_id = request.args.get("hook_id", "")
        limit = int(request.args.get("limit", 50))
        logs = manager.get_execution_logs(hook_id=hook_id, limit=limit)
        return jsonify({"logs": logs, "total": len(logs)})

    # -- Event History --

    @app.route("/api/hooks/events", methods=["GET"])
    def get_hook_events():
        manager = _get_hook_manager()
        event_type = request.args.get("event_type", "")
        limit = int(request.args.get("limit", 50))
        events = manager._event_bus.get_history(event_type=event_type, limit=limit)
        return jsonify({"events": events, "total": len(events)})

    # -- Stats --

    @app.route("/api/hooks/stats", methods=["GET"])
    def get_hook_stats():
        manager = _get_hook_manager()
        return jsonify(manager.get_stats())

    _log.info("[Web] Hook routes registered")
