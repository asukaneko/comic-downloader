# MCP - AI Agent 接口

## 概述

NekoBot 内置 MCP (Model Context Protocol) Server，将 Gateway 的消息、事件、队列、节点等能力以标准协议暴露给 AI 智能体。

通过 MCP，Claude Code、Cursor、ChatGPT Agent 等外部智能体可以安全、标准地调用 NekoBot 的核心能力。

## 架构

```text
AI Agent / IDE / Claude Code / Cursor
        │
        ▼
MCP Server Layer (nbot/mcp/)
        │
        ├── Tools     → 产生动作（查询、发送、重试）
        ├── Resources → 只读上下文（状态、统计）
        └── Prompts   → 操作模板（诊断、测试）
        │
        ▼
Gateway Facade (nbot/gateway/facade.py)
        │
        ▼
Gateway Core
        │
        ├── Security / RateLimit / Dedupe
        ├── Router / Adapter
        ├── Queue / Worker
        ├── Delivery
        ├── Node Control Plane
        └── Storage / Trace
```

## 启动方式

```bash
# 仅 MCP Server（推荐用于 Claude Code / Cursor）
python bot.py --mcp-only

# Bot + MCP + Web（完整模式）
python bot.py --mcp
```

启动后：
- QQ Bot 在后台线程运行（如果配置了）
- Web Dashboard 在后台线程运行（除非 --no-web）
- MCP Server 在主线程运行（stdio 模式）

## 连接配置

### Claude Code

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

### Cursor

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

> **提示**：如 Cursor 不在项目根目录启动，需添加  字段指定项目路径。

## 能力分类

| 类型 | 说明 | 示例 |
|------|------|------|
| Tools | 产生动作的操作 | 查询状态、发送消息、重试死信 |
| Resources | 只读上下文数据 | Gateway 状态、统计、能力清单 |
| Prompts | 操作模板 | 故障诊断、频道测试、节点健康检查 |

## 子模块

| 模块 | 文件 | 职责 |
|------|------|------|
| Tools | `tools/gateway_tools.py` | MCP 工具注册与处理 |
| 配置 | `config.ini` | MCP 行为配置 |
| Server | `server.py` | FastMCP 入口 |
| Context | `context.py` | 运行时上下文管理 |
| Schemas | `schemas.py` | Pydantic 输入输出模型 |
| Errors | `errors.py` | 结构化错误包装 |
| Permissions | `permissions.py` | 权限模型与审计日志 |

## 安全设计

- **默认本地优先**：第一版只支持 stdio 传输，安全风险低
- **权限分级**：只读 → 操作 → 管理 → 超级管理
- **高危工具保护**：发送消息、重试死信等需要显式启用
- **审计日志**：所有操作型工具调用都记录审计日志
- **敏感字段脱敏**：token、secret 等字段自动脱敏

## MCP Client 模式

除了作为 MCP Server 对外暴露工具，NekoBot 还支持作为 MCP Client 连接外部 MCP 服务器：

```bash
# 启动 Bot + MCP Server + Web Dashboard
python bot.py --mcp
```

通过 Web Dashboard 的「MCP 服务」页面，可以：

- 添加 stdio / streamable-http 类型的 MCP 服务
- 管理连接状态（连接/断开/测试）
- 查看每个服务暴露的工具列表
- AI 在 ReAct 循环中自动使用已连接的 MCP 工具

详细配置参见 [MCP Client](./client.md)。
