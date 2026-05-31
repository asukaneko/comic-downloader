# 开发指南

## 项目概述

NekoBot 是一个多频道 AI 机器人，采用"统一 AI 内核 + 频道适配层"的架构设计：

- **统一 AI 核心** - 多频道共用同一套 AI 处理链路
- **多协议适配** - 支持 OpenAI Chat/Responses、Anthropic Messages、Gemini Native 等协议
- **频道适配层** - QQ、Web、Telegram、飞书等频道输入输出归一化
- **统一消息网关** - 安全验证、限流、去重、分发、投递全流程
- **角色情感系统** - 实时情感引擎，支持情绪、关系、记忆动态模拟
- **世界书系统** - 关键词匹配注入世界观设定，支持多源召回
- **工作区支持** - 私有和共享工作区，支持文件操作
- **工具调用** - 支持多轮工具调用和继续执行
- **Web 后台** - 完整的可视化管理界面

## 核心架构

```
Ncatbot-comic-QQbot/
├── bot.py                     # 入口文件，负责启动配置
├── nbot/                      # 核心模块包
│   ├── channels/              # 频道适配层
│   │   ├── base.py            # 频道适配器基类
│   │   ├── qq.py              # QQ 频道适配器
│   │   ├── web.py             # Web 频道适配器
│   │   ├── telegram.py        # Telegram 频道适配器
│   │   ├── feishu.py          # 飞书频道适配器
│   │   ├── configured.py      # 通用配置化适配器
│   │   └── registry.py        # 频道注册器
│   │
│   ├── core/                  # 统一 AI 核心
│   │   ├── agent_service.py   # AI 处理入口
│   │   ├── ai_pipeline.py     # AI 管道中间件
│   │   ├── chat_models.py     # ChatRequest / ChatResponse 模型
│   │   ├── session_store.py   # 会话存储
│   │   ├── model_adapter.py   # 模型适配层
│   │   ├── failover.py        # 模型故障转移队列
│   │   ├── workflow.py        # 工作流引擎
│   │   ├── message.py         # 消息模型
│   │   ├── message_middleware.py # 消息中间件
│   │   ├── prompt.py          # 提示词管理
│   │   ├── prompt_format.py   # 提示词格式化
│   │   ├── progress_card.py   # 进度卡片
│   │   ├── skills_manager.py  # 技能管理器
│   │   ├── todo_card.py       # 待办卡片
│   │   ├── token_stats.py     # Token 用量统计
│   │   ├── auto_memory.py     # AI 自动记忆
│   │   ├── heartbeat.py       # 会话心跳管理
│   │   ├── file_parser.py     # 文件解析器
│   │   ├── protocols/         # 多协议适配层
│   │   │   ├── openai_chat.py     # OpenAI Chat 协议
│   │   │   ├── openai_responses.py # OpenAI Responses 协议
│   │   │   ├── anthropic_messages.py # Anthropic Messages 协议
│   │   │   └── gemini_native.py   # Gemini Native 协议
│   │   ├── knowledge/         # 知识库系统
│   │   └── memory/            # 记忆系统
│   │
│   ├── character/             # 角色情感系统
│   │   ├── models.py          # 数据模型
│   │   ├── runtime.py         # 运行时引擎
│   │   ├── planner.py         # 反应计划生成器
│   │   ├── state_machine.py   # 状态机
│   │   ├── policies.py        # 信号分析器
│   │   ├── memory.py          # 角色记忆服务
│   │   ├── repository.py      # 数据仓库
│   │   ├── prompt_stack.py    # 动态提示词栈
│   │   └── world_book.py      # 世界书系统
│   │
│   ├── gateway/               # 统一消息网关
│   │   ├── gateway.py         # 核心管道 (ChannelGateway)
│   │   ├── security.py        # 安全模块 (SecurityProvider)
│   │   ├── rate_limit.py      # 限流模块 (RateLimiter)
│   │   ├── dedupe.py          # 消息去重 (DedupeStore)
│   │   ├── delivery.py        # 投递模块 (GatewayDelivery)
│   │   ├── delivery_store.py  # 投递存储
│   │   ├── queue.py           # 异步队列 (EventQueue)
│   │   ├── worker.py          # 网关工作线程 (GatewayWorker)
│   │   ├── dispatcher.py      # 事件分发器
│   │   ├── router.py          # 路由器
│   │   ├── schemas.py         # 数据模式
│   │   ├── errors.py          # 错误定义
│   │   ├── event_store.py     # 事件存储
│   │   ├── storage.py         # 持久化存储
│   │   ├── heartbeat.py       # 网关心跳
│   │   ├── trace.py           # 链路追踪
│   │   ├── bus/               # 事件总线 (发布/订阅)
│   │   └── nodes/             # 节点控制面
│   │
│   ├── plugins/               # 插件系统
│   │   ├── skills/            # 技能模块
│   │   │   ├── base.py        # 技能基类
│   │   │   ├── loader.py      # 技能加载器
│   │   │   └── builtin/       # 内置技能
│   │   ├── dispatcher.py      # 技能调度器
│   │   └── manager.py         # 插件管理器
│   │
│   ├── services/              # 服务层
│   │   ├── ai.py              # AI 客户端
│   │   ├── chat_service.py    # 聊天服务
│   │   ├── anthropic_adapter.py # Anthropic 适配器
│   │   ├── tools.py           # 工具注册
│   │   ├── skills_tools.py    # 技能工具
│   │   ├── todo_tools.py      # 待办工具
│   │   ├── react.py           # ReAct 模式
│   │   ├── dynamic_executor.py # 动态执行器
│   │   ├── stt.py             # 语音转文字
│   │   ├── tts.py             # 文字转语音
│   │   ├── tool_registry.py   # 工具注册表
│   │   ├── feishu_service.py  # 飞书服务
│   │   ├── feishu_ws_service.py # 飞书 WebSocket 服务
│   │   ├── feishu_chat_service.py # 飞书聊天服务
│   │   └── telegram_service.py # Telegram 服务
│   │
│   ├── web/                   # Web 界面
│   │   ├── server.py          # Flask 服务
│   │   ├── ai_service.py      # Web AI 服务
│   │   ├── socket_events.py   # SocketIO 事件处理
│   │   ├── persistence.py     # 持久化层
│   │   ├── config_transfer.py # 配置导入导出
│   │   ├── file_gateway.py    # 文件网关
│   │   ├── log_cleanup.py     # 日志清理
│   │   ├── secure_store.py    # 安全存储
│   │   ├── message_adapter.py # 消息适配器
│   │   ├── agent_tools.py     # Agent 工具
│   │   ├── sessions_db.py     # 会话数据库
│   │   ├── push_keys.py       # 推送密钥
│   │   ├── routes/            # API 路由
│   │   ├── static/            # 静态资源
│   │   ├── templates/         # 前端模板
│   │   └── utils/             # 工具函数
│   │
│   ├── commands.py            # 命令处理
│   ├── ai_commands.py         # AI 相关命令
│   ├── chat.py                # 聊天兼容层
│   ├── config.py              # 配置兼容层
│   └── heartbeat.py           # 心跳兼容层
│
├── data/                      # 运行数据
│   ├── qq/                    # QQ 相关数据
│   ├── web/                   # Web 会话、模型配置
│   ├── skills/                # Skills 存储
│   └── workspaces/            # 私有 / 共享工作区
│
└── resources/                 # 静态资源
    ├── config/                # 配置文件
    └── prompts/               # 提示词
```

