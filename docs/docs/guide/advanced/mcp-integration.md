# MCP 集成指南

## 概述

MCP (Model Context Protocol) 是 Anthropic 推出的开放标准协议，让 AI 智能体能够以统一、安全的方式调用外部工具和获取数据。NekoBot 内置完整的 MCP 支持，将机器人管理能力标准化为 MCP 工具，供 Claude Code、Cursor、ChatGPT Agent 等外部 AI 调用。

## 架构

NekoBot 的 MCP 实现分为两个角色：

### Server 模式（对外暴露工具）

NekoBot 作为 MCP Server，将以下能力暴露为 MCP 工具：

- **Gateway 工具**：消息发送、事件查询、队列管理、节点管理
- **Web 工具**：会话管理、角色卡 CRUD、世界书管理、记忆管理、知识库管理、AI 模型配置

```
AI Agent (Claude Code / Cursor / 其他 MCP 客户端)
        │
        ▼
  NekoBot MCP Server
        │
        ├── Gateway Tools  → 消息、事件、队列、节点
        └── Web Tools      → 会话、角色、世界书、记忆、知识库、AI 模型
        │
        ▼
  NekoBot Core (Gateway + Services + Storage)
```

### Client 模式（连接外部 MCP）

NekoBot 也可以作为 MCP Client，连接外部 MCP 服务，将外部工具接入 AI 的 ReAct 工具链。

```
AI ReAct Loop
    │
    ▼
Tool Registry
    │
    ├── 内置工具（memory、todo 等）
    └── MCP 工具（mcp__<server>__<tool> 格式）
            │
            ▼
    MCPBridge
            │
            ├── Server A (stdio)  ──→  子进程
            ├── Server B (http)   ──→  远程端点
            └── _builtin (stdio)  ──→  本机 MCP Server
```

---

## MCP Server 模式

### 启动方式

```bash
# 仅启动 MCP Server（推荐用于 Claude Code / Cursor）
python bot.py --mcp-only

# 完整模式：Bot + MCP + Web
python bot.py --mcp

# 连接远程 MCP Server（客户端模式）
python bot.py --mcp-connect http://192.168.1.100:5001/mcp
```

### 传输模式

支持两种传输协议：

| 模式 | 配置值 | 适用场景 |
|------|--------|----------|
| stdio | `transport = stdio` | 本地开发，Claude Code / Cursor 集成 |
| streamable-http | `transport = streamable-http` | 远程访问，跨机器调用 |

在 `config.ini` 中配置：

```ini
[mcp]
; 传输模式
transport = stdio

; streamable-http 模式的绑定地址
host = 127.0.0.1
port = 5001
```

### 暴露的工具分类

#### Gateway 工具（只读）

用于查询 Gateway 的状态和数据：

| 工具 | 功能 | 所需权限 |
|------|------|----------|
| `gateway_get_status` | Gateway 健康状态 | gateway.read |
| `gateway_get_stats` | 事件、投递、去重、队列统计 | gateway.read |
| `gateway_get_queue_stats` | 异步队列状态 | queue.read |
| `gateway_query_trace` | 查询事件链路 | events.query |
| `gateway_query_events` | 按条件查询事件历史 | events.query |
| `gateway_query_deliveries` | 查询投递记录 | events.query |
| `gateway_query_logs` | 查询统一日志 | events.query |
| `gateway_list_nodes` | 列出所有节点 | node.read |
| `gateway_get_node` | 获取节点详情 | node.read |
| `gateway_lookup_id` | 自动识别 ID 类型 | events.query |

#### Gateway 工具（操作型）

会产生实际影响的操作：

| 工具 | 功能 | 所需权限 | 高危 |
|------|------|----------|------|
| `gateway_receive_message` | 模拟或提交频道消息 | events.publish | 是 |
| `gateway_send_message` | 直接投递消息 | channels.send | 是 |
| `gateway_submit_internal_task` | 触发内部任务 | worker.manage | 是 |
| `gateway_retry_dead_letter` | 重试死信队列 | queue.manage | 是 |
| `gateway_register_node` | 注册新节点 | node.register | 是 |

#### Web 工具（只读）

