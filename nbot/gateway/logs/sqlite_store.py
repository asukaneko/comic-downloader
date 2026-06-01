"""Gateway 日志 SQLite 存储实现

基于 GatewayStorage 同一 SQLite 数据库 (data/gateway.db)，
新增 gateway_logs 表用于统一日志记录。
启动时自动将旧 gateway_events 数据迁移到 gateway_logs。
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from nbot.gateway.logs.models import GatewayLogRecord
from nbot.gateway.logs.store import GatewayLogStore

_log = logging.getLogger(__name__)

TABLE_LOGS = "gateway_logs"
TABLE_EVENTS = "gateway_events"
TABLE_MIGRATION = "_gateway_log_migrations"

# 旧 events status → (level, stage) 映射
_STATUS_MAP: dict[str, tuple[str, str]] = {
    "received": ("info", "receive_start"),
    "verified": ("info", "auth_passed"),
    "auth_failed": ("warning", "auth_failed"),
    "rate_limited": ("warning", "rate_limited"),
    "unknown_channel": ("warning", "route_failed"),
    "missing_parser": ("warning", "route_failed"),
    "parsed": ("info", "parsed"),
    "parse_failed": ("error", "parse_failed"),
    "ignored": ("info", "ignored"),
    "duplicated": ("info", "dedupe_hit"),
    "deduped": ("info", "deduped"),
    "queued": ("info", "queued"),
    "queue_full": ("error", "queue_failed"),
    "dispatched": ("info", "dispatched"),
    "delivering": ("info", "delivering"),
    "delivered": ("info", "completed"),
    "built": ("info", "completed"),
    "no_sender": ("info", "completed"),
    "delivery_failed": ("error", "delivery_failed"),
    "dispatch_failed": ("error", "dispatch_failed"),
    "build_request_failed": ("error", "build_failed"),
    "model_selected": ("info", "dispatched"),
    "model_failover": ("warning", "dispatched"),
    "failed": ("error", "failed"),
    "dead": ("error", "failed"),
}


class SQLiteGatewayLogStore(GatewayLogStore):
    """SQLite 日志存储实现

    复用 GatewayStorage 的数据库文件 (data/gateway.db)，
    新增 gateway_logs 表。
    """

    def __init__(self, data_dir: str = ""):
        self._data_dir = data_dir or "data"
        self._db_path = os.path.join(self._data_dir, "gateway.db")
        self._ensure_table()
        self._migrate_events()

    def _connect(self) -> sqlite3.Connection:
        """获取数据库连接"""
        os.makedirs(self._data_dir, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        """创建 gateway_logs 表（如果不存在）"""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS gateway_logs (
                    id TEXT PRIMARY KEY,
                    trace_id TEXT,
                    source TEXT NOT NULL,
                    type TEXT NOT NULL,
                    level TEXT NOT NULL,
                    stage TEXT,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,

                    tool_name TEXT,
                    channel_id TEXT,
                    conversation_id TEXT,
                    user_id TEXT,
                    message_id TEXT,
                    delivery_id TEXT,
                    queue_item_id TEXT,
                    node_id TEXT,

                    request_id TEXT,
                    parent_id TEXT,

                    metadata_json TEXT,
                    error_code TEXT,
                    error_message TEXT,

                    created_at TEXT NOT NULL
                )
            """)
            indices = [
                ("idx_gateway_logs_trace_id", "trace_id"),
                ("idx_gateway_logs_source", "source"),
                ("idx_gateway_logs_type", "type"),
                ("idx_gateway_logs_tool_name", "tool_name"),
                ("idx_gateway_logs_channel_id", "channel_id"),
                ("idx_gateway_logs_message_id", "message_id"),
                ("idx_gateway_logs_delivery_id", "delivery_id"),
                ("idx_gateway_logs_queue_item_id", "queue_item_id"),
                ("idx_gateway_logs_created_at", "created_at"),
            ]
            for idx_name, col in indices:
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {TABLE_LOGS}({col})"
                )

        _log.info("[LogStore] gateway_logs 表初始化完成 path=%s", self._db_path)

    def _migrate_events(self) -> None:
        """启动时自动将旧 gateway_events 数据迁移到 gateway_logs（一次性）"""
        with self._connect() as conn:
            # 检查旧表是否存在
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            if TABLE_EVENTS not in tables:
                return

            # 检查是否已迁移
            if TABLE_MIGRATION in tables:
                done = conn.execute(
                    f"SELECT 1 FROM {TABLE_MIGRATION} WHERE name = 'events_to_logs'"
                ).fetchone()
                if done:
                    return

            # 如果 gateway_logs 已有数据，说明新日志已在写入，跳过迁移避免重复
            existing = conn.execute(f"SELECT COUNT(*) FROM {TABLE_LOGS}").fetchone()[0]
            if existing > 0:
                _log.info("[LogStore] gateway_logs 已有 %d 条记录，跳过旧事件迁移", existing)
                conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {TABLE_MIGRATION} (
                        name TEXT PRIMARY KEY, migrated_at TEXT NOT NULL
                    )
                """)
                conn.execute(
                    f"INSERT OR IGNORE INTO {TABLE_MIGRATION} VALUES (?, ?)",
                    ("events_to_logs", datetime.now().isoformat()),
                )
                return

            # 统计旧记录数
            count = conn.execute(f"SELECT COUNT(*) FROM {TABLE_EVENTS}").fetchone()[0]
            if count == 0:
                # 没有旧数据，直接标记完成
                conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {TABLE_MIGRATION} (
                        name TEXT PRIMARY KEY, migrated_at TEXT NOT NULL
                    )
                """)
                conn.execute(
                    f"INSERT OR IGNORE INTO {TABLE_MIGRATION} VALUES (?, ?)",
                    ("events_to_logs", datetime.now().isoformat()),
                )
                return

            _log.info("[LogStore] 发现 %d 条旧事件记录，开始迁移到统一日志...", count)

            # 读取旧数据
            rows = conn.execute(
                f"SELECT * FROM {TABLE_EVENTS} ORDER BY id"
            ).fetchall()

            migrated = 0
            for row in rows:
                d = dict(row)
                status = d.get("status", "")
                level, stage = _STATUS_MAP.get(status, ("info", ""))

                # 推断 action
                if status in ("received",):
                    action = "receive"
                elif status in ("verified", "auth_failed"):
                    action = "verify"
                elif status in ("rate_limited",):
                    action = "rate_limit"
                elif status in ("unknown_channel", "missing_parser"):
                    action = "route"
                elif status in ("parsed", "parse_failed", "ignored"):
                    action = "parse"
                elif status in ("duplicated", "deduped"):
                    action = "dedupe"
                elif status in ("queued", "queue_full"):
                    action = "queue"
                elif status in ("dispatched", "dispatch_failed", "build_request_failed",
                                "model_selected", "model_failover", "delivering"):
                    action = "dispatch" if "dispatch" in status or "build" in status or "model" in status else "deliver"
                elif status in ("delivered", "built", "no_sender", "delivery_failed"):
                    action = "deliver"
                else:
                    action = "event"

                log_id = f"evt_{d['id']:08d}"
                event_type = d.get("event_type", "message")
                error = d.get("error", "")

                conn.execute(
                    f"""INSERT OR IGNORE INTO {TABLE_LOGS}
                    (id, trace_id, source, type, level, stage, action, status, message,
                     channel_id, conversation_id, user_id, message_id,
                     metadata_json, error_message, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?, ?)""",
                    (
                        log_id, d.get("trace_id"), "gateway", event_type,
                        level, stage, action, status, "",
                        d.get("channel_id"), d.get("conversation_id"),
                        d.get("user_id"), d.get("message_id"),
                        d.get("metadata_json"), error or None,
                        d.get("created_at"),
                    ),
                )
                migrated += 1

            # 标记迁移完成
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE_MIGRATION} (
                    name TEXT PRIMARY KEY, migrated_at TEXT NOT NULL
                )
            """)
            conn.execute(
                f"INSERT OR IGNORE INTO {TABLE_MIGRATION} VALUES (?, ?)",
                ("events_to_logs", datetime.now().isoformat()),
            )

        _log.info("[LogStore] 旧事件迁移完成 count=%d", migrated)

    def _row_to_record(self, row: sqlite3.Row) -> GatewayLogRecord:
        """将数据库行转换为 GatewayLogRecord"""
        d = dict(row)
        metadata = None
        if d.get("metadata_json"):
            try:
                metadata = json.loads(d["metadata_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        return GatewayLogRecord(
            id=d["id"],
            trace_id=d.get("trace_id"),
            source=d["source"],
            type=d["type"],
            level=d["level"],
            stage=d.get("stage", ""),
            action=d["action"],
            status=d["status"],
            message=d.get("message", ""),
            tool_name=d.get("tool_name"),
            channel_id=d.get("channel_id"),
            conversation_id=d.get("conversation_id"),
            user_id=d.get("user_id"),
            message_id=d.get("message_id"),
            delivery_id=d.get("delivery_id"),
            queue_item_id=d.get("queue_item_id"),
            node_id=d.get("node_id"),
            request_id=d.get("request_id"),
            parent_id=d.get("parent_id"),
            metadata=metadata,
            error_code=d.get("error_code"),
            error_message=d.get("error_message"),
            created_at=d["created_at"],
        )

    def insert(self, record: GatewayLogRecord) -> None:
        """插入一条日志记录"""
        meta_json = json.dumps(record.metadata, ensure_ascii=False) if record.metadata else None
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {TABLE_LOGS}
                (id, trace_id, source, type, level, stage, action, status, message,
                 tool_name, channel_id, conversation_id, user_id, message_id,
                 delivery_id, queue_item_id, node_id,
                 request_id, parent_id,
                 metadata_json, error_code, error_message,
                 created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?,
                        ?, ?, ?,
                        ?)
                """,
                (
                    record.id, record.trace_id, record.source, record.type,
                    record.level, record.stage, record.action, record.status,
                    record.message,
                    record.tool_name, record.channel_id, record.conversation_id,
                    record.user_id, record.message_id,
                    record.delivery_id, record.queue_item_id, record.node_id,
                    record.request_id, record.parent_id,
                    meta_json, record.error_code, record.error_message,
                    record.created_at,
                ),
            )

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
        conditions: list[str] = []
        params: list[Any] = []
        for val, col in [
            (trace_id, "trace_id"),
            (source, "source"),
            (type, "type"),
            (level, "level"),
            (status, "status"),
            (tool_name, "tool_name"),
            (channel_id, "channel_id"),
        ]:
            if val:
                conditions.append(f"{col} = ?")
                params.append(val)

        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {TABLE_LOGS}{where}"
                f" ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
            return [self._row_to_record(r) for r in rows]

    def get_by_trace(self, trace_id: str) -> list[GatewayLogRecord]:
        """根据 trace_id 查询所有关联日志"""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {TABLE_LOGS} WHERE trace_id = ? ORDER BY created_at",
                (trace_id,),
            ).fetchall()
            return [self._row_to_record(r) for r in rows]

    def get_by_id(self, log_id: str) -> GatewayLogRecord | None:
        """根据日志 ID 查询单条记录"""
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM {TABLE_LOGS} WHERE id = ?",
                (log_id,),
            ).fetchone()
            return self._row_to_record(row) if row else None

    def count(self) -> int:
        """获取日志总数"""
        with self._connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM {TABLE_LOGS}").fetchone()
            return row["cnt"] if row else 0

    def cleanup(self, *, keep_days: int = 30) -> int:
        """清理旧日志"""
        cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                f"DELETE FROM {TABLE_LOGS} WHERE created_at < ?",
                (cutoff,),
            )
            count = cursor.rowcount
        if count:
            _log.debug("[LogStore] 清理旧日志 count=%d", count)
        return count
