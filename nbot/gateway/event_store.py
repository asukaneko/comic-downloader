"""Gateway 事件存储

负责记录和查询消息在 Gateway 中的生命周期状态。

事件状态流转：
  received → verified → rate_limited / parsed → deduped
  → queued → dispatched → delivering → delivered
  → failed / dead
"""

import logging
from typing import Any

if __name__ == "TYPE_CHECKING":
    from nbot.gateway.storage import GatewayStorage

_log = logging.getLogger(__name__)


class EventStore:
    """事件持久化与查询

    通过 GatewayStorage 将事件写入 SQLite，
    支持按 trace_id、channel_id、status 查询。
    """

    def __init__(self, storage: "GatewayStorage"):
        self._storage = storage

    def record(
        self,
        *,
        trace_id: str,
        channel_id: str,
        status: str,
        event_type: str = "message",
        conversation_id: str = "",
        user_id: str = "",
        message_id: str = "",
        raw_event: dict | None = None,
        metadata: dict | None = None,
        error: str = "",
    ) -> int:
        """记录一条事件状态变更

        Args:
            trace_id: 追踪 ID
            channel_id: 频道 ID
            status: 当前状态（received/verified/parsed/deduped/delivered/failed 等）
            raw_event: 原始事件数据（仅在 received 时记录）
            error: 错误信息（仅在失败时记录）

        Returns:
            新插入记录的 ID
        """
        return self._storage.event_insert(
            trace_id=trace_id,
            channel_id=channel_id,
            status=status,
            conversation_id=conversation_id,
            user_id=user_id,
            message_id=message_id,
            event_type=event_type,
            raw_event=raw_event,
            metadata=metadata,
            error=error,
        )

    def update_status(self, trace_id: str, status: str, error: str = "") -> None:
        """更新已有事件的状态"""
        self._storage.event_update_status(trace_id, status, error)

    def update_event(
        self,
        *,
        trace_id: str,
        raw_event: dict | None = None,
        metadata: dict | None = None,
    ) -> None:
        """更新已有事件的 raw_event 和 metadata（用于异步回补内容）"""
        self._storage.event_update_event(
            trace_id=trace_id,
            raw_event=raw_event,
            metadata=metadata,
        )

    def get_by_trace(self, trace_id: str) -> list[dict[str, Any]]:
        """根据 trace_id 查询事件完整链路"""
        return self._storage.event_get_by_trace(trace_id)

    def get_latest_by_trace(self, trace_id: str) -> dict[str, Any] | None:
        """根据 trace_id 查询最新一条事件"""
        return self._storage.event_get_latest_by_trace(trace_id)

    def query(
        self,
        *,
        channel_id: str = "",
        status: str = "",
        event_type: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """查询事件列表"""
        return self._storage.event_query(
            channel_id=channel_id,
            status=status,
            event_type=event_type,
            limit=limit,
            offset=offset,
        )

    def count(self) -> int:
        """获取事件总数"""
        return self._storage.event_count()

    def cleanup(self, *, keep_days: int = 30, failed_keep_days: int = 90) -> int:
        """清理旧的事件日志"""
        return self._storage.event_cleanup(keep_days=keep_days, failed_keep_days=failed_keep_days)
