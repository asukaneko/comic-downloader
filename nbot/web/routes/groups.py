"""群聊管理 API"""

from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, jsonify, request

_log = logging.getLogger(__name__)


def register_group_routes(app, server):
    """注册群聊管理路由"""

    @app.route("/api/groups", methods=["GET"])
    def list_groups():
        from nbot.group.manager import get_group_manager
        gm = get_group_manager()
        groups = gm.list_groups()
        return jsonify({"groups": [g.to_dict() for g in groups]})

    @app.route("/api/groups", methods=["POST"])
    def create_group():
        data = request.get_json(force=True) or {}
        name = data.get("name", "").strip()
        character_ids = data.get("character_ids", [])
        narrator_id = data.get("narrator_id")
        config_data = data.get("config")

        if not name:
            return jsonify({"error": "name is required"}), 400
        if not character_ids:
            return jsonify({"error": "character_ids is required"}), 400

        from nbot.group.manager import get_group_manager
        from nbot.group.models import GroupConfig
        gm = get_group_manager()
        config = GroupConfig.from_dict(config_data) if config_data else None
        group = gm.create_group(name, character_ids, narrator_id=narrator_id, config=config)
        return jsonify({"group": group.to_dict()}), 201

    @app.route("/api/groups/<group_id>", methods=["GET"])
    def get_group(group_id):
        from nbot.group.manager import get_group_manager
        gm = get_group_manager()
        group = gm.get_group(group_id)
        if not group:
            return jsonify({"error": "group not found"}), 404
        return jsonify({"group": group.to_dict()})

    @app.route("/api/groups/<group_id>", methods=["PUT"])
    def update_group(group_id):
        data = request.get_json(force=True) or {}
        from nbot.group.manager import get_group_manager
        gm = get_group_manager()
        group = gm.update_group(group_id, **data)
        if not group:
            return jsonify({"error": "group not found"}), 404
        return jsonify({"group": group.to_dict()})

    @app.route("/api/groups/<group_id>", methods=["DELETE"])
    def delete_group(group_id):
        from nbot.group.manager import get_group_manager
        gm = get_group_manager()
        if not gm.delete_group(group_id):
            return jsonify({"error": "group not found"}), 404
        return jsonify({"ok": True})

    @app.route("/api/groups/<group_id>/characters", methods=["POST"])
    def add_character(group_id):
        data = request.get_json(force=True) or {}
        character_id = data.get("character_id", "").strip()
        if not character_id:
            return jsonify({"error": "character_id is required"}), 400
        from nbot.group.manager import get_group_manager
        gm = get_group_manager()
        if not gm.add_character(group_id, character_id):
            return jsonify({"error": "group not found"}), 404
        return jsonify({"ok": True})

    @app.route("/api/groups/<group_id>/characters/<character_id>", methods=["DELETE"])
    def remove_character(group_id, character_id):
        from nbot.group.manager import get_group_manager
        gm = get_group_manager()
        if not gm.remove_character(group_id, character_id):
            return jsonify({"error": "group not found"}), 404
        return jsonify({"ok": True})

    @app.route("/api/groups/<group_id>/strategy", methods=["PUT"])
    def set_strategy(group_id):
        data = request.get_json(force=True) or {}
        strategy = data.get("strategy", "").strip()
        if not strategy:
            return jsonify({"error": "strategy is required"}), 400
        from nbot.group.manager import get_group_manager
        gm = get_group_manager()
        if not gm.set_speaker_strategy(group_id, strategy):
            return jsonify({"error": "invalid strategy or group not found"}), 400
        return jsonify({"ok": True})

    @app.route("/api/groups/<group_id>/bind", methods=["POST"])
    def bind_channel(group_id):
        data = request.get_json(force=True) or {}
        channel_id = data.get("channel_id", "").strip()
        if not channel_id:
            return jsonify({"error": "channel_id is required"}), 400
        from nbot.group.manager import get_group_manager
        gm = get_group_manager()
        if not gm.bind_channel(group_id, channel_id):
            return jsonify({"error": "group not found"}), 404
        return jsonify({"ok": True})

    @app.route("/api/groups/<group_id>/relations", methods=["GET"])
    def get_relations(group_id):
        from nbot.group.manager import get_group_manager
        gm = get_group_manager()
        group = gm.get_group(group_id)
        if not group:
            return jsonify({"error": "group not found"}), 404
        return jsonify({"relations": group.get_relation_matrix()})

    @app.route("/api/groups/<group_id>/relations", methods=["PUT"])
    def update_relation(group_id):
        data = request.get_json(force=True) or {}
        char_a = data.get("char_a", "").strip()
        char_b = data.get("char_b", "").strip()
        dimension = data.get("dimension", "").strip()
        delta = float(data.get("delta", 0))
        reason = data.get("reason", "")

        if not all([char_a, char_b, dimension]):
            return jsonify({"error": "char_a, char_b, dimension are required"}), 400

        from nbot.group.manager import get_group_manager
        gm = get_group_manager()
        if not gm.update_relation(group_id, char_a, char_b, dimension, delta, reason):
            return jsonify({"error": "group not found"}), 404
        return jsonify({"ok": True})

    _log.info("group routes registered")
