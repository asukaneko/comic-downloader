# MCP Client — 连接外部 MCP 服务

## 概述

NekoBot 不仅能作为 MCP Server 对外暴露工具，还能作为 MCP Client 连接外部 MCP 服务器，将外部工具接入 AI 的 ReAct 工具链。

通过 Web Dashboard 的「MCP 服务」页面，可以管理多个 MCP 服务连接，支持 stdio 和 streamable-http 两种传输方式。

## 架构

```text
AI ReAct Loop
    │
    ▼
Tool Registry (nbot/services/tools.py)
    │
    ├── 内置工具（memory、todo 等）
    └── MCP 工具（mcp__<server>__<tool> 格式）
            │
            ▼
    MCPBridge (nbot/services/mcp_bridge.py)
            │
            ├── Server A (stdio)  ──→  子进程
            ├── Server B (http)   ──→  远程端点
            └── _builtin (stdio)  ──→  本机 bot.py --mcp-only
```

## 启动方式

```bash
# Bot + MCP Server + Web（推荐）
python bot.py --mcp

# 启动后在 Web Dashboard → MCP 服务 页面管理连接
```

使用 `--mcp` 启动时，系统会自动注册一个内置的本机 MCP 服务（不可删除，可关闭），对应 `bot.py --mcp-only` 子进程。

## Web 管理界面

进入 Web Dashboard 的 **配置 → MCP 服务** 页面：

- **查看**：所有已配置的 MCP 服务及其连接状态
- **添加**：通过 JSON 配置添加新的 MCP 服务
- **连接/断开**：手动控制服务连接状态
- **测试**：测试连接是否正常
- **查看工具**：展开查看每个服务暴露的工具列表
- **删除**：删除自定义服务（内置服务不可删除）

## 配置格式

添加 MCP 服务时，输入标准 JSON 配置：

### stdio 模式（本地子进程）

```json
{
  "transport": "stdio",
  "command": "python",
  "args": ["-m", "my_mcp_server"],
  "env": {
    "API_KEY": "your-key"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| transport | string | 是 | 固定为 `"stdio"` |
| command | string | 是 | 可执行文件路径或命令名 |
| args | string[] | 否 | 命令参数 |
| env | object | 否 | 环境变量 |

### streamable-http 模式（远程网络）

```json
{
  "transport": "streamable-http",
  "url": "http://192.168.1.100:5001/mcp"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| transport | string | 是 | 固定为 `"streamable-http"` |
| url | string | 是 | MCP 服务端点 URL |

## AI 工具调用

MCP 工具通过 `mcp__<server_id>__<tool_name>` 格式注入 AI 的工具列表，AI 在 ReAct 循环中可以像使用内置工具一样调用。

### 工具名格式

```
mcp__<server_id前8位>__<工具名>
```

例如连接了一个 server_id 为 `a1b2c3d4-...` 的 MCP 服务，其 `read_file` 工具会注册为：

```
mcp__a1b2c3d4__read_file
```

### 调用流程

1. AI 在 ReAct 循环中决定调用 `mcp__xxx__tool_name`
2. `execute_tool()` 识别 `mcp__` 前缀，路由到 MCPBridge
3. MCPBridge 解析 server_id 和 tool_name，找到对应连接
4. 通过 MCP 协议调用远程工具
5. 返回结果给 AI

## 内置 MCP 服务

使用 `--mcp` 启动时，系统自动注册一个内置条目：

| 属性 | 值 |
|------|------|
| 名称 | 本机 MCP 服务 |
| ID | `_builtin_local_mcp` |
| 传输 | stdio |
| 命令 | `<python解释器> bot.py --mcp-only` |
| 可删除 | 否 |
| 可关闭 | 是 |
| 自动连接 | 是 |

内置服务暴露 Gateway 和 Web 的全部 MCP 工具（共 40+ 个），包括：

- Gateway 状态查询、事件查询、日志查询
- 消息发送、节点管理、队列管理
- 会话/角色卡/世界书/记忆/知识库/AI 模型的 CRUD

## 数据存储

MCP 服务配置保存在 `data/web/mcp_servers.json`，结构示例：

```json
{
  "servers": {
    "_builtin_local_mcp": {
      "id": "_builtin_local_mcp",
      "name": "本机 MCP 服务",
      "transport": "stdio",
      "command": "python",
      "args": ["bot.py", "--mcp-only"],
      "enabled": true,
      "auto_connect": true,
      "_builtin": true
    }
  }
}
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/mcp-servers` | 列出所有服务 |
| POST | `/api/mcp-servers` | 添加服务 |
| PUT | `/api/mcp-servers/<id>` | 更新服务 |
| DELETE | `/api/mcp-servers/<id>` | 删除服务（内置不可删） |
| POST | `/api/mcp-servers/<id>/connect` | 连接服务 |
| POST | `/api/mcp-servers/<id>/disconnect` | 断开服务 |
| GET | `/api/mcp-servers/<id>/tools` | 获取服务工具列表 |
| POST | `/api/mcp-servers/<id>/test` | 测试连接 |

## 注意事项

- stdio 模式下，子进程的 stdout 用于 MCP 协议通信，日志输出会自动重定向到 stderr
- 每个 MCP 服务连接维护独立的会话，互不影响
- 内置服务在 bot 启动时自动注册，配置修改后需重启生效
- 连接超时默认 30 秒，可在代码中调整
