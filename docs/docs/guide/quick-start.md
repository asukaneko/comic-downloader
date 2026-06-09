# 快速开始

> 多频道 AI 机器人，支持 QQ / Web / Telegram / 飞书，集成聊天、角色情感系统、世界书、工作区、工具调用、知识库、记忆与可视化管理后台

## 环境要求

::: warning
- Python 3.10+
- Windows / Linux / macOS
- 建议使用小号登录 QQ
:::

::: info
基于 [NapCat](https://github.com/NapNeko/NapCatQQ) 和 [ncatbot](https://github.com/NapNeko/NcatBot) 开发
:::

## 安装

### 1. 克隆项目

```bash
git clone https://github.com/asukaneko/nekobot.git
cd nekobot
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 NapCat

首次运行会自动提示下载 NapCat，或手动下载：

- [NapCat 下载](https://github.com/NapNeko/NapCatQQ/releases)
- 解压到根目录，重命名为 `napcat`

### 4. 配置环境变量

复制 `.env.example` 为 `.env` 并编辑：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# Web 登录密码（必需）
WEB_PASSWORD=你的Web登录密码

# QQ 配置（可选，如果不需要 QQ 功能可跳过）
BOT_UIN=你的QQ号
ROOT=管理员QQ号
WS_URI=ws://localhost:3001
TOKEN=napcat_token
WEBUI_URI=http://localhost:6099

# Telegram 配置（可选）
TELEGRAM_BOT_TOKEN=你的Telegram_Bot_Token
TELEGRAM_WEBHOOK_SECRET=你的Webhook_Secret

# 飞书配置（可选）
FEISHU_APP_ID=你的飞书_App_ID
FEISHU_APP_SECRET=你的飞书_App_Secret
```

::: tip
AI 相关的配置都可以在 Web 端进行配置，包括：
- 多模型配置管理（支持 OpenAI / Anthropic / Gemini 等协议）
- API 密钥设置
- 模型能力声明（supports_tools, supports_reasoning, supports_stream）
- 自定义价格（人民币计价）
- 故障转移队列
:::

## 启动

### 同时启动 QQ + Web（默认）

```bash
python bot.py
```

### 仅启动 Web 后台

```bash
python bot.py --only-web
```

### 仅启动 QQ

```bash
python bot.py --no-web
```

### CLI + Web 模式

```bash
python bot.py --cli-and-web
```

### 自定义 Web 地址

```bash
python bot.py --web-host 0.0.0.0 --web-port 5000
```

### Bot + MCP 模式（AI Agent 接口）

```bash
# 启动 Bot + MCP Server
python bot.py --mcp

# 无 Web 模式
python bot.py --mcp-only
```

MCP 模式会启动一个 stdio 传输的 MCP Server，供 Claude Code、Cursor 等 AI 智能体连接。详见 [MCP 文档](./nbot/mcp/index.md)。

## 访问 Web 后台

启动后访问 `http://localhost:5000`，使用 `.env` 中设置的 `WEB_PASSWORD` 登录。

Web 后台功能：
- **仪表盘** - 监控机器人状态、消息趋势和系统健康
- **聊天** - Web 端 AI 对话（支持流式输出）
- **会话管理** - 管理 Web 和 QQ 会话（标签页切换、归档、收藏）
- **AI 配置** - 多模型配置、API 密钥、故障转移队列
- **角色管理** - 角色卡编辑、立绘管理、情感系统配置
- **世界书** - 世界观设定管理，支持关键词匹配注入
- **记忆管理** - 跨会话记忆与角色记忆
- **知识库** - RAG 知识库管理（ChromaDB 向量检索）
- **Skills 配置** - 技能插件管理
- **Tools 配置** - 工具配置
- **工作流** - 可视化工作流编排
- **登录令牌** - 登录令牌管理（创建、查看、删除，支持 IP 记录）
- **定时任务** - 任务调度
- **Token 用量** - 用量统计（自定义日期范围、CSV 导出）
- **频道管理** - 多频道接入配置（QQ / Telegram / 飞书）
- **系统日志** - 日志查看与自动清理
- **调试台** - 调试工具

## 项目结构

```
nekobot/
├── bot.py                 # 入口文件
├── nbot/                  # 核心模块包
│   ├── channels/          # 频道适配层（QQ / Web / Telegram / 飞书）
│   ├── core/              # 统一 AI 核心
│   │   ├── protocols/     # 多协议适配（OpenAI / Anthropic / Gemini）
│   │   ├── knowledge/     # 知识库系统
│   │   └── memory/        # 记忆系统
│   ├── character/         # 角色情感系统
│   ├── gateway/           # 统一消息网关
│   │   ├── bus/           # 事件总线
│   │   ├── nodes/         # 节点控制面
│   │   └── facade.py      # MCP 服务门面
│   ├── mcp/               # MCP Server (AI Agent 接口)
│   ├── plugins/           # 插件系统
│   ├── services/          # AI、工具、聊天服务
│   └── web/               # Web 后台与前端
│       ├── routes/        # API 路由
│       ├── static/        # 静态资源
│       └── templates/     # 前端模板
├── data/                  # 运行数据
│   ├── qq/               # QQ 相关数据
│   ├── web/              # Web 会话、模型配置
│   ├── character/        # 角色运行时数据
│   ├── skills/           # Skills 存储
│   ├── models/           # 本地模型缓存
│   ├── sessions.db       # 会话持久化数据库
│   ├── memories.json     # 跨会话记忆
│   └── world_books.json  # 世界书数据
└── resources/            # 静态资源
    ├── config/           # 配置文件
    └── prompts/          # 提示词
```

## 工作区说明

工作区分为两种：

- **private** - 当前会话私有，位于 `data/workspaces/private/<session_id>/`
- **shared** - 全局共享，位于 `data/workspaces/_shared/`

AI 可以通过工具调用来读写工作区文件，支持文件变更预览与 diff 展示。

## 配置文件说明

| 文件 | 说明 |
|------|------|
| `.env` | 环境变量配置（推荐） |
| `config.ini` | 兼容配置（兜底） |
| `resources/config/option.yml` | 漫画下载配置 |
| `resources/config/urls.ini` | 图片 API |
| `resources/prompts/neko.txt` | AI 角色提示词 |

## 下一步

- [命令手册](./commands.md) - 了解所有命令
- [MCP 接口](./nbot/mcp/index.md) - AI Agent 接入
- [开发指南](./guide.md) - 开发自己的功能
- [频道管理](./channels.md) - 配置多频道接入
- [更新日志](./changelog.md) - 查看版本更新记录
