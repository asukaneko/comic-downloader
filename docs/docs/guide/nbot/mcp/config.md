# MCP 配置

## 概述

MCP Server 的行为通过 `config.ini` 中的 `[mcp]` 和 `[gateway]` 段控制。

## 配置文件位置

配置文件位于项目根目录的 `config.ini`：

```text
Ncatbot-comic-QQbot/
├── bot.py
├── config.ini          ← MCP 配置在这里
├── nbot/
│   ├── mcp/
│   └── gateway/
└── data/
    └── web/
        └── gateway.db  ← Gateway 持久化数据
```

## MCP 配置段

```ini
[mcp]
; 是否允许 MCP 发送真实消息（高危，默认关闭）
send_message_enabled = false

; 是否允许 MCP 注册节点（高危，默认关闭）
register_node_enabled = false

; 是否允许 MCP 提交内部任务（高危，默认开启）
submit_task_enabled = true

; 重试死信是否需要确认
retry_require_confirmation = true

; 审计日志
audit_enabled = true

; 授予 MCP 全部权限（本地 stdio 模式建议开启）
admin = false

; 传输模式: stdio (本地子进程) | streamable-http (远程网络)
transport = stdio

; 服务端绑定地址（streamable-http 模式生效）
host = 127.0.0.1

; 服务端端口（streamable-http 模式生效）
port = 5001

; 远程 MCP Server URL（--mcp-connect 客户端模式使用）
connect_url = http://127.0.0.1:5001/mcp
```

### 配置项说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| send_message_enabled | bool | false | 是否启用 `gateway_send_message` 工具 |
| register_node_enabled | bool | false | 是否启用 `gateway_register_node` 工具 |
| submit_task_enabled | bool | true | 是否启用 `gateway_submit_internal_task` 工具 |
| retry_require_confirmation | bool | true | `gateway_retry_dead_letter` 是否需要确认 |
| audit_enabled | bool | true | 是否记录审计日志 |
| admin | bool | false | 是否授予 MCP 全部权限（admin scope） |
| transport | string | "stdio" | 传输模式：`stdio`（本地）或 `streamable-http`（远程） |
| host | string | "127.0.0.1" | 服务端绑定地址（streamable-http 模式） |
| port | int | 5001 | 服务端端口（streamable-http 模式） |
| connect_url | string | "" | 远程 MCP Server URL（`--mcp-connect` 使用） |

::: warning 工具启用 ≠ 权限授予
`send_message_enabled` 只控制工具是否**可用**，不控制是否有**权限**调用。
即使工具已启用，如果未授予对应权限，调用时仍会返回 `permission_denied`。
本地使用建议设置 `admin = true` 以授予全部权限。
:::

## Gateway 配置段

```ini
[gateway]
; Gateway 持久化存储（启用后可查询历史事件）
storage_enabled = true

; 数据目录
data_dir = data/web
```

### 配置项说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| storage_enabled | bool | true | 是否启用 SQLite 持久化 |
| data_dir | string | "data/web" | 数据目录路径，与 Web Dashboard 共用 |

::: tip
启用 `storage_enabled` 后，MCP 才能查询历史事件、投递记录和 trace 链路。
:::

## 完整配置示例

```ini
[BotConfig]
bot_uin = your_qq_number
ws_uri = ws://localhost:3001

[gateway]
storage_enabled = true
data_dir = data/web

[mcp]
; 启用发送消息工具
send_message_enabled = true
; 启用注册节点工具
register_node_enabled = true
; 启用提交内部任务工具
submit_task_enabled = true
; 重试死信需要确认
retry_require_confirmation = true
; 审计日志
audit_enabled = true
; 授予全部权限（本地使用必开）
admin = true
; 传输模式: stdio (本地) | streamable-http (远程)
transport = stdio
; 服务端配置（streamable-http 模式）
host = 127.0.0.1
port = 5001
; 远程连接 URL（--mcp-connect 使用）
connect_url = http://127.0.0.1:5001/mcp
```

## 权限配置

MCP 工具调用经过两层检查：

1. **工具是否启用** — 由 `send_message_enabled`、`register_node_enabled` 等配置控制
2. **是否有权限调用** — 由 `admin` 配置控制

