# 处理管线

## 概述

Gateway 支持同步和异步两种处理模式。同步模式直接在请求线程内完成全部 9 步；异步模式在前 6 步完成后将事件入队，由后台 Worker 异步处理剩余步骤。

## 同步管线（9 步）

```python
result = await gateway.receive(
    channel_id="qq",
    raw_event=event_data,
    headers=headers,
    remote_addr="127.0.0.1",
    raw_body=raw_body,
)
```

| 步骤 | 状态 | 说明 |
|------|------|------|
| 1 | `received` → `verified` | 安全验证（Token / HMAC / IP） |
| 2 | → `rate_limited` | IP 和通道维度限流 |
| 3 | → `unknown_channel` | 路由查找频道适配器 |
| 4 | → `parsed` / `parse_failed` | 适配器解析平台事件 |
| 5 | → `rate_limited` | 用户和会话维度限流 |
| 6 | → `deduped` / `duplicated` | 消息去重检查 |
| 7 | → `dispatched` / `build_request_failed` | 构建 ChatRequest |
| 8 | → `dispatch_failed` | 分发到 AI Core 处理 |
| 9 | → `delivered` / `delivery_failed` | 投递回复到频道 |

## 异步管线（6 步 + 队列）

异步模式下，步骤 1-6 执行完毕后事件入队，立即返回 `200 OK`。

```python
gateway = create_async_gateway_with_storage(data_dir="data")
await gateway.start_worker()

result = await gateway.receive(...)  # 快速返回
# result.queued == True
```

后台 `GatewayWorker` 从队列取出事件，执行步骤 7-9，并支持失败重试。

## GatewayResult

`receive()` 返回 `GatewayResult`：

```python
@dataclass
class GatewayResult:
    ok: bool                    # 是否成功
    trace_id: str               # 追踪 ID
    channel_id: str             # 频道 ID
    conversation_id: str        # 会话 ID
    status: str                 # 最终状态
    ignored: bool = False       # 是否被忽略
    duplicated: bool = False    # 是否重复消息
    queued: bool = False        # 是否已入队（异步模式）
    error: str = ""             # 错误信息
    data: dict = None           # 附加数据
```

## 事件状态一览

管线中可能出现的所有状态：

| 状态 | 含义 |
|------|------|
| `received` | 事件到达网关 |
| `verified` | 安全验证通过 |
| `rate_limited` | 触发限流 |
| `parsed` | 平台事件解析成功 |
| `ignored` | 解析后为空/无关事件 |
| `deduped` | 通过去重检查 |
| `duplicated` | 检测为重复消息 |
| `unknown_channel` | 频道 ID 未注册 |
| `missing_parser` | 适配器缺少 parse_event 方法 |
| `parse_failed` | 平台事件解析异常 |
| `build_request_failed` | 构建 ChatRequest 失败 |
| `dispatched` | 已分发到 AI Core |
| `dispatch_failed` | AI Core 处理失败 |
| `delivering` | 回复投递中 |
| `delivered` | 回复投递成功 |
| `built` | 消息已构建但未发送（Web/内部频道） |
| `no_sender` | 无可用发送函数 |
| `delivery_failed` | 回复投递失败 |
| `partial_failed` | 部分分片投递失败 |
| `queued` | 事件已入队（异步模式） |
| `queue_full` | 队列已满，事件丢弃 |
| `completed` | 内部任务完成 |
| `failed` | 内部任务失败 |

## 错误处理

管线中任何步骤失败都会记录对应的事件状态，并返回包含错误信息的 `GatewayResult`。详细的错误类型参见 [节点控制平面 - 错误体系](./nodes.md#错误体系)。
