"""Gateway 内部事件总线

基于发布/订阅模式的轻量级事件总线，
用于 Gateway 内部各组件之间的解耦通信。

支持：
- 主题（topic）模式匹配
- 同步和异步订阅者
- 事件历史记录
- 订阅者管理
"""

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

_log = logging.getLogger(__name__)

# 默认事件历史最大条数
_DEFAULT_HISTORY_MAX = 100


class EventBusTopic(StrEnum):
    """预定义的事件主题"""

    # Gateway 生命周期
    GATEWAY_STARTED = "gateway.started"
    GATEWAY_STOPPED = "gateway.stopped"
    GATEWAY_ERROR = "gateway.error"

    # 事件处理
    EVENT_RECEIVED = "event.received"
    EVENT_VERIFIED = "event.verified"
    EVENT_PARSED = "event.parsed"
    EVENT_DEDUPE_CHECKED = "event.dedupe_checked"
    EVENT_DISPATCHED = "event.dispatched"
    EVENT_DELIVERED = "event.delivered"
    EVENT_FAILED = "event.failed"
    EVENT_QUEUED = "event.queued"

    # 队列相关
    QUEUE_ENQUEUED = "queue.enqueued"
    QUEUE_DEQUEUED = "queue.dequeued"
    QUEUE_FULL = "queue.full"

    # Worker 相关
    WORKER_STARTED = "worker.started"
    WORKER_STOPPED = "worker.stopped"
    WORKER_ITEM_COMPLETED = "worker.item_completed"
    WORKER_ITEM_FAILED = "worker.item_failed"

    # 节点控制面
    NODE_REGISTERED = "node.registered"
    NODE_UNREGISTERED = "node.unregistered"
    NODE_HEARTBEAT = "node.heartbeat"
    NODE_OFFLINE = "node.offline"

    # 安全相关
    SECURITY_VIOLATION = "security.violation"
    RATE_LIMIT_EXCEEDED = "rate_limit.exceeded"


@dataclass
class BusEvent:
    """事件总线中的事件对象"""

    topic: str
    data: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    timestamp: float = 0.0
    event_id: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()
        if not self.event_id:
            import uuid

            self.event_id = f"evt_{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "topic": self.topic,
            "source": self.source,
            "timestamp": self.timestamp,
            "data": self.data,
        }


class Subscriber:
    """订阅者包装器"""

    def __init__(
        self,
        callback: Callable[[BusEvent], Any] | Callable[[BusEvent], Coroutine],
        *,
        name: str = "",
        filter_topic: str | None = None,
        once: bool = False,
    ):
        self.callback = callback
        self.name = name or getattr(callback, "__name__", "anonymous")
        self.filter_topic = filter_topic
        self.once = once
        self.call_count = 0


