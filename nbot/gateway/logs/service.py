"""Gateway 统一日志服务

提供统一的日志记录、查询、聚合能力。
作为 Gateway 内部各模块和 MCP 层的统一写入入口。
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from nbot.gateway.logs.models import GatewayLogRecord
from nbot.gateway.logs.redact import redact_metadata, redact_sensitive
from nbot.gateway.logs.store import GatewayLogStore

_log = logging.getLogger(__name__)


class GatewayLogService:
    """Gateway 统一日志服务

    职责：
    1. 记录各类日志（MCP 调用、Gateway 事件、投递、安全等）
    2. 提供统一查询接口
    3. 聚合 trace 链路（events + deliveries + mcp_logs）
    4. ID 类型识别与查找
    """

    def __init__(self, store: GatewayLogStore):
        self._store = store

    @property
    def store(self) -> GatewayLogStore:
        return self._store

    def record(
        self,
        *,
        source: str,
        type: str,
        action: str,
        status: str,
        message: str = "",
        level: str = "info",
        stage: str = "",
        trace_id: str | None = None,
        tool_name: str | None = None,
        channel_id: str | None = None,
        conversation_id: str | None = None,
        user_id: str | None = None,
        message_id: str | None = None,
        delivery_id: str | None = None,
        queue_item_id: str | None = None,
        node_id: str | None = None,
        request_id: str | None = None,
        parent_id: str | None = None,
        raw_event: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> GatewayLogRecord:
        """记录一条日志

        自动生成 id 和 created_at，对 metadata 进行脱敏后写入。
        """
        now = datetime.now().isoformat()
        log_id = f"log_{uuid.uuid4().hex[:16]}"

        safe_metadata = redact_metadata(metadata)
        safe_raw_event = redact_sensitive(raw_event) if raw_event else None

        record = GatewayLogRecord(
            id=log_id,
            trace_id=trace_id,
            source=source,
            type=type,
            level=level,
            stage=stage,
            action=action,
            status=status,
            message=message,
            tool_name=tool_name,
            channel_id=channel_id,
            conversation_id=conversation_id,
            user_id=user_id,
            message_id=message_id,
            delivery_id=delivery_id,
            queue_item_id=queue_item_id,
            node_id=node_id,
            request_id=request_id,
            parent_id=parent_id,
            raw_event=safe_raw_event,
            metadata=safe_metadata,
            error_code=error_code,
            error_message=error_message,
            created_at=now,
        )

        self._store.insert(record)
        return record

    def query(
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
    ) -> list[GatewayLogRecord]:
        """按条件查询日志"""
        return self._store.query(
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

    def query_by_trace(self, trace_id: str) -> list[GatewayLogRecord]:
        """根据 trace_id 查询所有关联日志"""
        return self._store.get_by_trace(trace_id)

    def records_to_dicts(
        self,
        records: list[GatewayLogRecord],
        *,
        event_store: Any = None,
    ) -> list[dict[str, Any]]:
        """Convert log records to API dictionaries, enriched from matching event rows."""
        items = [record.to_dict() for record in records]
        if not event_store:
            return items

        events_by_trace: dict[str, list[dict[str, Any]]] = {}
        used_event_indexes: dict[str, set[int]] = {}

        for record, item in zip(records, items, strict=False):
            trace_id = record.trace_id or ""
            if not trace_id:
                continue
            if trace_id not in events_by_trace:
                try:
                    events_by_trace[trace_id] = event_store.get_by_trace(trace_id)
                except Exception:
                    events_by_trace[trace_id] = []
            events = events_by_trace[trace_id]
            used = used_event_indexes.setdefault(trace_id, set())
            event_index = _find_matching_event_index(record, events, used)
            if event_index is None:
                continue
            used.add(event_index)
            _merge_event_fields(item, events[event_index])

        return items

    def lookup_id(
        self,
        value: str,
        event_store: Any = None,
        delivery_store: Any = None,
        queue: Any = None,
    ) -> dict[str, Any]:
        """识别任意 ID 的类型

        在 events、deliveries、gateway_logs、queue 中搜索该 ID，
        返回匹配结果和最佳猜测。
        """
        matches: list[dict[str, Any]] = []

        # 1. 在 gateway_logs 中查找
        log_as_trace = self._store.get_by_trace(value)
        if log_as_trace:
            matches.append({
                "type": "mcp_log_trace_id",
                "count": len(log_as_trace),
                "source": "gateway_logs",
            })

        log_as_id = self._store.get_by_id(value)
        if log_as_id:
            matches.append({
                "type": "mcp_log_id",
                "count": 1,
                "source": "gateway_logs",
            })

        # 2. 在 events 中查找
        if event_store:
            events_by_trace = event_store.get_by_trace(value)
            if events_by_trace:
                matches.append({
                    "type": "trace_id",
                    "count": len(events_by_trace),
                    "source": "gateway_events",
                })

        # 3. 在 deliveries 中查找
        if delivery_store:
            delivery = delivery_store.get_by_trace(value)
            if delivery:
                matches.append({
                    "type": "delivery_trace_id",
                    "count": 1,
                    "source": "deliveries",
                })

        # 4. 在 queue 中查找
        if queue:
            item = queue.get_item(value)
            if item:
                matches.append({
                    "type": "queue_item_id",
                    "count": 1,
                    "source": "queue",
                })

        best_guess = _compute_best_guess(matches)
        next_tools = _suggest_next_tools(value, matches)

        return {
            "ok": True,
            "input": value,
            "matches": matches,
            "best_guess": best_guess,
            "next_tools": next_tools,
        }

    def aggregate_trace(
        self,
        trace_id: str,
        event_store: Any = None,
        delivery_store: Any = None,
        queue: Any = None,
    ) -> dict[str, Any]:
        """聚合 trace 链路

        聚合 events + deliveries + mcp_logs + timeline。
        """
        raw_events = event_store.get_by_trace(trace_id) if event_store else []
        delivery = delivery_store.get_by_trace(trace_id) if delivery_store else None
        deliveries = [delivery] if delivery else []
        all_logs = self._store.get_by_trace(trace_id)

        # 回退：前端对无 trace_id 的记录构造了 event-{log_id} 伪 ID，
        # 按 trace_id 查不到时，尝试提取 log ID 并按 ID 查询。
        if not all_logs and trace_id.startswith("event-"):
            log_id = trace_id[len("event-"):]
            record = self._store.get_by_id(log_id)
            if record:
                all_logs = [record]

        mcp_logs = _filter_event_mirror_logs(raw_events, all_logs)

        # queue items
        queue_items: list[dict[str, Any]] = []
        if queue:
            item = queue.get_item(trace_id)
            if item:
                queue_items.append(_queue_item_to_dict(item))

        # 构建时间线
        timeline: list[dict[str, Any]] = []

        for ev in raw_events:
            timeline.append(_event_to_timeline_item(ev))

        for d in deliveries:
            if d:
                timeline.append({
                    "type": "delivery",
                    "status": d.get("status", ""),
                    "created_at": d.get("created_at", ""),
                    "channel_id": d.get("channel_id", ""),
                })

        for log in mcp_logs:
            timeline.append(_log_to_timeline_item(log))

        for qi in queue_items:
            timeline.append({
                "type": "queue_item",
                "status": qi.get("status", ""),
                "created_at": qi.get("created_at", ""),
            })

        timeline.sort(key=lambda x: x.get("created_at", ""))

        events_count = len(raw_events)
        deliveries_count = len(deliveries)
        queue_items_count = len(queue_items)
        mcp_logs_count = len(mcp_logs)
        has_content = any([events_count, deliveries_count, queue_items_count, mcp_logs_count])

        result: dict[str, Any] = {
            "ok": True,
            "trace_id": trace_id,
            "summary": {
                "events_count": events_count,
                "deliveries_count": deliveries_count,
                "queue_items_count": queue_items_count,
                "mcp_logs_count": mcp_logs_count,
                "has_content": has_content,
            },
            "events": raw_events,
            "deliveries": [_sanitize_delivery_minimal(d) for d in deliveries if d],
            "queue_items": queue_items,
            "mcp_logs": self.records_to_dicts(mcp_logs),
            "timeline": timeline,
        }

        if not has_content:
            result["diagnostics"] = {
                "reason": "no records found for this trace_id",
                "possible_causes": [
                    "the given id is not a trace_id",
                    "event store is not enabled",
                    "the event was not persisted",
                    "the id belongs to delivery, queue or message instead",
                ],
                "next_step": "call gateway_lookup_id with the same id",
            }

        return result


def _filter_event_mirror_logs(
    events: list[dict[str, Any]],
    logs: list[GatewayLogRecord],
) -> list[GatewayLogRecord]:
    """Remove gateway log rows that mirror lifecycle rows already present in events."""
    if not events:
        return logs

    matched_event_indexes: set[int] = set()
    visible_logs: list[GatewayLogRecord] = []

    for log in logs:
        event_index = _find_matching_event_index(log, events, matched_event_indexes)
        if event_index is None:
            visible_logs.append(log)
            continue
        matched_event_indexes.add(event_index)

    return visible_logs


def _find_matching_event_index(
    log: GatewayLogRecord,
    events: list[dict[str, Any]],
    used_indexes: set[int],
) -> int | None:
    """Find the event mirrored by a gateway log record, if any."""
    if log.source != "gateway":
        return None

    migrated_event_id = _migrated_event_id(log.id)
    if migrated_event_id is not None:
        for index, event in enumerate(events):
            if index not in used_indexes and event.get("id") == migrated_event_id:
                return index

    for index, event in enumerate(events):
        if index in used_indexes:
            continue
        if not _event_matches_log(event, log):
            continue
        return index

    return None


def _migrated_event_id(log_id: str) -> int | None:
    """Return legacy gateway_events.id encoded in migrated evt_* log ids."""
    if not log_id.startswith("evt_"):
        return None
    try:
        return int(log_id[4:])
    except ValueError:
        return None


def _event_matches_log(event: dict[str, Any], log: GatewayLogRecord) -> bool:
    """Heuristic match for live gateway event/log pairs written in the same call path."""
    if _norm(event.get("status")) != _norm(log.status):
        return False
    for event_key, log_value in (
        ("channel_id", log.channel_id),
        ("conversation_id", log.conversation_id),
        ("user_id", log.user_id),
        ("message_id", log.message_id),
    ):
        event_value = _norm(event.get(event_key))
        log_value_norm = _norm(log_value)
        if event_value and log_value_norm and event_value != log_value_norm:
            return False
    return _timestamps_close(event.get("created_at", ""), log.created_at)


def _timestamps_close(left: str, right: str, max_seconds: float = 10.0) -> bool:
    if not left or not right:
        return True
    try:
        left_dt = datetime.fromisoformat(str(left))
        right_dt = datetime.fromisoformat(str(right))
    except ValueError:
        return left == right
    return abs((left_dt - right_dt).total_seconds()) <= max_seconds


def _norm(value: Any) -> str:
    return str(value or "")


def _event_to_timeline_item(event: dict[str, Any]) -> dict[str, Any]:
    item = dict(event)
    item.setdefault("timeline_type", "event")
    return item


def _log_to_timeline_item(log: GatewayLogRecord) -> dict[str, Any]:
    item = log.to_dict()
    item.setdefault("timeline_type", "log")
    return item


def _merge_event_fields(item: dict[str, Any], event: dict[str, Any]) -> None:
    """Add event-only display fields to a log item without losing log metadata."""
    for key in (
        "raw_event_json",
        "event_type",
        "conversation_id",
        "user_id",
        "message_id",
        "channel_id",
        "error",
    ):
        value = event.get(key)
        if value and not item.get(key):
            item[key] = value

    event_metadata = _json_loads(event.get("metadata_json"))
    log_metadata = _json_loads(item.get("metadata_json"))
    merged_metadata = {**event_metadata, **log_metadata}
    if merged_metadata:
        item["metadata"] = merged_metadata
        item["metadata_json"] = json.dumps(merged_metadata, ensure_ascii=False)


def _json_loads(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        loaded = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _compute_best_guess(matches: list[dict[str, Any]]) -> dict[str, Any]:
    """根据匹配结果计算最佳猜测"""
    if not matches:
        return {"type": "unknown", "confidence": 0.0}

    priority = {
        "trace_id": 0.95,
        "delivery_trace_id": 0.85,
        "queue_item_id": 0.90,
        "mcp_log_trace_id": 0.80,
        "mcp_log_id": 0.70,
    }

    best = max(matches, key=lambda m: priority.get(m["type"], 0.5))
    return {
        "type": best["type"],
        "confidence": priority.get(best["type"], 0.5),
    }


def _suggest_next_tools(value: str, matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """根据匹配结果建议下一步工具调用"""
    tools: list[dict[str, Any]] = []

    has_trace = any(m["type"] in ("trace_id", "mcp_log_trace_id") for m in matches)
    has_delivery = any("delivery" in m["type"] for m in matches)
    has_queue = any(m["type"] == "queue_item_id" for m in matches)

    if has_trace:
        tools.append({"tool": "gateway_query_trace", "args": {"trace_id": value}})
    if has_delivery:
        tools.append({"tool": "gateway_query_deliveries", "args": {"trace_id": value}})
    if has_queue:
        tools.append({"tool": "gateway_get_queue_stats", "args": {}})

    if not tools:
        tools.append({"tool": "gateway_query_events", "args": {"channel_id": value}})

    return tools


def _queue_item_to_dict(item: Any) -> dict[str, Any]:
    """将 QueueItem 转换为字典"""
    return {
        "item_id": item.item_id,
        "trace_id": item.trace_id,
        "channel_id": item.channel_id,
        "status": item.status.value if hasattr(item.status, "value") else str(item.status),
        "attempt": item.attempt,
        "error": item.error,
        "created_at": datetime.fromtimestamp(item.created_at).isoformat() if item.created_at else "",
    }


def _sanitize_delivery_minimal(d: dict[str, Any]) -> dict[str, Any]:
    """清理投递数据（最小化）"""
    result: dict[str, Any] = {}
    for key in ("id", "trace_id", "channel_id", "conversation_id", "status", "attempts", "error", "created_at", "updated_at"):
        val = d.get(key)
        if val is not None:
            result[key] = val
    return result
