"""Gateway 异步事件队列

解决慢模型、长上下文、工具调用等场景下 Webhook 超时的问题。

核心流程：
  Webhook 收到事件 → 验证/解析/去重 → 入队 → 立即返回 200 OK
  Worker 后台消费 → 调度 AI Core → 投递回复 → 记录结果

队列接口设计为可替换：
- 第一版：内存 asyncio.Queue（适合单实例）
- 后续可替换为：Redis Stream / NATS / RabbitMQ 等
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

_log = logging.getLogger(__name__)


class QueueItemStatus(StrEnum):
    """队列项处理状态"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"


@dataclass
class QueueItem:
    """队列中的事件项

    包含原始事件数据和处理状态元信息。
    """

    item_id: str = ""
    trace_id: str = ""
    channel_id: str = ""
    raw_event: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    remote_addr: str = ""
    parsed_data: dict | None = None
    chat_request: Any | None = None

    # 状态与重试
    status: QueueItemStatus = QueueItemStatus.PENDING
    attempt: int = 0
    max_attempts: int = 3
    error: str = ""

    # 时间戳
    created_at: float = 0.0
    started_at: float | None = None
    completed_at: float | None = None
    next_retry_at: float | None = None

    # 结果
    result: dict | None = None

    def __post_init__(self):
        if not self.item_id:
            self.item_id = f"qi_{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = time.time()

    @property
    def is_expired(self) -> bool:
        """检查是否已超过最大重试次数"""
        return self.attempt >= self.max_attempts

    @property
    def is_ready_for_retry(self) -> bool:
        """检查是否可以重试"""
        if self.status != QueueItemStatus.FAILED:
            return False
        if self.is_expired:
            return False
        if self.next_retry_at and time.time() < self.next_retry_at:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "trace_id": self.trace_id,
            "channel_id": self.channel_id,
            "status": self.status.value,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "error": self.error,
            "created_at": self.created_at,
        }


