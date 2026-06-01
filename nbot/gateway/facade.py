"""Gateway Facade - 面向 MCP 的稳定服务接口

将 Gateway 内部组件的能力整理成统一的方法签名，
MCP 工具层不直接操作 gateway.storage / gateway.queue 等细节，
全部通过 Facade 调用。

设计原则：
- 返回值全部是 JSON 可序列化结构
- 不把底层对象直接暴露给 MCP
- 后续 Gateway 内部改结构，MCP 层不用大改
"""

import logging
from typing import Any

from nbot.gateway.gateway import ChannelGateway
from nbot.gateway.nodes.registry import NodeInfo, NodeRegistry

_log = logging.getLogger(__name__)


class GatewayFacade:
    """Gateway 服务门面

    将 ChannelGateway 的核心能力整理成 MCP 可调用的方法。
    """

    def __init__(
        self,
        gateway: ChannelGateway,
        node_registry: NodeRegistry | None = None,
    ):
        self._gateway = gateway
        self._node_registry = node_registry

    @property
    def gateway(self) -> ChannelGateway:
        return self._gateway

    # ========================
    # Gateway 状态查询
    # ========================

    async def get_status(self) -> dict[str, Any]:
        """获取 Gateway 健康状态"""
        queue_stats = None
        if self._gateway.queue:
            queue_stats = self._gateway.queue.get_stats()

        worker_running = False
        if self._gateway.worker:
            worker_running = self._gateway.worker.is_running

        return {
            "ok": True,
            "mode": "async" if self._gateway.async_mode else "sync",
            "storage": "sqlite" if self._gateway.storage else "memory",
            "worker_running": worker_running,
            "log_service": {
                "enabled": self._gateway.log_service is not None,
                "store": "sqlite" if self._gateway.log_service else "none",
            },
            "queue": {
                "pending": queue_stats.get("queue_size", 0) if queue_stats else 0,
                "processing": queue_stats.get("status_breakdown", {}).get("processing", 0) if queue_stats else 0,
                "dead": queue_stats.get("total_dead", 0) if queue_stats else 0,
            },
        }

    async def get_stats(self) -> dict[str, Any]:
        """获取事件、投递、去重、队列统计"""
        result: dict[str, Any] = {
            "events": {"count": 0},
            "deliveries": {"count": 0},
            "dedupe": {"count": 0},
            "queue": {
                "enqueued": 0,
                "completed": 0,
                "failed": 0,
                "dead": 0,
            },
        }

        if self._gateway.event_store:
            result["events"]["count"] = self._gateway.event_store.count()

        if self._gateway.delivery_store_obj:
            result["deliveries"]["count"] = self._gateway.delivery_store_obj.count()

        if self._gateway.dedupe_store:
            backend = self._gateway.dedupe_store.backend_name
            if backend == "sqlite" and self._gateway.storage:
                result["dedupe"]["count"] = self._gateway.storage.dedupe_count()

        if self._gateway.queue:
            qs = self._gateway.queue.get_stats()
            result["queue"] = {
                "enqueued": qs.get("total_enqueued", 0),
                "completed": qs.get("total_completed", 0),
                "failed": qs.get("total_failed", 0),
                "dead": qs.get("total_dead", 0),
            }

        return result

    # ========================
    # 事件与追踪查询
    # ========================

    async def query_trace(self, trace_id: str) -> dict[str, Any]:
        """根据 trace_id 聚合查询完整链路

        升级为聚合查询：events + deliveries + mcp_logs + timeline。
        空结果时返回 diagnostics 诊断信息。
        """
        if self._gateway.log_service:
            return self._gateway.log_service.aggregate_trace(
                trace_id,
                event_store=self._gateway.event_store,
                delivery_store=self._gateway.delivery_store_obj,
                queue=self._gateway.queue,
            )

        # 回退：无 log_service 时只查 event_store
        if not self._gateway.event_store:
            return {
                "ok": True,
                "trace_id": trace_id,
                "summary": {"events_count": 0, "deliveries_count": 0, "queue_items_count": 0, "mcp_logs_count": 0, "has_content": False},
                "events": [],
                "deliveries": [],
                "queue_items": [],
                "mcp_logs": [],
                "timeline": [],
                "diagnostics": {
                    "reason": "event store not available",
                    "possible_causes": ["storage not configured"],
                    "next_step": "check gateway configuration",
                },
            }

        raw_events = self._gateway.event_store.get_by_trace(trace_id)
        events = [_sanitize_event(ev) for ev in raw_events]
        has_content = len(events) > 0

        result: dict[str, Any] = {
            "ok": True,
            "trace_id": trace_id,
            "summary": {
                "events_count": len(events),
                "deliveries_count": 0,
                "queue_items_count": 0,
                "mcp_logs_count": 0,
                "has_content": has_content,
            },
            "events": events,
            "deliveries": [],
            "queue_items": [],
            "mcp_logs": [],
            "timeline": [],
        }

        if not has_content:
            result["diagnostics"] = {
                "reason": "no records found for this trace_id",
                "possible_causes": [
                    "the given id is not a trace_id",
                    "the event was not persisted",
                    "the id belongs to delivery, queue or message instead",
                ],
                "next_step": "call gateway_lookup_id with the same id",
            }

        return result

    async def lookup_id(self, value: str) -> dict[str, Any]:
        """识别任意 ID 的类型"""
        if not self._gateway.log_service:
            return {"ok": False, "error": "log service not available"}

        return self._gateway.log_service.lookup_id(
            value,
            event_store=self._gateway.event_store,
            delivery_store=self._gateway.delivery_store_obj,
            queue=self._gateway.queue,
        )

    async def query_logs(
        self,
        *,
        trace_id: str = "",
        source: str = "",
        type: str = "",
        level: str = "",
        status: str = "",
        tool_name: str = "",
        channel_id: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """查询统一日志"""
        if not self._gateway.log_service:
            return {"ok": False, "items": [], "error": "log service not available"}

        records = self._gateway.log_service.query(
            trace_id=trace_id,
            source=source,
            type=type,
            level=level,
            status=status,
            tool_name=tool_name,
            channel_id=channel_id,
            limit=limit,
            offset=offset,
        )
        return {
            "ok": True,
            "items": self._gateway.log_service.records_to_dicts(
                records,
                event_store=self._gateway.event_store,
            ),
            "count": len(records),
            "limit": limit,
            "offset": offset,
        }

    async def query_events(
        self,
        *,
        channel_id: str = "",
        status: str = "",
        event_type: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        """按条件查询事件历史"""
        if not self._gateway.event_store:
            return {"ok": False, "items": [], "error": "event store not available"}

        raw_events = self._gateway.event_store.query(
            channel_id=channel_id,
            status=status,
            event_type=event_type,
            limit=limit,
        )
        items = [_sanitize_event(ev) for ev in raw_events]
        return {"ok": True, "items": items}

    # ========================
    # 投递查询
    # ========================

    async def query_deliveries(
        self,
        *,
        trace_id: str = "",
        channel_id: str = "",
        status: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        """查询回复投递记录"""
        if not self._gateway.delivery_store_obj:
            return {"ok": False, "items": [], "error": "delivery store not available"}

        if trace_id:
            record = self._gateway.delivery_store_obj.get_by_trace(trace_id)
            items = [record] if record else []
        else:
            items = self._gateway.delivery_store_obj.query(
                channel_id=channel_id,
                status=status,
                limit=limit,
            )

        sanitized = [_sanitize_delivery(d) for d in items if d]
        return {"ok": True, "items": sanitized}

    # ========================
    # 队列操作
    # ========================

    async def get_queue_stats(self) -> dict[str, Any]:
        """获取异步队列状态"""
        if not self._gateway.queue:
            return {
                "ok": True,
                "enqueued": 0,
                "completed": 0,
                "failed": 0,
                "dead": 0,
                "status_breakdown": {},
            }

        qs = self._gateway.queue.get_stats()
        return {
            "ok": True,
            "enqueued": qs.get("total_enqueued", 0),
            "completed": qs.get("total_completed", 0),
            "failed": qs.get("total_failed", 0),
            "dead": qs.get("total_dead", 0),
            "status_breakdown": qs.get("status_breakdown", {}),
        }

    async def retry_dead_letter(self, item_id: str) -> dict[str, Any]:
        """重试死信队列中的某个任务"""
        if not self._gateway.queue:
            return {"ok": False, "item_id": item_id, "error": "queue not available"}

        item = self._gateway.queue.get_item(item_id)
        if not item:
            return {"ok": False, "item_id": item_id, "error": "item not found"}

        from nbot.gateway.queue import QueueItemStatus

        if item.status != QueueItemStatus.DEAD:
            return {
                "ok": False,
                "item_id": item_id,
                "error": f"item status is {item.status.value}, not dead",
            }

        # 重置状态为 PENDING，允许重新处理
        self._gateway.queue.update_item(
            item_id,
            status=QueueItemStatus.PENDING,
            attempt=0,
            error="",
            next_retry_at=None,
        )

        # 重新入队
        enqueued = await self._gateway.queue.enqueue(item)
        if not enqueued:
            return {"ok": False, "item_id": item_id, "error": "queue is full"}

        return {"ok": True, "item_id": item_id, "status": "PENDING"}

    # ========================
    # 消息操作
    # ========================

    async def receive_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        """模拟或提交一条频道消息，让 Gateway 按正常管线处理

        Args:
            payload: {
                "channel_id": str,
                "raw_event": dict,
                "headers": dict | None,
                "remote_addr": str,
            }
        """
        result = await self._gateway.receive(
            channel_id=payload["channel_id"],
            raw_event=payload["raw_event"],
            headers=payload.get("headers"),
            remote_addr=payload.get("remote_addr", "127.0.0.1"),
        )
        return result.to_dict()

    async def send_channel_message(
        self,
        *,
        channel_id: str,
        conversation_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """直接向某个频道投递消息（高危操作）"""
        from nbot.core.chat_models import ChatResponse
        from nbot.gateway.schemas import DeliveryRequest

        delivery_request = DeliveryRequest(
            trace_id=self._gateway.trace_factory.new_trace_id(),
            channel_id=channel_id,
            conversation_id=conversation_id,
            content=content,
            metadata=metadata or {},
        )

        chat_response = ChatResponse(final_content=content)
        chat_request = type("ChatRequest", (), {
            "conversation_id": conversation_id,
            "parent_message_id": None,
        })()

        try:
            delivery_result = await self._gateway.delivery.send_response(
                channel_id=channel_id,
                chat_request=chat_request,
                chat_response=chat_response,
                trace_id=delivery_request.trace_id,
                metadata=metadata,
            )
            return {
                "ok": True,
                "trace_id": delivery_request.trace_id,
                "status": delivery_result.get("status", "unknown"),
            }
        except Exception as e:
            return {
                "ok": False,
                "trace_id": delivery_request.trace_id,
                "error": str(e),
            }

    # ========================
    # 内部任务
    # ========================

    async def submit_internal_task(
        self,
        *,
        task_kind: str,
        task_id: str,
        trigger_source: str = "mcp",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """触发内部任务（心跳、工作流、定时任务等）"""

        async def _noop_handler():
            return {"status": "noop", "task_kind": task_kind}

        result = await self._gateway.submit_internal_task(
            task_kind=task_kind,
            task_id=task_id,
            handler=_noop_handler,
            trigger_source=trigger_source,
            metadata=metadata,
        )
        return result.to_dict()

    # ========================
    # 节点管理
    # ========================

    async def list_nodes(
        self,
        *,
        node_type: str = "",
        status: str = "",
    ) -> dict[str, Any]:
        """列出所有节点"""
        if not self._node_registry:
            return {"ok": True, "nodes": []}

        nodes = self._node_registry.find_nodes(node_type=node_type, status=status)
        return {
            "ok": True,
            "nodes": [_node_to_dict(n) for n in nodes],
        }

    async def get_node(self, node_id: str) -> dict[str, Any]:
        """获取节点详情"""
        if not self._node_registry:
            return {"ok": False, "error": "node registry not available"}

        node = self._node_registry.get_node(node_id)
        if not node:
            return {"ok": False, "error": f"node not found: {node_id}"}

        return {"ok": True, "node": _node_to_dict(node)}

    async def register_node(
        self,
        *,
        node_id: str,
        node_type: str = "worker",
        version: str = "",
        address: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """注册节点"""
        if not self._node_registry:
            return {"ok": False, "error": "node registry not available"}

        node_info = NodeInfo(
            node_id=node_id,
            node_type=node_type,
            version=version,
            address=address,
            metadata=metadata or {},
        )

        try:
            self._node_registry.register(node_info)
            return {"ok": True, "node_id": node_id}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ========================
    # 能力声明
    # ========================

    async def get_capabilities(self) -> dict[str, Any]:
        """获取当前 Gateway 能力清单"""
        tools = [
            "gateway_get_status",
            "gateway_get_stats",
            "gateway_query_trace",
            "gateway_query_events",
            "gateway_query_deliveries",
            "gateway_get_queue_stats",
            "gateway_receive_message",
            "gateway_submit_internal_task",
            "gateway_list_nodes",
            "gateway_get_node",
        ]

        resources = [
            "nekobot://gateway/status",
            "nekobot://gateway/stats",
            "nekobot://gateway/capabilities",
            "nekobot://gateway/queue/stats",
            "nekobot://gateway/nodes",
        ]

        permissions = [
            "gateway.read",
            "events.query",
            "queue.read",
            "node.read",
        ]

        node_capabilities: list[dict[str, Any]] = []
        if self._node_registry:
            for node_dict in self._node_registry.list_all():
                caps = node_dict.get("capabilities")
                if caps:
                    node_capabilities.append({
                        "node_id": node_dict["node_id"],
                        "capabilities": caps,
                    })

        return {
            "tools": tools,
            "resources": resources,
            "permissions": permissions,
            "node_capabilities": node_capabilities,
        }


# ========================
# 辅助函数
# ========================


def _sanitize_event(ev: dict[str, Any]) -> dict[str, Any]:
    """清理事件数据，移除敏感信息并确保可序列化"""
    result: dict[str, Any] = {
        "status": ev.get("status", ""),
        "channel_id": ev.get("channel_id", ""),
        "created_at": ev.get("created_at", ""),
    }

    for key in ("trace_id", "conversation_id", "user_id", "message_id", "event_type", "error"):
        val = ev.get(key)
        if val:
            result[key] = val

    # metadata 可选返回（脱敏）
    metadata = ev.get("metadata_json")
    if metadata:
        import json

        try:
            meta = json.loads(metadata) if isinstance(metadata, str) else metadata
            result["metadata"] = _redact_sensitive(meta)
        except (json.JSONDecodeError, TypeError):
            pass

    return result


def _sanitize_delivery(d: dict[str, Any]) -> dict[str, Any]:
    """清理投递数据"""
    result: dict[str, Any] = {}
    for key in ("id", "trace_id", "channel_id", "conversation_id", "status", "attempts", "error", "created_at", "updated_at"):
        val = d.get(key)
        if val is not None:
            result[key] = val
    return result


def _node_to_dict(node: NodeInfo) -> dict[str, Any]:
    """将 NodeInfo 转换为字典"""
    return node.to_dict()


def _redact_sensitive(data: dict[str, Any]) -> dict[str, Any]:
    """脱敏敏感字段"""
    sensitive_keys = {"token", "secret", "password", "authorization", "api_key"}
    return {
        k: "***" if k.lower() in sensitive_keys else v
        for k, v in data.items()
    }