class EventBus:
    """内部事件总线

    支持同步/异步混合订阅者、主题模式匹配、事件历史。
    """

    def __init__(self, *, history_max: int = _DEFAULT_HISTORY_MAX):
        self._subscribers: dict[str, list[Subscriber]] = {}
        self._history: list[BusEvent] = []
        self._history_max = history_max
        self._total_published = 0
        self._total_delivered = 0

    async def publish(self, topic: str, data: dict[str, Any] | None = None, *, source: str = "") -> int:
        """发布事件到指定主题

        Args:
            topic: 事件主题
            data: 事件数据
            source: 事件来源标识

        Returns:
            成功投递的订阅者数量
        """
        event = BusEvent(topic=topic, data=data or {}, source=source)

        # 记录历史
        self._history.append(event)
        if len(self._history) > self._history_max:
            self._history.pop(0)
        self._total_published += 1

        # 查找匹配的订阅者
        matched_subscribers = self._match_subscribers(topic)
        if not matched_subscribers:
            _log.debug("[EventBus] 无订阅者 topic=%s", topic)
            return 0

        delivered = 0
        to_remove: list[tuple[str, Subscriber]] = []

        for sub in matched_subscribers:
            try:
                result = sub.callback(event)
                if asyncio.iscoroutine(result):
                    await result
                sub.call_count += 1
                delivered += 1
                self._total_delivered += 1

                if sub.once:
                    to_remove.append((topic, sub))
            except Exception as e:
                _log.error(
                    "[EventBus] 订阅者回调异常 topic=%s subscriber=%s error=%s",
                    topic,
                    sub.name,
                    str(e),
                )

        # 移除一次性订阅者
        for t, sub in to_remove:
            self.unsubscribe(t, sub)

        return delivered

    def subscribe(
        self,
        topic_pattern: str,
        callback: Callable[[BusEvent], Any] | Callable[[BusEvent], Coroutine],
        *,
        name: str = "",
        once: bool = False,
    ) -> Subscriber:
        """订阅主题

        支持：
        - 精确匹配："event.received"
        - 通配符前缀："event.*" 匹配 event.received, event.failed 等
        - 全通配符："*" 匹配所有主题

        Returns:
            Subscriber 对象（可用于取消订阅）
        """
        sub = Subscriber(
            callback=callback,
            name=name,
            filter_topic=topic_pattern,
            once=once,
        )
        if topic_pattern not in self._subscribers:
            self._subscribers[topic_pattern] = []
        self._subscribers[topic_pattern].append(sub)
        _log.debug("[EventBus] 新订阅 topic=%s subscriber=%s", topic_pattern, sub.name)
        return sub

    def unsubscribe(self, topic_pattern: str, subscriber: Subscriber | None = None) -> bool:
        """取消订阅"""
        if topic_pattern not in self._subscribers:
            return False

        if subscriber is None:
            del self._subscribers[topic_pattern]
            _log.debug("[EventBus] 清除全部订阅 topic=%s", topic_pattern)
            return True

        try:
            self._subscribers[topic_pattern].remove(subscriber)
            if not self._subscribers[topic_pattern]:
                del self._subscribers[topic_pattern]
            _log.debug("[EventBus] 取消订阅 topic=%s subscriber=%s", topic_pattern, subscriber.name)
            return True
        except ValueError:
            return False

    def on(
        self,
        topic_pattern: str,
        *,
        name: str = "",
        once: bool = False,
    ):
        """装饰器方式注册订阅者

        使用方式：
            @event_bus.on("event.received")
            def handle_event(event: BusEvent):
                print(f"收到事件: {event.topic}")
        """

        def decorator(func):
            self.subscribe(topic_pattern, func, name=name or func.__name__, once=once)
            return func

        return decorator

    def _match_subscribers(self, topic: str) -> list[Subscriber]:
        """查找匹配指定主题的所有订阅者"""
        matched: list[Subscriber] = []
        for pattern, subs in self._subscribers.items():
            if self._match_topic(pattern, topic):
                matched.extend(subs)
        return matched

    @staticmethod
    def _match_topic(pattern: str, topic: str) -> bool:
        """主题模式匹配"""
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return topic.startswith(prefix + ".") or topic == prefix[:-1]
        return pattern == topic

    def get_history(
        self,
        *,
        topic: str = "",
        limit: int = 50,
        since: float | None = None,
    ) -> list[dict[str, Any]]:
        """查询事件历史

        Args:
            topic: 按主题筛选（可选）
            limit: 最大返回数量
            since: 起始时间戳

        Returns:
            事件字典列表
        """
        events = self._history
        if since:
            events = [e for e in events if e.timestamp >= since]
        if topic:
            events = [e for e in events if e.topic == topic]

        result = events[-limit:] if len(events) > limit else events
        return [e.to_dict() for e in reversed(result)]

    def get_stats(self) -> dict[str, Any]:
        """获取事件总线统计信息"""
        total_subs = sum(len(s) for s in self._subscribers.values())
        return {
            "topics_registered": len(self._subscribers),
            "total_subscribers": total_subs,
            "total_published": self._total_published,
            "total_delivered": self._total_delivered,
            "history_size": len(self._history),
            "history_max": self._history_max,
            "topics": list(self._subscribers.keys()),
        }

    def clear_history(self) -> None:
        """清空事件历史"""
        self._history.clear()


# 全局默认事件总线实例
_default_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """获取全局默认事件总线实例"""
    global _default_event_bus
    if _default_event_bus is None:
        _default_event_bus = EventBus()
    return _default_event_bus