class MemoryEventQueue:
    """基于内存的异步事件队列

    使用 asyncio.Queue 实现，支持优先级（失败重试 > 新消息）。
    """

    def __init__(self, *, max_size: int = 1000):
        self._queue: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=max_size)
        self._max_size = max_size
        # 存储所有 item 的引用（用于查询和重试管理）
        self._items: dict[str, QueueItem] = {}
        # 统计
        self._total_enqueued = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_dead = 0

    async def enqueue(self, item: QueueItem) -> bool:
        """将事件入队

        Returns:
            True 表示入队成功，False 表示队列已满
        """
        if self._queue.full():
            _log.warning("[Queue] 队列已满，丢弃事件 trace=%s", item.trace_id)
            return False

        await self._queue.put(item)
        self._items[item.item_id] = item
        self._total_enqueued += 1
        _log.debug(
            "[Queue] 入队成功 item=%s trace=%s channel=%s queue_size=%d",
            item.item_id,
            item.trace_id,
            item.channel_id,
            self.size,
        )
        return True

    async def dequeue(self, timeout: float | None = None) -> QueueItem | None:
        """从队列中取出一个事件

        Args:
            timeout: 最大等待时间（秒），None 表示无限等待

        Returns:
            QueueItem 或 None（超时）
        """
        try:
            if timeout is not None:
                item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            else:
                item = await self._queue.get()
            return item
        except TimeoutError:
            return None

    def get_item(self, item_id: str) -> QueueItem | None:
        """根据 ID 获取队列项"""
        return self._items.get(item_id)

    def update_item(self, item_id: str, **kwargs) -> None:
        """更新队列项属性"""
        item = self._items.get(item_id)
        if item:
            for k, v in kwargs.items():
                if hasattr(item, k):
                    setattr(item, k, v)

    def mark_processing(self, item: QueueItem) -> None:
        """标记为正在处理"""
        item.status = QueueItemStatus.PROCESSING
        item.attempt += 1
        item.started_at = time.time()

    def mark_completed(self, item: QueueItem, result: dict | None = None) -> None:
        """标记为处理完成"""
        item.status = QueueItemStatus.COMPLETED
        item.completed_at = time.time()
        item.result = result
        self._total_completed += 1

    def mark_failed(self, item: QueueItem, error: str = "", next_retry_at: float | None = None) -> None:
        """标记为处理失败"""
        if item.is_expired:
            # 超过最大重试次数，进入死信
            item.status = QueueItemStatus.DEAD
            item.error = error or "max attempts exceeded"
            item.completed_at = time.time()
            self._total_dead += 1
            _log.warning(
                "[Queue] 进入死信 item=%s trace=%s attempts=%d/%d error=%s",
                item.item_id,
                item.trace_id,
                item.attempt,
                item.max_attempts,
                item.error,
            )
        else:
            item.status = QueueItemStatus.FAILED
            item.error = error
            item.next_retry_at = next_retry_at
            self._total_failed += 1
            # 重新入队等待重试
            try:
                self._queue.put_nowait(item)
            except asyncio.QueueFull:
                _log.error("[Queue] 重试入队失败（队列满）item=%s", item.item_id)

    @property
    def size(self) -> int:
        """当前队列中的待处理数量"""
        return self._queue.qsize()

    @property
    def total_items(self) -> int:
        """总跟踪条目数"""
        return len(self._items)

    def get_stats(self) -> dict[str, Any]:
        """获取队列统计信息"""
        pending = sum(1 for i in self._items.values() if i.status == QueueItemStatus.PENDING)
        processing = sum(1 for i in self._items.values() if i.status == QueueItemStatus.PROCESSING)
        failed = sum(1 for i in self._items.values() if i.status == QueueItemStatus.FAILED)
        dead = sum(1 for i in self._items.values() if i.status == QueueItemStatus.DEAD)

        return {
            "queue_size": self.size,
            "total_tracked": len(self._items),
            "total_enqueued": self._total_enqueued,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "total_dead": self._total_dead,
            "status_breakdown": {
                "pending": pending,
                "processing": processing,
                "failed": failed,
                "dead": dead,
            },
        }

    def cleanup(self, *, max_age_seconds: float = 3600) -> int:
        """清理已完成/死信的旧条目

        Args:
            max_age_seconds: 保留最近多长时间的记录

        Returns:
            清理数量
        """
        cutoff = time.time() - max_age_seconds
        to_remove = [
            iid for iid, item in self._items.items()
            if item.status in (QueueItemStatus.COMPLETED, QueueItemStatus.DEAD)
            and (item.completed_at or 0) < cutoff
        ]
        for iid in to_remove:
            del self._items[iid]
        if to_remove:
            _log.debug("[Queue] 清理旧条目 count=%d", len(to_remove))
        return len(to_remove)


class EventQueue:
    """事件队列统一接口

    第一版委托给 MemoryEventQueue，
    后续可替换为 Redis Stream / NATS 等实现。
    """

    def __init__(self, queue: MemoryEventQueue | None = None):
        self._queue = queue or MemoryEventQueue()

    async def enqueue(self, item: QueueItem) -> bool:
        return await self._queue.enqueue(item)

    async def dequeue(self, timeout: float | None = None) -> QueueItem | None:
        return await self._queue.dequeue(timeout)

    def get_item(self, item_id: str) -> QueueItem | None:
        return self._queue.get_item(item_id)

    def mark_processing(self, item: QueueItem) -> None:
        self._queue.mark_processing(item)

    def mark_completed(self, item: QueueItem, result: dict | None = None) -> None:
        self._queue.mark_completed(item, result)

    def mark_failed(self, item: QueueItem, error: str = "", next_retry_at: float | None = None) -> None:
        self._queue.mark_failed(item, error, next_retry_at)

    @property
    def size(self) -> int:
        return self._queue.size

    def get_stats(self) -> dict[str, Any]:
        return self._queue.get_stats()
