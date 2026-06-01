"""Gateway 日志 SQLite 存储实现

基于 GatewayStorage 同一 SQLite 数据库 (data/gateway.db)，
新增 gateway_logs 表用于统一日志记录。
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


class SQLiteGatewayLogStore(GatewayLogStore):
    """SQLite 日志存储实现

    复用 GatewayStorage 的数据库文件 (data/gateway.db)，
    新增 gateway_logs 表。
    """

    def __init__(self, data_dir: str = ""):
        self._data_dir = data_dir or "data"
        self._db_path = os.path.join(self._data_dir, "gateway.db")
        self._ensure_table()

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
