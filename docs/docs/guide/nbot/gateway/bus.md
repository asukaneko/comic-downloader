# 事件总线

## 概述

EventBus 是 Gateway 内部的发布/订阅消息总线，用于各组件之间的解耦通信。支持主题模式匹配、同步/异步混合订阅者、事件历史记录。

## 核心概念

### BusEvent

```python
@dataclass
class BusEvent:
    topic: str                         # 事件主题
    data: dict[str, Any]               # 事件数据
    source: str                        # 事件来源标识
    timestamp: float                   # 事件发生时间
    event_id: str                      # 唯一事件 ID（自动生成）
```

事件 ID 格式：`evt_{uuid_hex[:12]}`。

### 主题匹配规则

```
"event.received"      → 精确匹配 event.received
"event.*"             → 前缀匹配 event.received, event.failed, event.parsed 等
"*"                   → 匹配所有主题
```

## 预定义事件主题

### Gateway 生命周期

| 主题 | 说明 |
|------|------|
| `gateway.started` | Gateway 启动 |
| `gateway.stopped` | Gateway 停止 |
| `gateway.error` | Gateway 运行错误 |

### 事件处理管线

| 主题 | 说明 |
|------|------|
| `event.received` | 事件到达 Gateway |
| `event.verified` | 安全验证通过 |
| `event.parsed` | 平台事件解析成功 |
| `event.dedupe_checked` | 去重检查完成 |
| `event.dispatched` | 已分发到 AI Core |
| `event.delivered` | 回复投递成功 |
| `event.failed` | 事件处理失败 |
| `event.queued` | 事件已入队（异步模式） |

### 队列与 Worker

| 主题 | 说明 |
|------|------|
| `queue.enqueued` | 事件入队 |
| `queue.dequeued` | 事件出队 |
| `queue.full` | 队列已满 |
| `worker.started` | Worker 启动 |
| `worker.stopped` | Worker 停止 |
| `worker.item_completed` | 队列项处理完成 |
| `worker.item_failed` | 队列项处理失败 |

### 节点控制面

| 主题 | 说明 |
|------|------|
| `node.registered` | 控制节点注册 |
| `node.unregistered` | 控制节点注销 |
| `node.heartbeat` | 控制节点心跳 |
| `node.offline` | 控制节点离线 |

### 安全相关

| 主题 | 说明 |
|------|------|
| `security.violation` | 安全违规事件 |
| `rate_limit.exceeded` | 限流触发事件 |

## 使用方法

### 发布事件

```python
from nbot.gateway.bus import EventBus, EventBusTopic

bus = EventBus()

# 使用预定义主题
await bus.publish(EventBusTopic.EVENT_RECEIVED, {
    "channel_id": "qq",
    "trace_id": "gw_abc",
})

# 使用自定义主题
await bus.publish("custom.event", {"key": "value"}, source="my_component")
```

`publish()` 返回成功投递的订阅者数量。

### 订阅事件

```python
# 精确匹配
sub = bus.subscribe("event.received", my_handler)

# 通配符前缀
bus.subscribe("event.*", my_handler)

# 全通配符
bus.subscribe("*", my_handler)
```

### 装饰器方式

```python
@event_bus.on("event.received")
def handle_received(event: BusEvent):
    print(f"收到事件: {event.topic}")

@event_bus.on("event.dispatched", once=True)
def handle_first_dispatch(event: BusEvent):
    """一次性订阅：只在第一次 dispatch 时触发"""
```

### 异步订阅者

`EventBus.publish()` 自动检测回调是否为协程：

```python
async def async_handler(event: BusEvent):
    await some_async_work()

bus.subscribe("event.received", async_handler)  # 自动 await
```

### 取消订阅

```python
# 取消特定订阅者
bus.unsubscribe("event.received", sub)

# 清除主题下所有订阅者
bus.unsubscribe("event.received")
```

## 事件历史

EventBus 自动保存最近的事件历史，用于调试和监控：

```python
# 查询最近事件
history = bus.get_history()
history = bus.get_history(topic="event.received", limit=20)
history = bus.get_history(since=timestamp)

# 清空历史
bus.clear_history()
```

## 全局实例

```python
from nbot.gateway.bus import get_event_bus

bus = get_event_bus()  # 获取单例
```

## 统计信息

```python
>>> bus.get_stats()
{
    "topics_registered": 5,         # 已注册主题数
    "total_subscribers": 12,        # 总订阅者数
    "total_published": 1024,        # 总发布事件数
    "total_delivered": 980,         # 总投递成功数
    "history_size": 100,            # 当前历史条数
    "history_max": 100,             # 历史上限
    "topics": ["event.*", "queue.*", "gateway.*"],
}
```

## 与管线集成

EventBus 当前作为 Gateway 的内部基础设施，提供事件驱动的观测能力。典型集成场景：

- Worker 在入队/出队时发布 `queue.*` 事件
- 安全模块检测到违规时发布 `security.violation`
- 控制节点注册/下线时发布 `node.*` 事件
- 用户可以通过订阅 `event.*` 实现自定义的日志、监控、统计逻辑

```python
bus = get_event_bus()

# 监控所有失败事件
bus.subscribe("event.failed", lambda e: alerting.notify(e.data))

# 统计限流触发数
rate_limit_count = 0
bus.subscribe("rate_limit.exceeded", lambda e: increment_count())

# 订阅 Worker 处理结果
bus.subscribe("worker.item_completed", on_worker_done)
```
