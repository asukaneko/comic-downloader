# NekoBot

![cover](docs/cover.png)

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-2ea043?style=flat)
![Web](https://img.shields.io/badge/Web-Dashboard-ec4899?style=flat)
![QQ](https://img.shields.io/badge/QQ-NapCat%20%2B%20ncatbot-58a6ff?style=flat)
![MCP](https://img.shields.io/badge/MCP-AI%20Agent%20Interface-8b5cf6?style=flat)

面向 Web 的多渠道 AI 角色扮演系统，包含Web、QQ、CLI、Telegram、Feishu等频道。

</div>

## Overview

NekoBot 是一个面向角色扮演与长期互动场景的 AI 系统。项目采用统一 AI 内核与频道适配层分离的架构，提供完整的 Web 管理后台、角色运行时、记忆系统、工具调用与工作区能力。

它的核心目标不是单纯提供“聊天接口”，而是提供一套可持续运行、可配置、可观测、可扩展的角色型智能体基础设施。

## Core Capabilities

- 多渠道接入：支持 QQ、Web、CLI、Telegram、Feishu，共用统一的 `ChatRequest / ChatResponse` 处理链路。
- 角色运行时：内置实时情感引擎、六维关系模型、动态 PromptStack、自动状态评估与角色记忆。
- Web 控制台：提供会话管理、角色管理、模型配置、工作流、知识库、记忆、日志与调试界面。
- 工具与工作区：支持工具调用、文件读写、共享/私有工作区、文件变更预览与任务执行。
- 模型适配：兼容 OpenAI Chat Completions/Responses , Anthropic , Gemini接口，可接入 Deepseek、GLM、Kimi、Mimo及其他兼容服务。
- 插件与技能：支持通过插件与技能系统扩展能力，而不破坏核心处理流程。
- MCP 接口：通过 Model Context Protocol 暴露 Gateway 能力，支持 Claude Code、Cursor、ChatGPT Agent 等 AI 智能体直接调用。

## Architecture

项目围绕“统一 AI 内核 + 多渠道适配”的原则组织：

```text
bot.py
└── nbot/
    ├── commands.py             # QQ command handlers, BotClient init
    ├── core/                   # Unified AI pipeline
    │   ├── chat_models.py      # ChatRequest / ChatResponse
    │   ├── agent_service.py    # Main AI entry
    │   ├── ai_pipeline.py      # Pre-process -> chat -> post-process
    │   ├── session_store.py    # Unified session state
    │   ├── model_adapter.py    # Cross-provider model adapter
    │   ├── workspace.py        # Per-session file workspace
    │   ├── auto_memory.py      # Automatic memory extraction
    │   └── workflow.py         # Workflow executor
    ├── character/              # Affective runtime and relationship model
    ├── channels/               # QQ, Web, Telegram, Feishu adapters
    ├── services/               # AI client, chat service, tools, TTS/STT
    ├── plugins/                # Plugin and skill system
    ├── gateway/                # Message bus, routing, delivery, dedupe
    │   └── facade.py            # Gateway service facade for MCP
    ├── web/                    # Flask blueprints, Socket.IO events, dashboard
    ├── mcp/                    # MCP Server (AI Agent interface)
    │   ├── server.py            # FastMCP entry point
    │   ├── tools/               # MCP Tools
    │   ├── resources/           # MCP Resources
    │   └── prompts/             # MCP Prompts
    └── cli/                    # Terminal UI
```

请求流如下：

```text
Channel Adapter
  -> ChatRequest
  -> Agent Service / AI Pipeline
  -> Character Runtime (before_turn / after_turn)
  -> Model Adapter / AI Client
  -> ChatResponse
  -> Channel Adapter
```

## Runtime Features

### Character Runtime

`nbot/character/` 提供角色运行时，用于把“角色设定”转化为持续一致的对话行为：

- `PromptStack`：按优先级动态拼装提示词，而不是把所有状态污染进历史消息。
- `StateMachine`：控制情绪惯性与关系平滑变化，避免单轮输入导致剧烈失真。
- `AutoState`：定期总结近期互动，自动调整情绪强度、精力与六维关系值。
- `Memory`：支持按角色、按用户隔离的长期与短期记忆。
- `ReactionPlan`：在每轮回复前生成风格与行为策略，约束角色输出。

### Workspace and Tools

系统支持私有工作区与共享工作区：

- 私有工作区绑定当前会话。
- 共享工作区可被多个会话访问。
- 文件创建、修改、删除、传输与差异预览可通过 Web 界面管理。
- 工具系统支持在对话中触发文件、搜索、执行等能力。

### Web Dashboard

Web 后台覆盖日常运维与调试需求：

- 会话与聊天管理
- 角色卡创建、编辑、导入、导出
- AI 模型配置与切换
- 记忆、知识库、技能、工具管理
- 工作流与定时任务
- Token 统计、日志、调试与运行状态查看

## Requirements

- Python 3.10+
- NapCatQQ
- ncatbot 3.8.5
- 可用的 OpenAI-compatible API 服务

说明：

- `.env` 是首选配置来源。
- `config.ini` 仍作为 QQ 连接参数的兼容回退。
- 项目默认使用 Flask + Flask-SocketIO + Eventlet 提供 Web 服务。

## Installation

```bash
git clone https://github.com/asukaneko/nekobot.git
cd nekobot
```

```bash
#配置虚拟环境（可选）
python -m venv venv
source venv/bin/activate
# windows: venv\Scripts\activate.bat
python -m pip install -r requirements.txt
```

复制环境变量模板并填写必要配置：

```bash
cp .env.example .env
```

至少建议先配置：

```env
WEB_PASSWORD=your_web_password
```

如需启用 QQ Bot，还需要补充：

```env
BOT_UIN=your_qq_number
ROOT=your_admin_qq_number
WS_URI=ws://your_napcat_host:port
TOKEN=your_napcat_token
```

AI 服务的最小示例：

```env
API_KEY=your_api_key
BASE_URL=https://your-openai-compatible-endpoint/v1
MODEL=your_model_name
```

但你仍然可以通过web界面来配置你的模型

## Running

```bash
# QQ + Web
python bot.py

# Web only
python bot.py --only-web

# Web only on custom host/port
python bot.py --only-web --web-host 0.0.0.0 --web-port 5000

# CLI only
python bot.py --cli

# CLI + Web
python bot.py --cli-and-web

# QQ only
python bot.py --no-web
```

默认情况下：

- 若检测到 QQ 相关配置，启动 `QQ + Web`。
- 若未检测到 QQ 配置，项目可仅以 Web 模式运行。

## Development Notes

- 目标 Python 版本为 `3.10`。
- 代码风格使用 Ruff，行宽 100，双引号，空格缩进。
- `nbot/core/` 不应依赖频道层模块。
- 所有新频道都应通过 `BaseChannelAdapter` 接入，而不是直接调用模型。
- 角色逻辑应通过 `before_turn()` / `after_turn()` 挂入统一流水线。

常用检查命令：

```bash
ruff check .
python -m compileall -q bot.py nbot tools
python -m pytest -q
```

CI 主要执行：

1. `ruff check . --select E9,F63,F7,F82`
2. `python -m compileall -q bot.py nbot tools`
3. `python -m pip install -r requirements.txt`
4. `python -m pytest -q`

## Documentation

更详细的使用与开发文档位于 `docs/`：

- 快速开始：[docs/docs/guide/quick-start.md](docs/docs/guide/quick-start.md)
- 命令说明：[docs/docs/guide/commands.md](docs/docs/guide/commands.md)
- 频道接入：[docs/docs/guide/channels.md](docs/docs/guide/channels.md)
- 贡献指南：[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)
- 更新记录：[docs/CHANGELOG.md](docs/CHANGELOG.md)


## MCP (Model Context Protocol)

NekoBot 内置 MCP Server，可以将 Gateway 的消息、事件、队列、节点等能力以标准 MCP 协议暴露给 AI 智能体。

### 支持的能力

| 类型 | 说明 |
|------|------|
| Tools | 查询状态、查询事件链路、查询队列、模拟消息、触发任务、重试死信、节点管理 |
| Resources | Gateway 状态、统计数据、能力清单、队列状态、节点列表 |
| Prompts | 故障诊断、频道测试、节点健康检查 |

### 快速开始

```bash
# 启动 Bot + MCP
python bot.py --mcp
```

### Claude Code 配置

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

> **提示**：`bot.py` 是相对路径，会从当前工作目录查找。如果 Claude Code 不在项目根目录启动，需要通过 `cwd` 指定项目路径，或将 `args` 改为绝对路径。

### Cursor 配置

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

### MCP 配置项

在 `config.ini` 中配置 MCP 行为：

```ini
[mcp]
; 是否允许 MCP 发送真实消息（高危，默认关闭）
send_message_enabled = false
; 重试死信是否需要确认
retry_require_confirmation = true
; 审计日志
audit_enabled = true
; 授予 MCP 全部权限（本地使用建议开启）
admin = true

[gateway]
; Gateway 持久化存储（启用后可查询历史事件）
storage_enabled = true
data_dir = data/web
```

### 可用 Tools

| Tool | 说明 | 风险 |
|------|------|------|
| `gateway_get_status` | Gateway 健康状态 | 只读 |
| `gateway_get_stats` | 事件/投递/去重统计 | 只读 |
| `gateway_query_trace` | 查询 trace 完整链路 | 只读 |
| `gateway_query_events` | 按条件查询事件 | 只读 |
| `gateway_query_deliveries` | 查询投递记录 | 只读 |
| `gateway_get_queue_stats` | 队列状态 | 只读 |
| `gateway_list_nodes` | 节点列表 | 只读 |
| `gateway_get_node` | 节点详情 | 只读 |
| `gateway_receive_message` | 模拟频道消息 | 操作 |
| `gateway_send_message` | 发送真实消息 | 高危 |
| `gateway_submit_internal_task` | 触发内部任务 | 操作 |
| `gateway_retry_dead_letter` | 重试死信 | 高危 |
| `gateway_register_node` | 注册节点 | 操作 |

## Security Notes

- 不要将 Web 后台直接暴露到公网且不做额外防护。
- 请为 `WEB_PASSWORD`、API Key、NapCat Token 设置有效且独立的密钥。
- 不要提交 `.env`、真实凭据或运行时敏感数据到仓库。
- 机器人运行期间，不要手动修改 `data/character/` 下的持久化文件。

## License

本项目基于 MIT License 发布，详见 [LICENSE](LICENSE)。

