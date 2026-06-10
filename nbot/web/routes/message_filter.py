"""消息过滤器 Web API 路由"""

import logging

from flask import jsonify, request

_log = logging.getLogger(__name__)


def register_message_filter_routes(app, server):
    """注册消息过滤器相关路由"""

    @app.route("/api/message-filter", methods=["GET"])
    def get_message_filter():
        """获取全部过滤规则"""
        from nbot.message_filter import message_filter

        all_rules = message_filter.list_all_rules()
        return jsonify({
            "enabled": message_filter.enabled,
            "rules": all_rules,
        })

    @app.route("/api/message-filter", methods=["POST"])
    def create_message_filter_rule():
        """添加过滤规则"""
        from nbot.message_filter import MessageFilter, message_filter

        data = request.json or {}
        pattern = (data.get("pattern") or "").strip()
        if not pattern:
            return jsonify({"error": "关键词不能为空"}), 400

        rule_type = data.get("type", "keyword")
        if rule_type not in ("keyword", "regex"):
            return jsonify({"error": "类型必须是 keyword 或 regex"}), 400

        action = data.get("action", "strip")
        if action not in ("strip", "recall"):
            return jsonify({"error": "动作必须是 strip 或 recall"}), 400

        filter_target = data.get("filter_target", "user")
        if filter_target not in ("user", "ai", "both"):
            return jsonify({"error": "过滤目标必须是 user、ai 或 both"}), 400

        channel = MessageFilter.normalize_channel(data.get("channel", "global"))
        session_id = MessageFilter.normalize_session_id(channel, data.get("session_id", ""))
        session_scope = MessageFilter.normalize_session_scope(
            data.get("session_scope", "all"),
            session_id,
        )

        rule = message_filter.add_rule(
            pattern=pattern,
            channel=channel,
            session_scope=session_scope,
            session_id=session_id,
            rule_type=rule_type,
            action=action,
            filter_target=filter_target,
        )
        return jsonify({"success": True, "rule": rule})

    @app.route("/api/message-filter/<rule_id>", methods=["PUT"])
    def update_message_filter_rule(rule_id):
        """更新过滤规则"""
        from nbot.message_filter import MessageFilter, message_filter

        data = request.json or {}

        # 找到规则：需要知道它在哪个 channel 下
        old_channel = MessageFilter.normalize_channel(data.get("_old_channel", "global"))
        old_session_id = MessageFilter.normalize_session_id(
            old_channel,
            data.get("_old_session_id", ""),
        )

        rule = message_filter.find_rule(rule_id, old_channel, old_session_id)
        if not rule:
            return jsonify({"error": "规则不存在"}), 404

        # 更新字段
        if "pattern" in data:
            pattern = (data["pattern"] or "").strip()
            if not pattern:
                return jsonify({"error": "关键词不能为空"}), 400
            rule["pattern"] = pattern
        if "type" in data and data["type"] in ("keyword", "regex"):
            rule["type"] = data["type"]
        if "action" in data and data["action"] in ("strip", "recall"):
            rule["action"] = data["action"]
        if "filter_target" in data and data["filter_target"] in ("user", "ai", "both"):
            rule["filter_target"] = data["filter_target"]
        if "enabled" in data:
            rule["enabled"] = bool(data["enabled"])

        # 如果 channel 或 session_id 变了，需要移动规则
        new_channel = MessageFilter.normalize_channel(data.get("channel", old_channel))
        requested_scope = data.get("session_scope", "all")
        requested_session_id = data.get("session_id", "") if requested_scope == "specific" else ""
        new_session_id = MessageFilter.normalize_session_id(new_channel, requested_session_id)
        new_session_scope = MessageFilter.normalize_session_scope(
            requested_scope,
            new_session_id,
        )

        if new_channel != old_channel or new_session_id != old_session_id:
            message_filter.remove_rule(rule_id, old_channel, old_session_id)
            rule["session_scope"] = new_session_scope
            rule["session_id"] = new_session_id
            message_filter.add_rule_to(new_channel, new_session_scope, new_session_id, rule)

        message_filter._compiled_regex.pop(rule_id, None)
        message_filter.save()
        return jsonify({"success": True, "rule": rule})

    @app.route("/api/message-filter/<rule_id>", methods=["DELETE"])
    def delete_message_filter_rule(rule_id):
        """删除过滤规则"""
        from nbot.message_filter import MessageFilter, message_filter

        channel = MessageFilter.normalize_channel(request.args.get("channel", "global"))
        session_id = MessageFilter.normalize_session_id(channel, request.args.get("session_id", ""))

        removed = message_filter.remove_rule(rule_id, channel, session_id)
        if not removed:
            return jsonify({"error": "规则不存在"}), 404

        return jsonify({"success": True})

    @app.route("/api/message-filter/toggle", methods=["POST"])
    def toggle_message_filter():
        """开关过滤器"""
        from nbot.message_filter import message_filter

        data = request.json or {}
        enabled = data.get("enabled")
        if enabled is None:
            enabled = not message_filter.enabled

        message_filter.set_enabled(bool(enabled))
        return jsonify({"success": True, "enabled": message_filter.enabled})
