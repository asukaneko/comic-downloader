# 队列与投递

## 事件队列

异步模式下，事件经前 6 步处理后入队，由后台 Worker 消费。

### MemoryEventQueue

基于 `asyncio.Queue` 的内存队列：

- 最大容量：1000 条
- 支持按 item_id 追踪所有队列项
- 支持优先级重入队（用于重试）
- 死信处理：超过 `max_attempts` 的项目转为 DEAD 状态

### QueueItem 状态流转

```
PENDING ──► PROCESSING ──► COMPLETED
                │
                ├──► FAILED ──► (重试) ──► PENDING
                │
                └──► DEAD (超过最大重试次数)
```

### 统计信息

```python
stats = gateway.queue.get_stats()
# => {
#     "enqueued": 1234,
#     "completed": 1200,
#     "failed": 30,
#     "dead": 4,
#     "status_breakdown": {"PENDING": 5, "PROCESSING": 1}
# }
```

## 后台 Worker

`GatewayWorker` 是异步模式的后台消费者：

- 持续出队循环，空闲超时默认 30 秒
- 处理延迟重试：将带 `next_retry_at` 的项目重新入队
- 完整处理管线：路由 → 解析 → 构建 ChatRequest → 分发 AI Core → 投递回复 → 标记去重
- 优雅关闭：等待当前项目处理完毕
- 错误分类处理：可恢复错误触发重试，不可恢复错误直接进入死信

```python
await gateway.start_worker()
# ... 处理消息 ...
await gateway.stop_worker(graceful=True)
```

## 回复投递

`GatewayDelivery` 负责将 AI 回复发送回各频道。

### 注册发送函数

```python
from nbot.gateway.delivery import GatewayDelivery

delivery = GatewayDelivery()

# 为每个频道注册发送函数
delivery.register_sender("qq", qq_send_func)
delivery.register_sender("telegram", telegram_send_func)
```

### 长文本自动分片

超过 4000 字符的回复会自动按优先级分割：

1. 双换行符（段落边界）
2. 句号/问号/感叹号
3. 逗号
4. 空格

每片带有 `chunk_index` / `chunk_total` 元数据。

### Markdown 转纯文本

对于不支持 Markdown 的频道，自动转换：

- 标题 → 加粗文本
- `**粗体**` / `*斜体*` → 纯文本
- 代码块 → 缩进文本
- 链接 `[text](url)` → `text (url)`
- 列表 → 带前缀的文本

### 投递状态

| 状态 | 说明 |
|------|------|
| `pending` | 等待发送 |
| `sending` | 发送中 |
| `delivered` | 发送成功 |
| `built` | 消息已构建但未发送（Web/内部频道） |
| `no_sender` | 无可用发送函数 |
| `failed` | 发送失败 |
| `partial_failed` | 部分分片发送失败 |
| `dead` | 超过最大重试次数 |

## 重试机制

`RetryHandler` 基于错误分类决定是否重试：

### 错误分类

| 分类 | 示例 | 行为 |
|------|------|------|
| `RECOVERABLE` | 超时、连接错误、502/503/504 | 重试 |
| `NON_RECOVERABLE` | 签名无效、未知频道、限流、重复消息 | 不重试 |
| `UNKNOWN` | 未识别的错误 | 重试（视为可恢复） |

### 退避策略

指数退避 + 抖动：

```
delay = min(base_delay × 2^(attempt-1), max_delay) + jitter
```

默认配置：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 最大重试次数 | 3 | `max_attempts` |
| 基础延迟 | 1 秒 | `base_delay` |
| 最大延迟 | 60 秒 | `max_delay` |
| 抖动 | 启用 | `jitter` |
