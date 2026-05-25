"""Gateway Webhook API 路由

提供统一的 Webhook 入口和管理端点：
  POST   /api/gateway/<channel_id>/webhook    ← 统一事件入口
  GET    /api/gateway/health                   ← 健康检查
  GET    /api/gateway/stats                    ← 运行统计
  GET    /api/gateway/queue/status             ← 队列状态
  POST   /api/gateway/worker/start             ← 启动 Worker
  POST   /api/gateway/worker/stop              ← 停止 Worker

异步模式下，Webhook 快速返回 200（queued），Worker 后台处理。
同步模式下，Webhook 等待 AI 完成后返回（delivered）。
"""

import logging

from flask import jsonify, request

from nbot.gateway.gateway import get_gateway as _get_core_gateway
from nbot.gateway.gateway import set_gateway as _set_core_gateway

_log = logging.getLogger(__name__)


def get_gateway():
    """获取全局 Gateway 实例（委托到 gateway 核心模块）"""
    return _get_core_gateway()


def set_gateway(gateway) -> None:
    """设置全局 Gateway 实例（委托到 gateway 核心模块）"""
    _set_core_gateway(gateway)


def register_gateway_routes(app):
    """注册 Gateway Webhook 路由

    Args:
        app: Flask 应用实例
    """

    @app.route("/api/gateway/<channel_id>/webhook", methods=["POST"])
    async def gateway_webhook(channel_id: str):
        """统一 Webhook 入口

        请求头建议：
            X-NekoBot-Timestamp: Unix 时间戳
            X-NekoBot-Nonce:     随机字符串
            X-NekoBot-Signature: HMAC-SHA256 签名
            X-NekoBot-Token:     静态 Token（可选）

        返回格式：
            同步-成功：{"ok": true, "trace_id": "...", "status": "delivered"}
            同步-重复：{"ok": true, "trace_id": "...", "status": "duplicated", "duplicated": true}
            异步-入队：{"ok": true, "trace_id": "...", "status": "queued", "queued": true}
            错误：     {"ok": false, "trace_id": "...", "status": "error_code", "error": "..."}
        """
        gateway = get_gateway()

        headers = dict(request.headers)
        remote_addr = request.remote_addr or ""

        # 解析请求体
        content_type = request.content_type or ""
        if "application/json" in content_type:
            raw_event = request.get_json(silent=True) or {}
        elif "application/x-www-form-urlencoded" in content_type:
            raw_event = request.form.to_dict()
        else:
            raw_event = request.get_json(force=True, silent=True) or {}

        _log.info(
            "[Webhook] 收到请求 channel=%s addr=%s content_type=%s",
            channel_id,
            remote_addr,
            content_type,
        )

        try:
            result = await gateway.receive(
                channel_id=channel_id,
                raw_event=raw_event,
                headers=headers,
                remote_addr=remote_addr,
            )
            return jsonify(result.to_dict())
        except Exception as e:
            _log.error(
                "[Webhook] 未处理的异常 channel=%s error=%s",
                channel_id,
                str(e),
            )
            return (
                jsonify(
                    {
                        "ok": False,
                        "trace_id": "",
                        "channel_id": channel_id,
                        "status": "internal_error",
                        "error": f"internal error: {e}",
                    }
                ),
                500,
            )

    @app.route("/api/gateway/health", methods=["GET"])
    def gateway_health():
        """Gateway 健康检查端点"""
        return jsonify({"status": "ok", "service": "NekoBot Gateway"})

    @app.route("/api/gateway/stats", methods=["GET"])
    def gateway_stats():
        """Gateway 运行统计信息

        返回模式、去重后端、持久化状态、队列统计、Worker 统计等。
        """
        gateway = get_gateway()
        stats = gateway.get_stats()
        return jsonify(stats)

    @app.route("/api/gateway/queue/status", methods=["GET"])
    def gateway_queue_status():
        """队列状态查询

        返回队列大小、各状态条目数等。
        """
        gateway = get_gateway()
        if not gateway.queue:
            return jsonify({
                "status": "not_available",
                "message": "队列未启用（非异步模式）",
            })

        queue_stats = gateway.queue.get_stats()
        return jsonify(queue_stats)

    @app.route("/api/gateway/worker/start", methods=["POST"])
    async def gateway_worker_start():
        """启动后台 Worker

        仅在异步模式下可用。
        启动后 Worker 会持续消费队列中的事件。
        """
        gateway = get_gateway()

        if not gateway.async_mode:
            return (
                jsonify({
                    "ok": False,
                    "error": "Worker 仅在异步模式(async_mode=True)下可用",
                }),
                400,
            )

        try:
            await gateway.start_worker()
            return jsonify({
                "ok": True,
                "message": "Worker 已启动",
                "mode": "async",
            })
        except Exception as e:
            _log.error("[Routes] Worker 启动失败 error=%s", str(e))
            return (
                jsonify({
                    "ok": False,
                    "error": str(e),
                }),
                500,
            )

    @app.route("/api/gateway/worker/stop", methods=["POST"])
    async def gateway_worker_stop():
        """停止后台 Worker

        支持优雅关闭（等待当前任务完成）和强制关闭。
        Query 参数：?force=true 强制关闭
        """
        gateway = get_gateway()

        if not gateway.worker:
            return (
                jsonify({
                    "ok": False,
                    "error": "Worker 未运行",
                }),
                400,
            )

        force = request.args.get("force", "").lower() == "true"
        try:
            await gateway.stop_worker(graceful=not force)
            return jsonify({
                "ok": True,
                "message": "Worker 已停止",
                "graceful": not force,
            })
        except Exception as e:
            _log.error("[Routes] Worker 停止失败 error=%s", str(e))
            return (
                jsonify({
                    "ok": False,
                    "error": str(e),
                }),
                500,
            )

    _log.info("[Routes] Gateway 路由已注册（含 Worker 管理端点）")