| 工具 | 功能 |
|------|------|
| `web_list_sessions` | 列出所有 Web 会话 |
| `web_get_session` | 获取会话详情 |
| `web_get_messages` | 获取会话消息列表 |
| `web_list_characters` | 列出所有角色卡 |
| `web_get_character` | 获取角色卡详情 |
| `web_list_world_books` | 列出所有世界书 |
| `web_get_world_book` | 获取世界书详情 |
| `web_list_memories` | 列出记忆 |
| `web_list_knowledge` | 列出知识库文档 |
| `web_search_knowledge` | 搜索知识库 |
| `web_list_ai_models` | 列出 AI 模型配置 |
| `web_get_active_models` | 获取当前活跃模型 |
| `web_get_token_usage` | 获取 Token 用量统计 |

#### Web 工具（操作型）

| 工具 | 功能 | 高危 |
|------|------|------|
| `web_create_session` | 创建新会话 | 是 |
| `web_send_message` | 发送用户消息 | 是 |
| `web_delete_session` | 删除会话 | 是 |
| `web_create_character` | 创建角色卡 | 是 |
| `web_update_character` | 更新角色卡 | 是 |
| `web_delete_character` | 删除角色卡 | 是 |
| `web_create_world_book` | 创建世界书 | 是 |
| `web_add_world_book_entry` | 添加世界书条目 | 是 |
| `web_delete_world_book` | 删除世界书 | 是 |
| `web_add_memory` | 添加记忆 | 是 |
| `web_update_memory` | 更新记忆 | 是 |
| `web_delete_memory` | 删除记忆 | 是 |
| `web_add_knowledge` | 添加知识库文档 | 是 |
| `web_delete_knowledge` | 删除知识库文档 | 是 |

---

## 权限系统

MCP 工具调用经过两层安全检查：

### 第一层：工具启用检查

在 `config.ini` 的 `[mcp]` 段控制：

```ini
[mcp]
send_message_enabled = false      ; 关闭发送消息工具
register_node_enabled = false     ; 关闭注册节点工具
submit_task_enabled = true        ; 开启提交任务工具
```

### 第二层：权限检查

权限分为 4 级：

| 级别 | Scope | 说明 |
|------|-------|------|
| 只读 | gateway.read, events.query, queue.read, node.read | 查看状态、查询事件 |
| 操作 | events.publish, channels.send, worker.manage | 发送消息、触发任务 |
| 管理 | gateway.manage, queue.manage, node.manage | 管理队列和节点 |
| 超级管理 | admin | 包含以上所有权限 |

默认只授予只读权限。要使用操作型工具，需要开启 `admin`：

```ini
[mcp]
admin = true
```

### 高危工具保护

高危工具调用需要：

1. 在配置中显式启用（如 `send_message_enabled = true`）
2. 在调用参数中传入 `confirm: true`
3. 所有调用记录审计日志

### 审计日志

所有操作型工具调用都会记录审计日志，包含：

- 时间戳
- 工具名称
- 调用参数（敏感字段自动脱敏）
- 执行结果
- 是否高危操作

---

## Claude Code 集成

### 本地 stdio 模式

在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "nekobot": {
      "command": "python",
      "args": ["bot.py", "--mcp-only"],
      "env": {
        "PYTHONPATH": "."
      }
    }
  }
}
```

然后在 Claude Code 中使用：

```
> 查看 NekoBot 的状态
> 查询最近的聊天事件
> 列出所有角色卡
```

### 远程连接模式

在远程服务器上启动 MCP Server（streamable-http 模式）：

```ini
[mcp]
transport = streamable-http
host = 0.0.0.0
port = 5001
admin = true
```

```bash
python bot.py --mcp-only
```

在本地 `.mcp.json` 中配置：

```json
{
  "mcpServers": {
    "nekobot": {
      "url": "http://192.168.1.100:5001/mcp"
    }
  }
}
```

---

## Cursor IDE 集成

在项目根目录创建 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "nekobot": {
      "command": "python",
      "args": ["bot.py", "--mcp-only"],
      "env": {
        "PYTHONPATH": "."
      }
    }
  }
}
```

如果 Cursor 不在项目根目录启动，需要添加 `cwd` 字段：

```json
{
  "mcpServers": {
    "nekobot": {
      "command": "python",
      "args": ["bot.py", "--mcp-only"],
      "env": {
        "PYTHONPATH": "."
      },
      "cwd": "/path/to/Ncatbot-comic-QQbot"
    }
  }
}
```

