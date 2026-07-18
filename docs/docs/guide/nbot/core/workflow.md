# workflow - 工作流

## 概述

NekoBot 的工作流是一个**基于 AI + 工具调用的自动化任务执行系统**，由 `nbot/web/server.py` 中的
`WebServer._execute_workflow` 实现。每个工作流绑定一个 agent 会话，触发时把工作流描述作为
用户消息，复用统一的 `AgentHarness`（详见 [agent_service.md](./agent_service.md)）执行多轮
工具调用，最终结果写回会话历史。

## 两个工作流模块的关系

项目中存在两个与工作流相关的模块，定位不同：

### 1. `nbot/web/server.py` — 真实工作流执行（已生效）

实际被调用的工作流实现。`WebServer._execute_workflow` 负责完整流程：

1. **Gateway 提交**（非 gateway 入口时）：通过 `gateway.submit_internal_task_sync` 把
   执行交给 Gateway worker 池，避免阻塞调用方
2. **会话解析**：若工作流未绑定 `session_id` 或会话已丢失，调
   `_create_workflow_session` 创建一个 `session_mode: "agent"` 的会话
3. **消息构建**：
   - system: 工作流 `description`
   - history: 会话历史中的 user/assistant 消息
   - user: 触发消息，格式为 `[工作流触发 - {source}] 任务内容：{content}`
     或 `[工作流触发 - {source}] 请根据以下工作流描述执行任务。触发时间：{time}\n\n{workflow_desc}`
4. **AI + 工具循环**：调用 `run_tool_call_loop(messages, model_call, tool_executor, max_iterations=50)`
   - `model_call` 委托 `WebServer._get_ai_response_with_tools`
   - `tool_executor` 委托 `nbot.services.tools.execute_tool`（统一工具入口）
5. **结果回写**：通过 `_send_workflow_result` 把最终回复写回会话历史、Socket.IO 推送

### 2. `nbot/core/workflow.py` — DAG 引擎占位（未生效）

**当前状态：占位实现，未被主流程调用。** 保留作为未来可能的 DAG 节点图引擎的基础。

已定义但未生效的类：

| 类 | 说明 |
|----|------|
| `WorkflowEngine` | 工作流引擎主体，提供 `execute_workflow` / `list_workflows` 等接口 |
| `Workflow` | 工作流数据模型（name/description/steps/enabled） |
| `WorkflowStep` | 单步定义（action_type/action_data/condition） |
| `WorkflowInstance` | 执行实例（status/logs/context） |
| `TriggerType` | 触发类型枚举（manual/schedule/event/webhook） |
| `WorkflowStatus` | 状态枚举（idle/running/completed/error） |

已实现 4 个 action handler，但 `fetch_data` 和 `condition` 仅 print 不真执行：

- `_action_log` — 记录日志
- `_action_send_message` — 通过 channel adapter 发送消息
- `_action_fetch_data` — **占位**：仅 print
- `_action_condition` — **占位**：仅 print

**不要在主流程中调用 `core/workflow.py` 的 `WorkflowEngine`。** 工作流执行必须走
`WebServer._execute_workflow`。

## 数据模型

工作流以 JSON 对象存储在 `data/web/workflows.json`。字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | 工作流 ID |
| `name` | str | 名称 |
| `description` | str | 工作流描述（作为 system prompt 和触发消息） |
| `prompt` | str | 备用提示词 |
| `enabled` | bool | 是否启用 |
| `session_id` | str | 关联的 agent 会话 ID（懒创建） |
| `config` | object | 模型/工具配置 |
| `trigger` | object | 触发器配置（cron / manual / webhook / event） |
| `last_trace_id` | str | 最近一次 Gateway trace ID |
| `last_gateway_status` | str | 最近一次 Gateway 状态 |

## 触发方式

### 1. 手动触发

```http
POST /api/workflows/{workflow_id}/execute
```

Web 路由：`nbot/web/routes/workflows.py:execute_workflow`

### 2. 定时触发（cron）

`_init_workflow_scheduler` 在 server 启动时读取所有 enabled 工作流的 trigger，若 `type == "cron"`
则用 APScheduler 注册定时任务。到点后调 `_execute_workflow(workflow_id, {"source": "scheduler"})`。

### 3. 消息触发

`trigger_workflow_by_message(conversation_id, content)`：根据会话绑定的 workflow_id 自动触发，
用于"对工作流会话发消息"的场景。

### 4. Hook action 触发

Hook 的 `workflow` action 通过 `HookManager.set_workflow_trigger` 注入的回调把执行路由到
`WebServer._execute_workflow`：

```json
{
  "type": "workflow",
  "workflow": "wf_goodnight_event"
}
```

回调由 `nbot/web/ai_service.py` 在 WebServer 初始化时注入。详见 [hooks/index.md](../hooks/index.md)。

> 注意：早期版本中 `_action_workflow` 直接调用 `core/workflow.py:get_workflow_engine()`，
> 但由于该引擎未实现完整（`fetch_data`/`condition` 仅 print）且未对接 web 数据源，
> 实际从未生效。现已改为通过 callback 路由到 `WebServer._execute_workflow`，
> hook 触发的工作流才能真实执行。

### 5. 任务中心

`nbot/web/routes/task_center.py` 的任务中心可在 UI 触发工作流执行。

## Agent 模式会话

工作流创建的会话对象支持 `session_mode: "agent"` 字段：

```json
{
  "session_id": "wf_xxx",
  "session_mode": "agent"
}
```

启用 agent 模式后：

- `ai_service` 会把 `session_mode` 同步到 `ctx.metadata`，`AIPipeline` 通过 `ModePolicy`
  据此识别 agent 模式会话（详见 [ai_pipeline.md](./ai_pipeline.md)）
- agent 模式下自动**跳过角色记忆注入**（`character.memories_legacy` / `MemoryFS` 等），
  避免上下文污染
- 定时触发使用工作流自身描述/提示作为用户消息，移除系统提示中多余的 `CORE_INSTRUCTIONS`
- 工具调用循环统一复用 `AgentHarness`，与主对话/CLI 保持同一套错误处理与退出语义

该模式适合让工作流会话以「无角色身份」的方式直接响应调度系统，绕开角色卡片的情感/状态/记忆层。

## Web 界面

工作流可以在 Web 后台的管理界面中创建和编辑：

- 编辑工作流名称、描述、提示词
- 配置触发器（cron 表达式 / 手动 / 消息触发）
- 启用/禁用工作流
- 查看执行历史与 Gateway trace

## 相关代码

| 模块 | 文件 | 关键函数 |
|------|------|----------|
| 工作流执行 | `nbot/web/server.py` | `WebServer._execute_workflow` |
| 工作流会话 | `nbot/web/server.py` | `WebServer._create_workflow_session` |
| 工作流调度 | `nbot/web/server.py` | `WebServer._init_workflow_scheduler` / `_schedule_workflow` |
| 消息触发 | `nbot/web/server.py` | `WebServer.trigger_workflow_by_message` |
| Hook 集成 | `nbot/hooks/manager.py` | `HookManager.set_workflow_trigger` |
| Hook action | `nbot/hooks/actions.py` | `ActionExecutor._action_workflow` |
| Web 路由 | `nbot/web/routes/workflows.py` | `register_workflow_routes` |
| 工具执行 | `nbot/services/tools.py` | `execute_tool`（统一入口） |
| Agent harness | `nbot/core/agent_service.py` | `AgentHarness` |
| **DAG 引擎占位** | `nbot/core/workflow.py` | `WorkflowEngine`（未生效，保留作未来扩展） |
