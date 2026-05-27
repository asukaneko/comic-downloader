# 内部任务

## 概述

Gateway 支持将心跳、工作流、自定义定时任务等内部调度任务纳入统一的追踪链路，实现执行记录可查、状态可追踪。

## 提交内部任务

```python
from nbot.gateway.gateway import get_gateway

gateway = get_gateway()

# 异步方式
result = await gateway.submit_internal_task(
    task_kind="heartbeat",          # 任务类型
    task_id="heartbeat",            # 任务 ID
    task_name="Heartbeat",          # 任务名称
    handler=my_handler,             # 执行函数（支持 sync/async）
    trigger_source="scheduler",     # 触发来源
    metadata={"target": "session-1"},  # 附加元数据
)

# 同步方式
result = gateway.submit_internal_task_sync(
    task_kind="workflow",
    task_id="wf-1",
    handler=my_handler,
)
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_kind` | str | 是 | 任务类型：`heartbeat` / `workflow` / `scheduled_task` |
| `task_id` | str | 是 | 任务唯一标识 |
| `handler` | callable | 是 | 执行函数，支持同步和异步 |
| `task_name` | str | 否 | 任务显示名称 |
| `trigger_source` | str | 否 | 触发来源，默认 `"system"` |
| `channel_id` | str | 否 | 频道 ID，默认 `"internal"` |
| `metadata` | dict | 否 | 附加元数据，会合并到事件记录中 |

### 返回值

返回 `GatewayResult`，包含 `ok`、`trace_id`、`status`、`data` 等字段。

## 追踪链路

每个内部任务会记录 3 个事件（正常流程）：

```
received ──► dispatched ──► completed
                          └──► failed（异常时）
```

handler 返回的 dict 中的以下字段会被自动提取到元数据：

| 字段 | 说明 |
|------|------|
| `content` | 内容预览 |
| `workflow_id` | 工作流 ID |
| `response_preview` | 响应预览 |
| `target_session_id` / `session_id` | 目标会话 ID |
| `message_count` | 消息数量 |
| `result_summary` | 结果摘要 |

## 内置任务类型

### 心跳（Heartbeat）

由 `WebChatServer._execute_heartbeat()` 提交，通过 Gateway 追踪执行。

```python
# 手动触发心跳
result = await server._execute_heartbeat(force=True)
# result.trace_id 可用于查询执行记录
```

### 工作流（Workflow）

由 `WebChatServer._execute_workflow()` 提交，元数据包含 `workflow_id` 和触发内容。

```python
# 手动触发工作流
result = server._execute_workflow("wf-1", {"source": "manual", "content": "hello"})
```

### 自定义定时任务

由 `WebChatServer._execute_custom_task()` 提交，元数据包含 `target_session_id`。

```python
# 手动触发定时任务
result = server._execute_custom_task("task-1")
```

## 查询执行记录

```python
from nbot.gateway.gateway import get_gateway

gateway = get_gateway()

# 通过 trace_id 查询完整执行链
events = gateway.event_store.get_by_trace(trace_id)

for event in events:
    print(f"{event['status']} - {event['created_at']}")

# 查询所有失败的内部任务
failed = gateway.event_store.query(event_type="internal_task", status="failed")
```
