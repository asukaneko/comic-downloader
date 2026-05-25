"""Gateway 投递存储

负责记录回复投递的状态和结果。

投递状态流转：
  pending → sending → delivered
                  → failed → (retry) → sending → ...
                  → failed → ... → dead（超过最大重试次数）
"""

import logging
from typing import Any

if __name__ == "TYPE_CHECKING":
    from nbot.gateway.storage import GatewayStorage

_log = logging.getLogger(__name__)

# 默认最大重试次数
_DEFAULT_MAX_RETRIES = 3


class DeliveryStore:
    """投递状态持久化与查询"""

    def __init__(self, storage: "GatewayStorage"):
        self._storage = storage

    def create(
        self,
        *,
        trace_id: str,
        channel_id: str,
        conversation_id: str,
        content: str = "",
        request_data: dict | None = None,
        response_data: dict | None = None,
    ) -> int:
        """创建投递记录（初始状态为 pending）

        Returns:
            新记录 ID
        """
        return self._storage.delivery_insert(
            trace_id=trace_id,
            channel_id=channel_id,
            conversation_id=conversation_id,
            status="pending",
            content=content,
            request_json=request_data,
            response_json=response_data,
        )

    def mark_sending(self, delivery_id: int | str) -> None:
        """标记为正在发送"""
        self._storage.delivery_update_status(delivery_id, "sending")

    def mark_delivered(self, delivery_id: int | str) -> None:
        """标记为发送成功"""
        self._storage.delivery_update_status(delivery_id, "delivered")

    def mark_failed(
        self,
        delivery_id: int | str | None = None,
        trace_id: str = "",
        error: str = "",
        increment_attempts: bool = True,
    ) -> None:
        """标记为发送失败"""
        if delivery_id:
            self._storage.delivery_update_status(
                delivery_id, "failed", error=error, increment_attempts=increment_attempts
            )
        elif trace_id:
            self._storage.delivery_update_by_trace(trace_id, "failed", error=error)

    def mark_dead(self, delivery_id: int | str, error: str = "") -> None:
        """标记为死信（多次重试仍失败）"""
        self._storage.delivery_update_status(delivery_id, "dead", error=error)

    def mark_built(self, delivery_id: int | str, status: str = "built") -> None:
        """标记为已构建消息（但未真实发送，如 Web/内部频道）"""
        self._storage.delivery_update_status(delivery_id, status)

    def get_by_trace(self, trace_id: str) -> dict[str, Any] | None:
        """根据 trace_id 查询投递记录"""
        return self._storage.delivery_get_by_trace(trace_id)

    def get_by_id(self, delivery_id: int | str) -> dict[str, Any] | None:
        """根据 ID 查询投递记录"""
        # 复用 storage 的查询能力
        results = self._storage.delivery_query(limit=1, offset=0)
        for r in results:
            if r["id"] == int(delivery_id):
                return r
        return None

    def query(
        self,
        *,
        channel_id: str = "",
        status: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """查询投递记录列表"""
        return self._storage.delivery_query(
            channel_id=channel_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    def query_failed(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """查询失败的投递记录"""
        return self.query(status="failed", limit=limit)

    def query_dead(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """查询死信记录"""
        return self.query(status="dead", limit=limit)

    def count(self) -> int:
        return self._storage.delivery_count()

    def cleanup(self, *, keep_days: int = 30) -> int:
        """清理旧的投递记录"""
        return self._storage.delivery_cleanup(keep_days=keep_days)