---

## 自定义 MCP 客户端

### 配置格式

任何 MCP 客户端都可以通过标准配置连接：

**stdio 模式：**

```json
{
  "mcpServers": {
    "nekobot": {
      "command": "python",
      "args": ["bot.py", "--mcp-only"],
      "env": {
        "PYTHONPATH": "."
      }
    }
  }
}
```

**streamable-http 模式：**

```json
{
  "mcpServers": {
    "nekobot": {
      "url": "http://host:port/mcp"
    }
  }
}
```

### 使用 Python SDK 连接

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="python",
    args=["bot.py", "--mcp-only"],
)

async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        # 获取工具列表
        result = await session.list_tools()
        for tool in result.tools:
            print(f"{tool.name}: {tool.description}")

        # 调用工具
        result = await session.call_tool(
            "gateway_get_status",
            arguments={}
        )
        print(result.content)
```

---

## NekoBot 作为 MCP Client

NekoBot 也可以连接外部 MCP 服务，将外部工具纳入 AI 的工具链。

### 配置方法

通过 Web Dashboard 的"配置 → MCP 服务"页面管理：

- **添加服务**：支持 stdio 和 streamable-http 两种类型
- **连接/断开**：手动控制连接状态
- **测试**：测试连接是否正常

### AI 工具调用

MCP 工具通过 `mcp__<server_id>__<tool_name>` 格式注入 AI 工具列表。AI 在 ReAct 循环中可像使用内置工具一样调用。

例如，连接了一个文件系统的 MCP 服务后，AI 可以：

```
mcp__a1b2c3d4__read_file → 读取文件
mcp__a1b2c3d4__write_file → 写入文件
```

### 内置 MCP 服务

使用 `--mcp` 启动时自动注册一个内置的本机 MCP 服务：

| 属性 | 值 |
|------|-----|
| 名称 | 本机 MCP 服务 |
| ID | `_builtin_local_mcp` |
| 传输 | stdio |
| 暴露工具 | 40+ 个 Gateway + Web 工具 |

---

## 安全建议

### 本地开发

- 使用 stdio 模式，避免暴露网络端口
- 开启 `admin = true` 简化权限管理
- 高危工具只在需要时启用

### 远程部署

- **必须** 使用 streamable-http 模式配合防火墙
- **不要** 将 MCP 端口（默认 5001）暴露到公网
- 使用 VPN 或 SSH 隧道保护 MCP 连接
- 审计日志始终开启（`audit_enabled = true`）

### 密钥管理

- API Key 等敏感信息不要写在 `config.ini` 中
- 通过 Web 后台的 AI 配置中心管理密钥（加密存储）
- 审计日志中的敏感字段自动脱敏

### 权限最小化

- 非必要不开启 `send_message_enabled`
- 非必要不开启 `register_node_enabled`
- 定期检查审计日志中的异常调用

---

## 故障排查

### MCP Server 无法启动

1. 检查 `mcp` 包是否安装：`pip install mcp`
2. 检查 Python 版本 >= 3.10
3. 检查 `config.ini` 格式是否正确

### 工具调用返回 permission_denied

1. 确认 `config.ini` 中 `[mcp]` 段有 `admin = true`
2. 确认已重启 MCP Server（配置不支持热更新）
3. 检查对应工具的启用开关（如 `send_message_enabled`）

### 无法查询历史事件

1. 确认 `[gateway]` 段的 `storage_enabled = true`
2. 确认 `data/` 目录存在且可写
3. 检查 `data/web/gateway.db` 文件是否生成

### 远程连接超时

1. 检查目标服务器防火墙是否放行 MCP 端口
2. 确认 `transport = streamable-http` 已设置
3. 检查 `host` 和 `port` 配置是否正确
4. 尝试 `curl http://host:port/mcp` 测试端点是否可达

---

## 完整配置示例

```ini
[BotConfig]
bot_uin = your_qq_number
ws_uri = ws://localhost:3001

[gateway]
storage_enabled = true
data_dir = data/web

[mcp]
send_message_enabled = true
register_node_enabled = false
submit_task_enabled = true
retry_require_confirmation = true
audit_enabled = true
admin = true
transport = stdio
host = 127.0.0.1
port = 5001
connect_url = http://127.0.0.1:5001/mcp
```
