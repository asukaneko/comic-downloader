# MCP Tools 参考

## 概述

MCP Tools 是"会产生动作"的能力，适合包装查询、发送、重试、注册等操作。

所有工具返回 JSON 字符串，包含 `ok` 字段表示是否成功。

## 只读工具

### gateway_get_status

查看 Gateway 健康状态。

**输入**：无参数

**输出示例**：
```json
{
  "ok": true,
  "mode": "async",
  "storage": "sqlite",
  "worker_running": true,
  "queue": {
    "pending": 3,
    "processing": 1,
    "dead": 0
  }
}
```

### gateway_get_stats

查看事件、投递、去重、队列统计。

**输入**：无参数

**输出示例**：
```json
{
  "ok": true,
  "events": {"count": 12345},
  "deliveries": {"count": 890},
  "dedupe": {"count": 234},
  "queue": {
    "enqueued": 1234,
    "completed": 1200,
    "failed": 30,
    "dead": 4
  }
}
```

### gateway_query_trace

根据 trace_id 查询完整事件链路。

**输入**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| trace_id | string | 是 | Gateway trace id |

**输出示例**：
```json
{
  "ok": true,
  "trace_id": "gw_20260525_153000_a1b2c3d4",
  "events": [
    {"status": "received", "channel_id": "qq", "created_at": "2026-05-25T15:30:00"},
    {"status": "verified", "channel_id": "qq", "created_at": "2026-05-25T15:30:00"},
    {"status": "delivered", "channel_id": "qq", "created_at": "2026-05-25T15:30:03"}
  ]
}
```

### gateway_query_events

按条件查询事件历史。

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| channel_id | string | 否 | "" | 频道 ID 筛选 |
| status | string | 否 | "" | 状态筛选 (failed, delivered, etc.) |
| event_type | string | 否 | "" | 事件类型筛选 |
| limit | int | 否 | 50 | 返回数量上限 |

### gateway_query_deliveries

查询回复投递记录。

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| trace_id | string | 否 | "" | 按 trace_id 查询 |
| channel_id | string | 否 | "" | 频道 ID 筛选 |
| status | string | 否 | "" | 状态筛选 (failed, dead, etc.) |
| limit | int | 否 | 20 | 返回数量上限 |

### gateway_get_queue_stats

查看异步队列状态。

**输入**：无参数

**输出示例**：
```json
{
  "ok": true,
  "enqueued": 1234,
  "completed": 1200,
  "failed": 30,
  "dead": 4,
  "status_breakdown": {
    "pending": 5,
    "processing": 1
  }
}
```

### gateway_list_nodes

列出所有节点。

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| node_type | string | 否 | "" | 节点类型筛选 (gateway, worker, channel) |
| status | string | 否 | "" | 状态筛选 (online, busy, idle, offline) |

### gateway_get_node

获取节点详情。

**输入**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| node_id | string | 是 | 节点 ID |

### gateway_query_logs

查询统一 Gateway 日志。

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| trace_id | string | 否 | "" | 按 trace_id 查询 |
| source | string | 否 | "" | 来源筛选 (gateway, mcp, web) |
| type | string | 否 | "" | 类型筛选 (receive, mcp_tool, message) |
| level | string | 否 | "" | 级别筛选 (info, warning, error) |
| status | string | 否 | "" | 状态筛选 |
| tool_name | string | 否 | "" | MCP 工具名筛选 |
| channel_id | string | 否 | "" | 频道筛选 |
| limit | int | 否 | 100 | 返回数量上限 (1-500) |
| offset | int | 否 | 0 | 偏移量 |

### gateway_lookup_id

自动识别任意 Gateway ID 的类型，返回匹配结果和建议的下一步操作。

**输入**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 任意 Gateway ID |

## 操作型工具

### gateway_receive_message

模拟或提交一条频道消息，让 Gateway 按正常管线处理。

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| channel_id | string | 是 | - | 频道标识符 (qq, web, telegram, etc.) |
| raw_event | dict | 是 | - | 平台原始事件数据 |
| headers | dict | 否 | null | HTTP 请求头 |
| remote_addr | string | 否 | "127.0.0.1" | 请求来源 IP |

**输出示例**：
```json
{
  "ok": true,
  "trace_id": "gw_20260525_153000_a1b2c3d4",
  "status": "queued",
  "queued": true
}
```

### gateway_submit_internal_task

触发内部任务（心跳、工作流、定时任务等）。

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| task_kind | string | 是 | - | 任务类型 (heartbeat, workflow, cron, custom) |
| task_id | string | 是 | - | 任务 ID |
| trigger_source | string | 否 | "mcp" | 触发来源 |
| metadata | dict | 否 | null | 附加元数据 |

## 高危工具

以下工具需要在 `config.ini` 中显式启用。

### gateway_send_message

直接向某个频道投递消息。

**输入**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| channel_id | string | 是 | 频道标识符 |
| conversation_id | string | 是 | 会话 ID |
| content | string | 是 | 消息内容 |
| metadata | dict | 否 | 附加元数据 |

**配置启用**：
```ini
[mcp]
send_message_enabled = true
```

### gateway_retry_dead_letter

重试死信队列中的某个任务。

**输入**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| item_id | string | 是 | 死信队列项 ID |

### gateway_register_node

注册节点。

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| node_id | string | 是 | - | 节点 ID |
| node_type | string | 否 | "worker" | 节点类型 |
| version | string | 否 | "" | 版本号 |
| address | string | 否 | "" | 节点地址 |
| metadata | dict | 否 | null | 附加元数据 |

## 权限模型

| 等级 | 权限 | 说明 |
|------|------|------|
| 只读 | gateway.read, events.query, queue.read, node.read | 查询状态、事件、节点 |
| 操作 | events.publish, channels.send, worker.manage | 触发消息、发送消息、控制 worker |
| 管理 | gateway.manage, queue.manage, node.manage | 重试死信、管理节点、审批配对 |
| 超级管理 | admin | 全部能力 |

本地 stdio 模式默认具有所有权限。

## 错误格式

所有工具返回统一的错误格式：

```json
{
  "ok": false,
  "error": {
    "code": "rate_limited",
    "message": "请求触发限流",
    "stage": "rate_limit",
    "retryable": false,
    "trace_id": "gw_..."
  }
}
```