### 权限模型

| 权限级别 | Scope | 说明 |
|----------|-------|------|
| 只读 | gateway.read, events.query, queue.read, node.read | 查看状态、查询事件/日志 |
| 操作 | events.publish, channels.send, worker.manage | 发送消息、触发任务 |
| 管理 | gateway.manage, queue.manage, node.manage | 管理队列和节点 |
| 超级管理 | admin | 包含以上所有权限 |

默认只授予 4 个只读 scope。要使用操作型工具（如发送消息、重试死信等），需要开启 `admin`：

```ini
[mcp]
; 授予全部权限，本地使用建议开启
admin = true
```

::: tip
配置修改后需要**重启 MCP Server** 才能生效（配置在启动时加载，不支持热更新）。
:::

## 启动参数

| 参数 | 说明 |
|------|------|
| `--mcp` | 启动 MCP Server（同时启动 Bot + Web） |
| `--mcp-only` | 仅启动 MCP Server（不启动 Bot 和 Web） |
| `--mcp-connect [url]` | 连接远程 MCP Server（客户端模式） |
| `--no-web` | 禁用 Web Dashboard |
| `--web-port` | 自定义 Web 端口 |
| `--web-host` | 自定义 Web 绑定地址 |

组合示例：

```bash
# 仅 MCP Server（推荐用于 Claude Code / Cursor）
python bot.py --mcp-only

# MCP Server 远程模式（streamable-http）
# 先在 config.ini 设置 transport = streamable-http
python bot.py --mcp-only

# Bot + MCP + Web
python bot.py --mcp

# Bot + MCP + Web，自定义端口
python bot.py --mcp --web-port 8080

# 连接远程 MCP Server
python bot.py --mcp-connect http://192.168.1.100:5001/mcp
```

## 远程连接

MCP Server 支持通过 `streamable-http` 传输协议提供远程访问。

### 服务端（被连接方）

1. 在 `config.ini` 中设置 `transport = streamable-http`
2. 设置 `host` 和 `port`（默认 `127.0.0.1:5001`）
3. 启动服务端：`python bot.py --mcp-only`

```ini
[mcp]
transport = streamable-http
host = 0.0.0.0    ; 监听所有网卡
port = 5001
admin = true
```

服务端启动后，MCP 端点为 `http://<host>:<port>/mcp`。

### 客户端（连接方）

使用 `--mcp-connect` 连接远程 MCP Server：

```bash
# 直接指定 URL
python bot.py --mcp-connect http://192.168.1.100:5001/mcp

# 或在 config.ini 中配置 connect_url 后直接运行
python bot.py --mcp-connect
```

连接后进入交互式 CLI：

```
🐱 NekoBot MCP Client — 已连接 http://192.168.1.100:5001/mcp
输入 help 查看可用命令

mcp> tools                    # 列出远程工具
mcp> call gateway_get_status  # 调用工具
mcp> call gateway_query_events {"limit": 5}
mcp> quit
```

### Claude Code 远程连接

在 `.mcp.json` 中使用 `url` 字段（streamable-http）：

```json
{
  "mcpServers": {
    "nekobot": {
      "url": "http://192.168.1.100:5001/mcp"
    }
  }
}
```

## Claude Code 配置

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

## Cursor 配置

> **提示**：如 Cursor 不在项目根目录启动，需添加 `cwd` 字段指定项目路径。

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

## 故障排查

### MCP Server 无法启动

1. 检查 `mcp` 包是否安装：`pip install mcp`
2. 检查 Python 版本 >= 3.10
3. 检查 `config.ini` 格式是否正确

### 无法查询历史事件

1. 确认 `[gateway]` 段的 `storage_enabled = true`
2. 确认 `data/` 目录存在且可写
3. 检查 `data/web/gateway.db` 文件是否生成

### 工具调用返回 permission_denied

1. 确认 `config.ini` 中 `[mcp]` 段有 `admin = true`
2. 确认已**重启 MCP Server**（配置不支持热更新）
3. 检查 `send_message_enabled`、`register_node_enabled` 或 `submit_task_enabled` 是否已启用对应工具