## 主要模块详解

### 1. 频道适配层 (nbot/channels/)

频道适配层负责将不同频道的输入输出归一化为统一的 `ChatRequest` / `ChatResponse`。

#### 基类定义 (base.py)

```python
from nbot.channels.base import BaseChannelAdapter, ChannelCapabilities

class MyChannelAdapter(BaseChannelAdapter):
    channel_name = "my_channel"

    def get_capabilities(self):
        return ChannelCapabilities(
            supports_stream=True,
            supports_file_send=True,
            supports_progress_updates=True,
            supports_stop=True
        )

    def normalize_inbound_message(self, content: str) -> str:
        return content.strip()

    def build_chat_request(self, **kwargs):
        return super().build_chat_request(**kwargs)
```

#### 注册适配器

```python
from nbot.channels.registry import register_channel_adapter

register_channel_adapter("my_channel", MyChannelAdapter)
```

### 2. 统一 AI 核心 (nbot/core/)

#### ChatRequest / ChatResponse (chat_models.py)

```python
from nbot.core.chat_models import ChatRequest, ChatResponse

request = ChatRequest(
    channel="web",
    conversation_id="session_123",
    user_id="user_456",
    content="你好",
    attachments=[],
    metadata={}
)

response = ChatResponse(
    final_content="你好！有什么可以帮助你的？",
    can_continue=False,
    tool_trace=[]
)
```

#### AI 管道 (ai_pipeline.py)

AI 管道是核心处理链路，负责提示词组装、上下文管理、工具调用、流式输出等。

#### 模型故障转移 (failover.py)

支持多模型故障转移队列，可为每个模型设置 Token 使用上限，自动切换可用模型。

#### 多协议适配 (protocols/)

支持的协议：
- OpenAI Chat Completions
- OpenAI Responses API
- Anthropic Messages API
- Gemini Native API

### 3. 角色情感系统 (nbot/character/)

独立的角色运行时引擎，支持角色状态、情绪、关系与记忆的动态模拟。

