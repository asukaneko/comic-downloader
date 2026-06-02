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

; 重试死信是否需要确认
retry_require_confirmation = true

; 审计日志
audit_enabled = true

; 授予 MCP 全部权限（本地 stdio 模式建议开启）
admin = false
```

### 配置项说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| send_message_enabled | bool | false | 是否启用 `gateway_send_message` 工具 |
| retry_require_confirmation | bool | true | `gateway_retry_dead_letter` 是否需要确认 |
| audit_enabled | bool | true | 是否记录审计日志 |
| admin | bool | false | 是否授予 MCP 全部权限（admin scope） |

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
; 重试死信需要确认
retry_require_confirmation = true
; 审计日志
audit_enabled = true
; 授予全部权限（本地使用必开）
admin = true
```

## 权限配置

MCP 工具调用经过两层检查：

1. **工具是否启用** — 由 `send_message_enabled` 等配置控制
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
| `--no-web` | 禁用 Web Dashboard |
| `--web-port` | 自定义 Web 端口 |
| `--web-host` | 自定义 Web 绑定地址 |

组合示例：

```bash
# 仅 MCP Server（推荐用于 Claude Code / Cursor）
python bot.py --mcp-only

# Bot + MCP + Web
python bot.py --mcp

# Bot + MCP + Web，自定义端口
python bot.py --mcp --web-port 8080
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
3. 检查 `send_message_enabled` 是否已启用对应工具
