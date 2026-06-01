"""Gateway 统一日志 Web API 路由

提供统一日志查询、trace 聚合、ID 查找等 API：
  GET  /api/gateway/logs                   ← 统一日志查询
  GET  /api/gateway/logs/trace/<trace_id>  ← trace 聚合查询
  GET  /api/gateway/logs/lookup/<value>    ← ID 类型识别
"""

import logging

from flask import Blueprint, jsonify, request

from nbot.gateway.gateway import get_gateway as _get_gateway

_log = logging.getLogger(__name__)

gateway_logs_bp = Blueprint("gateway_logs", __name__)


def _parse_int(value: str, default: int, min_value: int = 0, max_value: int = 500) -> int:
    """安全解析整数，超出范围时返回默认值"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(n, max_value))


@gateway_logs_bp.route("/api/gateway/logs", methods=["GET"])
def query_gateway_logs():
    """查询统一 Gateway 日志

    Query 参数：
        source:    来源筛选 (mcp, gateway, web)
        type:      类型筛选 (mcp_tool, security, delivery, etc.)
        level:     级别筛选 (info, warning, error)
        status:    状态筛选 (success, failed, denied, etc.)
        tool_name: 工具名筛选
        trace_id:  按 trace_id 筛选
        channel_id: 按频道筛选
        limit:     返回条数（默认 100，最大 500）
        offset:    偏移量（默认 0）
    """
    gateway = _get_gateway()
    if gateway is None:
        return jsonify({"ok": False, "error": "Gateway not initialized"}), 503

    if not gateway.log_service:
        return jsonify({"ok": False, "error": "Log service not available"}), 503

    source = request.args.get("source", "")
    type_ = request.args.get("type", "")
    level = request.args.get("level", "")
    status = request.args.get("status", "")
    tool_name = request.args.get("tool_name", "")
    trace_id = request.args.get("trace_id", "")
    channel_id = request.args.get("channel_id", "")
    limit = _parse_int(request.args.get("limit"), default=100, min_value=1, max_value=500)
    offset = _parse_int(request.args.get("offset"), default=0, min_value=0)

    try:
        records = gateway.log_service.query(
            trace_id=trace_id,
            source=source,
            type=type_,
            level=level,
            status=status,
            tool_name=tool_name,
            channel_id=channel_id,
            limit=limit,
            offset=offset,
        )
        return jsonify({
            "ok": True,
            "items": [r.to_dict() for r in records],
            "count": len(records),
            "limit": limit,
            "offset": offset,
        })
    except Exception as e:
        _log.error("[Routes] 查询 Gateway 日志失败 error=%s", str(e))
        return jsonify({"ok": False, "error": str(e)}), 500


@gateway_logs_bp.route("/api/gateway/logs/trace/<trace_id>", methods=["GET"])
def query_gateway_logs_trace(trace_id: str):
    """查询 trace 聚合

    返回 events + deliveries + mcp_logs + timeline。
    """
    gateway = _get_gateway()
    if gateway is None:
        return jsonify({"ok": False, "error": "Gateway not initialized"}), 503

    if not gateway.log_service:
        return jsonify({"ok": False, "error": "Log service not available"}), 503

    try:
        result = gateway.log_service.aggregate_trace(
            trace_id,
            event_store=gateway.event_store,
            delivery_store=gateway.delivery_store_obj,
            queue=gateway.queue,
        )
        return jsonify(result)
    except Exception as e:
        _log.error("[Routes] 查询 trace 聚合失败 trace=%s error=%s", trace_id, str(e))
        return jsonify({"ok": False, "error": str(e)}), 500


@gateway_logs_bp.route("/api/gateway/logs/lookup/<value>", methods=["GET"])
def lookup_gateway_id(value: str):
    """ID 类型识别

    输入任意 ID，返回匹配的类型和建议的下一步操作。
    """
    gateway = _get_gateway()
    if gateway is None:
        return jsonify({"ok": False, "error": "Gateway not initialized"}), 503

    if not gateway.log_service:
        return jsonify({"ok": False, "error": "Log service not available"}), 503

    try:
        result = gateway.log_service.lookup_id(
            value,
            event_store=gateway.event_store,
            delivery_store=gateway.delivery_store_obj,
            queue=gateway.queue,
        )
        return jsonify(result)
    except Exception as e:
        _log.error("[Routes] ID 查找失败 value=%s error=%s", value, str(e))
        return jsonify({"ok": False, "error": str(e)}), 500


def register_gateway_log_routes(app) -> None:
    """注册 Gateway 日志路由"""
    app.register_blueprint(gateway_logs_bp)
    _log.info("[Routes] Gateway 日志路由已注册")
