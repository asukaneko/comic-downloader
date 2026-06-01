# 存储与追踪

## SQLite 持久化

`GatewayStorage` 使用 SQLite（默认路径 `data/web/gateway.db`）存储核心表。

> **统一日志迁移**：自 v0.2-log 起，`_record_event()` 写入 `gateway_logs`（通过 `GatewayLogService`）。`gateway_events` 仅用于历史兼容。Bot 启动时自动迁移旧数据（一次性，`_gateway_log_migrations` 表标记）。

### gateway_logs — 统一日志（主表）

所有事件、MCP 工具调用统一写入此表。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PK | 日志 ID（`log_{hex16}` 或迁移的 `evt_{id}`） |
| `trace_id` | TEXT | 追踪 ID，索引 |
| `source` | TEXT | 来源：`gateway` / `mcp` / `web` |
| `type` | TEXT | 类型：`receive` / `mcp_tool` / `message` 等 |
| `level` | TEXT | 级别：`info` / `warning` / `error` |
| `stage` | TEXT | 阶段：`receive_start` / `auth_passed` / `parsed` 等 |
| `action` | TEXT | 动作：`receive` / `verify` / `parse` / `dispatch` 等 |
| `status` | TEXT | 状态：`received` / `verified` / `delivered` 等 |
| `message` | TEXT | 描述信息 |
| `tool_name` | TEXT | MCP 工具名（仅 `source=mcp`） |
| `channel_id` | TEXT | 频道 ID |
| `conversation_id` | TEXT | 会话 ID |
| `user_id` / `message_id` | TEXT | 用户/消息 ID |
| `metadata_json` | TEXT | 元数据 JSON（自动脱敏） |
| `error_message` | TEXT | 错误信息 |
| `created_at` | TEXT | 创建时间，索引 |

```python
# 查询
records = gateway.log_service.query(source="gateway", status="delivered", limit=50)

# Trace 聚合（跨 events + deliveries + mcp_logs）
result = gateway.log_service.aggregate_trace(trace_id, ...)

# ID 类型识别
result = gateway.log_service.lookup_id("gw_20260601_xxx", ...)
```

### gateway_events — 事件生命周期（旧表，已迁移）

> **已废弃**：新事件写入 `gateway_logs`。此表仅保留历史数据。

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
# 清理 30 天前的统一日志
gateway.log_service.cleanup(keep_days=30)

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

# 统一日志条数
count = gateway.log_service.count()
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

`_record_event()` 写入 `gateway_logs`（通过 `GatewayLogService`），自动映射 `status` 到 `action`/`stage`/`level`。记录字段：`trace_id`、`channel_id`、`status`、`conversation_id`、`user_id`、`message_id`、`event_type`、`error`、`metadata`（自动合并 `remote_addr`）。