- **运行时引擎** (runtime.py) - 角色状态实时变化
- **反应计划器** (planner.py) - 根据情绪生成反应计划
- **状态机** (state_machine.py) - 角色状态管理
- **世界书** (world_book.py) - 关键词匹配注入世界观设定
- **动态提示词栈** (prompt_stack.py) - 提示词动态组装
- **角色记忆** (memory.py) - 角色专属记忆

### 4. 统一消息网关 (nbot/gateway/)

全新网关模块，为所有频道提供统一的事件处理链路。

核心流程：`received → dispatched → delivered/failed`

- **安全验证** - none/static/hmac/ip 四种鉴权策略
- **限流** - 基于滑动窗口的多维度限流（用户/会话/IP/频道）
- **去重** - 内存 LRU 和 SQLite 持久化两种后端
- **分发** - 事件总线发布/订阅模式
- **投递** - 长文本分片 + Markdown 降级
- **异步队列** - 失败项延迟重试，指数退避策略

### 5. 服务层 (nbot/services/)

#### AI 客户端 (ai.py)

```python
from nbot.services.ai import ai_client

response = await ai_client.chat(messages)

async for chunk in ai_client.chat_stream(messages):
    yield chunk
```

#### 工具注册 (tools.py)

```python
from nbot.services.tools import register_tool

@register_tool("search")
async def search_tool(query: str) -> str:
    """搜索工具"""
    return result
```

### 6. 插件系统 (nbot/plugins/)

#### 技能基类 (skills/base.py)

```python
from nbot.plugins.skills.base import Skill, skill

@skill
class MySkill(Skill):
    name = "my_skill"
    aliases = ["我的技能"]
    description = "技能描述"

    async def execute(self, content: str, **kwargs) -> str:
        return f"执行结果: {content}"
```

### 7. 工作区 (Workspace)

工作区分为两种：

- **private** - 当前会话私有
- **shared** - 全局共享

```python
from nbot.core.workspace import get_workspace_manager

wm = get_workspace_manager()

private_ws = wm.get_private_workspace(session_id)
shared_ws = wm.get_shared_workspace()

await private_ws.write_file("test.txt", "内容")
content = await private_ws.read_file("test.txt")
files = await private_ws.list_files()
```

## 命令系统

### 注册命令

在 `nbot/commands.py` 或 `nbot/ai_commands.py` 中使用装饰器注册命令：

```python
from nbot.commands import register_command

@register_command("/hello", help_text="/hello -> 你好")
async def handle_hello(msg, is_group=True):
    await msg.reply(text="你好！")

@register_command("/test", help_text="/test -> 测试命令", admin_show=True)
async def handle_test(msg, is_group=True):
    await msg.reply(text="测试成功")
```

### 命令参数

```python
@register_command("/echo", help_text="/echo <内容> -> 回声")
async def handle_echo(msg, is_group=True):
    content = msg.raw_message.replace("/echo", "").strip()
    await msg.reply(text=content)
```

## Web 后台开发

### 添加 API 路由

在 `nbot/web/routes/` 中添加新路由：

```python
from flask import Blueprint, jsonify

bp = Blueprint('my_feature', __name__)

@bp.route('/api/my-feature', methods=['GET'])
def get_my_feature():
    return jsonify({"status": "ok"})
```

### 注册路由

在 `nbot/web/server.py` 中注册：

```python
from nbot.web.routes import my_feature

app.register_blueprint(my_feature.bp)
```

## 扩展开发建议

### 添加新频道

1. 在 `nbot/channels/` 创建适配器类
2. 继承 `BaseChannelAdapter`
3. 实现必要的方法
4. 在 `registry.py` 中注册

### 添加新工具

1. 在 `nbot/services/tools.py` 中使用 `@register_tool` 装饰器
2. 实现工具函数
3. 在 Web 后台配置工具权限

### 添加新技能

1. 在 `nbot/plugins/skills/` 创建技能类
2. 继承 `Skill` 基类或使用 `@skill` 装饰器
3. 实现 `execute` 方法

### 添加新协议

1. 在 `nbot/core/protocols/` 创建协议适配器
2. 实现消息格式转换
3. 在 `model_adapter.py` 中注册

## 配置说明

### 环境变量 (.env)

```env
# 必需
WEB_PASSWORD=your_password

# QQ 配置
BOT_UIN=123456
ROOT=789012
WS_URI=ws://localhost:3001
TOKEN=napcat_token
WEBUI_URI=http://localhost:6099

# AI 配置（可在 Web 端配置）
```

### 模型配置

在 Web 后台的 AI 配置中心可以配置：

- API 密钥
- 基础 URL
- 模型名称
- 能力声明（supports_tools, supports_reasoning, supports_stream）
- 自定义价格（人民币计价）
- 故障转移队列

## 相关链接

- [NapCat 文档](https://napneko.github.io)
- [ncatbot 文档](https://docs.ncatbot.xyz/)
