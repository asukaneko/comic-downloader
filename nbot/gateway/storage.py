"""Gateway SQLite 持久化存储

提供三张核心表：
- gateway_dedupe:   消息去重记录
- gateway_events:   事件生命周期日志
- gateway_deliveries: 回复投递状态

数据库文件：data/gateway.db（独立于 sessions.db）
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any

_log = logging.getLogger(__name__)

# 默认数据目录
_DEFAULT_DATA_DIR = "data"

# 表名常量
TABLE_DEDUPE = "gateway_dedupe"
TABLE_EVENTS = "gateway_events"
TABLE_DELIVERIES = "gateway_deliveries"


class GatewayStorage:
    """Gateway 专用 SQLite 存储管理器

    管理去重、事件、投递三张表的建表、CRUD 和清理操作。
    """

    def __init__(self, data_dir: str = ""):
        self.data_dir = data_dir or _DEFAULT_DATA_DIR
        self._db_path = os.path.join(self.data_dir, "gateway.db")
        self._ensure_tables()

    def _connect(self) -> sqlite3.Connection:
        """获取数据库连接"""
        os.makedirs(self.data_dir, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self) -> None:
        """创建所有需要的表（如果不存在）"""
        with self._connect() as conn:
            # 消息去重表
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE_DEDUPE} (
                    dedupe_key TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT
                )
            """)
            # 去重索引
            conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{TABLE_DEDUPE}_expires
                ON {TABLE_DEDUPE}(expires_at)
            """)

            # 事件日志表
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE_EVENTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    conversation_id TEXT,
                    user_id TEXT,
                    message_id TEXT,
                    event_type TEXT,
                    status TEXT NOT NULL,
                    raw_event_json TEXT,
                    metadata_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            # 事件索引
            conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{TABLE_EVENTS}_trace_id
                ON {TABLE_EVENTS}(trace_id)
            """)
            conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{TABLE_EVENTS}_channel_created
                ON {TABLE_EVENTS}(channel_id, created_at)
            """)
            conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{TABLE_EVENTS}_status
                ON {TABLE_EVENTS}(status)
            """)

            # 投递状态表
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE_DELIVERIES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    content TEXT,
                    request_json TEXT,
                    response_json TEXT,
                    error TEXT,
                    attempts INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            # 投递索引
            conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{TABLE_DELIVERIES}_trace_id
                ON {TABLE_DELIVERIES}(trace_id)
            """)
            conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{TABLE_DELIVERIES}_channel_status
                ON {TABLE_DELIVERIES}(channel_id, status)
            """)

        _log.info("[Storage] 数据库初始化完成 path=%s", self._db_path)

    # ========================
    # Dedupe（去重）操作
    # ========================

    def dedupe_exists(self, key: str) -> bool:
        """检查去重键是否存在且未过期"""
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT expires_at FROM {TABLE_DEDUPE} WHERE dedupe_key = ?",
                (key,),
            ).fetchone()
            if not row:
                return False
            # 检查是否过期
            if row["expires_at"]:
                try:
                    expires_at = datetime.fromisoformat(row["expires_at"])
                    if datetime.now() > expires_at:
                        # 过期则删除并返回 False
                        self.dedupe_delete(key)
                        return False
                except (ValueError, TypeError):
                    pass
            return True

    def dedupe_mark(self, key: str, channel_id: str, message_id: str, ttl_seconds: int = 86400) -> None:
        """标记消息已处理"""
        now = datetime.now().isoformat()
        expires_at = (datetime.now() + timedelta(seconds=ttl_seconds)).isoformat()
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {TABLE_DEDUPE} (dedupe_key, channel_id, message_id, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(dedupe_key) DO UPDATE SET
                    expires_at = excluded.expires_at
                """,
                (key, channel_id, message_id, now, expires_at),
            )

    def dedupe_delete(self, key: str) -> None:
        """删除去重记录"""
        with self._connect() as conn:
            conn.execute(f"DELETE FROM {TABLE_DEDUPE} WHERE dedupe_key = ?", (key,))

    def dedupe_cleanup_expired(self) -> int:
        """清理已过期的去重记录，返回清理数量"""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                f"DELETE FROM {TABLE_DEDUPE} WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            count = cursor.rowcount
        if count:
            _log.debug("[Storage] 清理过期去重记录 count=%d", count)
        return count

    def dedupe_count(self) -> int:
        """获取当前去重记录总数"""
        with self._connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM {TABLE_DEDUPE}").fetchone()
            return row["cnt"] if row else 0

    # ========================
    # Events（事件）操作
    # ========================

    def event_insert(
        self,
        *,
        trace_id: str,
        channel_id: str,
        status: str,
        conversation_id: str = "",
        user_id: str = "",
        message_id: str = "",
        event_type: str = "message",
        raw_event: dict | None = None,
        metadata: dict | None = None,
        error: str = "",
    ) -> int:
        """插入事件记录，返回自增 ID"""
        now = datetime.now().isoformat()
        raw_json = json.dumps(raw_event, ensure_ascii=False) if raw_event else None
        meta_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                INSERT INTO {TABLE_EVENTS}
                (trace_id, channel_id, conversation_id, user_id, message_id,
                 event_type, status, raw_event_json, metadata_json, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id, channel_id, conversation_id, user_id, message_id,
                    event_type, status, raw_json, meta_json, error, now,
                ),
            )
            return cursor.lastrowid

    def event_update_status(self, trace_id: str, status: str, error: str = "") -> None:
        """更新事件状态"""
        with self._connect() as conn:
            conn.execute(
                f"UPDATE {TABLE_EVENTS} SET status = ?, error = ? WHERE trace_id = ?",
                (status, error, trace_id),
            )

    def event_get_by_trace(self, trace_id: str) -> list[dict]:
        """根据 trace_id 查询事件完整链路（按时间排序）"""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {TABLE_EVENTS} WHERE trace_id = ? ORDER BY id",
                (trace_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def event_get_latest_by_trace(self, trace_id: str) -> dict | None:
        """根据 trace_id 查询最新一条事件"""
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM {TABLE_EVENTS} WHERE trace_id = ? ORDER BY id DESC",
                (trace_id,),
            ).fetchone()
            return dict(row) if row else None

    def event_query(
        self,
        *,
        channel_id: str = "",
        status: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """查询事件列表（支持按频道和状态筛选）"""
        conditions = []
        params: list = []
        if channel_id:
            conditions.append("channel_id = ?")
            params.append(channel_id)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {TABLE_EVENTS}{where}"
                f" ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
            return [dict(r) for r in rows]

    def event_cleanup(self, *, keep_days: int = 30, failed_keep_days: int = 90) -> int:
        """清理旧的事件日志

        Args:
            keep_days: 普通事件保留天数
            failed_keep_days: 失败事件保留天数
        """
        normal_cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat()
        failed_cutoff = (datetime.now() - timedelta(days=failed_keep_days)).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                f"DELETE FROM {TABLE_EVENTS} "
                f"WHERE (status NOT IN ('failed', 'parse_failed', 'dispatch_failed', 'delivery_failed') "
                f"AND created_at < ?) "
                f"OR created_at < ?",
                (normal_cutoff, failed_cutoff),
            )
            count = cursor.rowcount
        if count:
            _log.debug("[Storage] 清理旧事件记录 count=%d", count)
        return count

    def event_count(self) -> int:
        """获取事件总数"""
        with self._connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM {TABLE_EVENTS}").fetchone()
            return row["cnt"] if row else 0

    # ========================
    # Deliveries（投递）操作
    # ========================

    def delivery_insert(
        self,
        *,
        trace_id: str,
        channel_id: str,
        conversation_id: str,
        status: str = "pending",
        content: str = "",
        request_json: dict | None = None,
        response_json: dict | None = None,
        error: str = "",
    ) -> int:
        """插入投递记录，返回自增 ID"""
        now = datetime.now().isoformat()
        req_json = json.dumps(request_json, ensure_ascii=False) if request_json else None
        res_json = json.dumps(response_json, ensure_ascii=False) if response_json else None
        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                INSERT INTO {TABLE_DELIVERIES}
                (trace_id, channel_id, conversation_id, status, content,
                 request_json, response_json, error, attempts, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (trace_id, channel_id, conversation_id, status, content,
                 req_json, res_json, error, now, now),
            )
            return cursor.lastrowid

    def delivery_update_status(
        self,
        delivery_id: int | str,
        status: str,
        error: str = "",
        increment_attempts: bool = False,
    ) -> None:
        """更新投递状态"""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            if increment_attempts:
                conn.execute(
                    f"UPDATE {TABLE_DELIVERIES} "
                    f"SET status = ?, error = ?, updated_at = ?, attempts = attempts + 1 "
                    f"WHERE id = ?",
                    (status, error, now, delivery_id),
                )
            else:
                conn.execute(
                    f"UPDATE {TABLE_DELIVERIES} "
                    f"SET status = ?, error = ?, updated_at = ? "
                    f"WHERE id = ?",
                    (status, error, now, delivery_id),
                )

    def delivery_update_by_trace(self, trace_id: str, status: str, error: str = "") -> None:
        """根据 trace_id 更新投递状态"""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                f"UPDATE {TABLE_DELIVERIES} "
                f"SET status = ?, error = ?, updated_at = ?, attempts = attempts + 1 "
                f"WHERE trace_id = ?",
                (status, error, now, trace_id),
            )

    def delivery_get_by_trace(self, trace_id: str) -> dict | None:
        """根据 trace_id 查询投递记录"""
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM {TABLE_DELIVERIES} WHERE trace_id = ? ORDER BY id DESC",
                (trace_id,),
            ).fetchone()
            return dict(row) if row else None

    def delivery_query(
        self,
        *,
        channel_id: str = "",
        status: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """查询投递记录列表"""
        conditions = []
        params: list = []
        if channel_id:
            conditions.append("channel_id = ?")
            params.append(channel_id)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {TABLE_DELIVERIES}{where}"
                f" ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
            return [dict(r) for r in rows]

    def delivery_cleanup(self, *, keep_days: int = 30) -> int:
        """清理旧的投递记录"""
        cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                f"DELETE FROM {TABLE_DELIVERIES} WHERE created_at < ?",
                (cutoff,),
            )
            count = cursor.rowcount
        if count:
            _log.debug("[Storage] 清理旧投递记录 count=%d", count)
        return count

    def delivery_count(self) -> int:
        """获取投递记录总数"""
        with self._connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM {TABLE_DELIVERIES}").fetchone()
            return row["cnt"] if row else 0

    # ========================
    # 通用维护
    # ========================

    def get_stats(self) -> dict[str, Any]:
        """获取存储统计信息"""
        with self._connect() as conn:
            dedupe_count = conn.execute(f"SELECT COUNT(*) as cnt FROM {TABLE_DEDUPE}").fetchone()["cnt"]
            events_count = conn.execute(f"SELECT COUNT(*) as cnt FROM {TABLE_EVENTS}").fetchone()["cnt"]
            deliveries_count = conn.execute(f"SELECT COUNT(*) as cnt FROM {TABLE_DELIVERIES}").fetchone()["cnt"]

        db_size = 0
        if os.path.exists(self._db_path):
            db_size = os.path.getsize(self._db_path)

        return {
            "db_path": self._db_path,
            "db_size_bytes": db_size,
            "dedupe_count": dedupe_count,
            "events_count": events_count,
            "deliveries_count": deliveries_count,
        }

    def vacuum(self) -> None:
        """压缩数据库文件"""
        with self._connect() as conn:
            conn.execute("VACUUM")
        _log.info("[Storage] 数据库压缩完成")


def init_gateway_storage(data_dir: str = "") -> GatewayStorage:
    """工厂函数：创建并初始化 Gateway 存储

    Args:
        data_dir: 数据目录，默认为 data/

    Returns:
        初始化完成的 GatewayStorage 实例
    """
    return GatewayStorage(data_dir=data_dir)
