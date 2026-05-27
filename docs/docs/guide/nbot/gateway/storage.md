# 存储与追踪

## SQLite 持久化

`GatewayStorage` 使用 SQLite（默认路径 `data/gateway.db`）存储 3 张核心表。

### gateway_events — 事件生命周期

记录消息和内部任务在管线中每一步的状态变化。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `trace_id` | TEXT | 追踪 ID，索引 |
| `channel_id` | TEXT | 频道 ID |
| `conversation_id` | TEXT | 会话 ID |
| `user_id` | TEXT | 用户 ID |
| `message_id` | TEXT | 消息 ID |
| `event_type` | TEXT | `message` / `internal_task` / `operation` |
| `status` | TEXT | 事件状态 |
| `raw_event_json` | TEXT | 原始事件 JSON |
| `metadata_json` | TEXT | 元数据 JSON |
| `error` | TEXT | 错误信息 |
| `created_at` | TEXT | 创建时间 |

```python
# 查询某条消息的完整追踪链
events = gateway.event_store.get_by_trace("gw_20260525_153000_a1b2c3d4")

# 按条件查询
events = gateway.event_store.query(
    channel_id="qq",
    status="failed",
    event_type="message",
    limit=50,
)
```

### gateway_deliveries — 回复投递记录

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `trace_id` | TEXT | 追踪 ID |
| `channel_id` | TEXT | 频道 ID |
| `conversation_id` | TEXT | 会话 ID |
| `status` | TEXT | `pending` / `sending` / `delivered` / `failed` / `dead` |
| `content` | TEXT | 回复内容 |
| `request_json` | TEXT | 请求数据 |
| `response_json` | TEXT | 响应数据 |
| `error` | TEXT | 错误信息 |
| `attempts` | INTEGER | 重试次数 |
| `created_at` | TEXT | 创建时间 |
| `updated_at` | TEXT | 更新时间 |

### gateway_dedupe — 去重记录

| 字段 | 类型 | 说明 |
|------|------|------|
| `dedupe_key` | TEXT PK | 去重 key |
| `channel_id` | TEXT | 频道 ID |
| `message_id` | TEXT | 消息 ID |
| `created_at` | TEXT | 创建时间 |
| `expires_at` | TEXT | 过期时间，索引 |

### 数据清理

```python
# 清理 30 天前的事件（失败事件保留 90 天）
gateway.storage.event_cleanup(keep_days=30, failed_keep_days=90)

# 清理 30 天前的投递记录
gateway.storage.delivery_cleanup(keep_days=30)

# 清理过期去重记录
gateway.storage.dedupe_cleanup_expired()

# 压缩数据库
gateway.storage.vacuum()
```

### 统计信息

```python
stats = gateway.storage.get_stats()
# => {
#     "events": {"count": 12345, "file_size_mb": 12.3},
#     "deliveries": {"count": 890, "file_size_mb": 5.1},
#     "dedupe": {"count": 234, "file_size_mb": 0.5},
# }
```

## 追踪链路

### TraceFactory

生成格式为 `gw_{YYYYMMDD}_{HHMMSS}_{8位hex}` 的追踪 ID：

```python
from nbot.gateway.trace import TraceFactory

factory = TraceFactory(prefix="gw")
trace_id = factory.new_trace_id()
# => "gw_20260525_153000_a1b2c3d4"
```

### 线程上下文

使用 `trace_context` 上下文管理器，确保同一处理管线内的所有日志携带相同 trace_id：

```python
from nbot.gateway.trace import trace_context, get_current_trace_id

with trace_context(trace_id):
    # 此作用域内 get_current_trace_id() 返回该 trace_id
    do_something()
```

### 事件元数据

`_record_event()` 自动记录：`trace_id`、`channel_id`、`status`、`conversation_id`、`user_id`、`message_id`、`event_type`、`raw_event`、`error`、`metadata`（自动合并 `remote_addr`）。
