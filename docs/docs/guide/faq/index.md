# 常见问题 FAQ

## 快速导航

- [安装与启动](#安装与启动)
- [NapCat 与 QQ 连接](#napcat-与-qq-连接)
- [AI 模型配置](#ai-模型配置)
- [多频道配置](#多频道配置)
- [角色情感引擎](#角色情感引擎)
- [记忆与知识库](#记忆与知识库)
- [MCP 集成](#mcp-集成)
- [性能与排错](#性能与排错)

---

## 安装与启动

### Q: 启动报错 `ModuleNotFoundError: No module named 'nbot'`

**A:** 确保在项目根目录运行，且 Python 版本 >= 3.10。如果使用虚拟环境，请先激活：

```bash
cd Ncatbot-comic-QQbot
pip install -r requirements.txt
python bot.py
```

如果仍有问题，检查 `PYTHONPATH` 是否包含项目根目录：

```bash
# Linux/macOS
export PYTHONPATH=.
# Windows PowerShell
$env:PYTHONPATH = "."
```

### Q: 启动后 Web 页面无法访问

**A:** 默认地址为 `http://localhost:5000`。检查以下可能：

1. 端口被占用：`python bot.py --web-port 8080` 指定其他端口
2. Web 模式未开启：使用 `--only-web` 或 `--no-web` 确认模式
3. 防火墙阻挡：检查防火墙是否放行 5000 端口
4. 绑定地址：默认 `127.0.0.1`，远程访问需 `--web-host 0.0.0.0`

### Q: 如何只启动 Web 后台，不启动 QQ Bot？

**A:** 使用 `--only-web` 参数：

```bash
python bot.py --only-web
```

配合自定义端口：`python bot.py --only-web --web-host 0.0.0.0 --web-port 5000`

---

## NapCat 与 QQ 连接

### Q: NapCat 连接失败，报 WebSocket 错误

**A:** 检查 `.env` 中的连接配置：

```env
BOT_UIN=你的QQ号
ROOT=管理员QQ号
WS_URI=ws://localhost:3001
TOKEN=你的NapCat令牌（可选）
```

常见问题：

- **NapCat 未运行**：先启动 NapCatQQ，确认 WebSocket 服务正常
- **WS_URI 地址错误**：NapCat 默认 WebSocket 地址为 `ws://localhost:3001`，如果修改过 NapCat 配置请对应调整
- **端口冲突**：检查 3001 端口是否被其他程序占用
- **Token 不匹配**：如果 NapCat 设置了访问令牌，`.env` 中的 `TOKEN` 必须一致

### Q: NapCat 日志显示连接成功，但 Bot 收不到消息

**A:** 按以下顺序排查：

1. **检查 NapCat 配置**：确认 NapCat 的 WebSocket 客户端已正确配置反向 WebSocket 地址
2. **检查 Bot 日志**：启动时看到 `[BotClient] connected` 表示连接正常
3. **检查过滤器**：消息过滤系统可能拦截了消息，检查 `resources/config/message_filter.json`
4. **检查命令权限**：群聊中可能需要 @机器人 或管理员权限

### Q: 如何切换 QQ 账号？

**A:** 修改 `.env` 中的 `BOT_UIN` 和 `ROOT`：

```env
BOT_UIN=新QQ号
ROOT=新管理员QQ号
```

然后重新启动 Bot。注意 NapCat 也需要使用对应账号登录。

---

## AI 模型配置

### Q: 支持哪些 AI 提供商？

**A:** NekoBot 兼容 OpenAI 协议，因此支持所有 OpenAI 兼容的 API，包括：

| 提供商 | 协议 | 配置方式 |
|--------|------|----------|
| OpenAI (GPT-4o, GPT-4o-mini 等) | OpenAI Chat / Responses | Web 后台 → AI 配置 |
| Anthropic (Claude 系列) | Anthropic Messages | Web 后台 → AI 配置 |
| Google Gemini | Gemini Native | Web 后台 → AI 配置 |
| MiniMax | OpenAI 兼容 | Web 后台 → AI 配置 |
| SiliconFlow | OpenAI 兼容 | Web 后台 → AI 配置 |
| 任何 OpenAI 兼容 API | OpenAI Chat | Web 后台 → AI 配置 |

### Q: API Key 应该配置在哪里？

**A:** 推荐在 **Web 后台的 AI 配置中心** 配置，支持多模型管理：

1. 登录 Web 后台 → AI 配置
2. 点击"添加模型"或编辑已有模型
3. 填写 API Key、Base URL、模型名称
4. API Key 会加密存储在 `data/secure_store.json` 中

也可以在 `.env` 中配置基础模型：

```env
API_KEY=sk-your-key
BASE_URL=https://api.openai.com/v1
MODEL=gpt-4o
```

### Q: 需要配置代理才能访问 OpenAI？

**A:** 不需要单独配置代理。在 AI 模型的 `base_url` 字段中直接填写代理转发地址即可。例如使用 MiniMax 或 SiliconFlow 等国内服务商的 OpenAI 兼容接口。

### Q: 如何配置多模型故障转移？

**A:** 在 Web 后台 → AI 配置 → 故障转移队列中配置：

1. 添加多个模型（如 GPT-4o 为主、Claude Sonnet 为备选）
2. 设置优先级（数值越小优先级越高）
3. 设置 Token 使用上限
4. 当主模型不可用时自动切换

故障转移逻辑：按优先级依次尝试，超时或返回不可恢复错误时自动切换。

### Q: 模型调用返回 401/403 错误？

**A:**

1. 检查 API Key 是否有效、是否过期
2. 检查 API Key 是否有该模型的访问权限
3. 检查 Base URL 是否正确（注意 `/v1` 后缀）
4. 如果使用了代理/转发服务，确认转发配置正确

### Q: 如何查看 Token 用量？

**A:** Web 后台 → Token 用量页面，支持：

- 按模型筛选
- 自定义日期范围
- CSV 导出
- 输入/输出 Token 分别统计

也可通过 MCP 工具 `web_get_token_usage` 查询。

---

## 多频道配置

### Q: 支持哪些消息频道？

**A:** 当前支持 5 种频道：

| 频道 | 类型 | 传输方式 | 配置 |
|------|------|----------|------|
| QQ (NapCat) | qq | WebSocket (NapCat) | `.env` 中配置 |
| QQ 官方机器人 | qqbot | WebSocket (官方 API) | 频道管理页面或 `.env` 配置 |
| Web | web | HTTP + SocketIO | 内置，无需额外配置 |
| Telegram | telegram | Webhook | 频道管理页面配置 |
| Feishu | feishu | Webhook / WebSocket | `.env` 中配置 |

### Q: 如何添加 Telegram 机器人？

**A:**

1. 在 [@BotFather](https://t.me/BotFather) 创建 Bot，获取 Token
2. 在 `.env` 中添加：`TELEGRAM_BOT_TOKEN=你的Token`
3. 启动 Bot：`python bot.py`
4. 进入 Web 后台 → 频道管理 → 添加 Telegram 频道
5. 填写配置，设置 Webhook URL
6. 点击"设置 Webhook"按钮

### Q: 如何配置飞书机器人？

**A:**

1. 在飞书开放平台创建自建应用
2. 获取 App ID 和 App Secret
3. 在 `.env` 中配置：

```env
FEISHU_APP_ID=你的飞书App_ID
FEISHU_APP_SECRET=你的飞书App_Secret
FEISHU_ENCRYPT_KEY=可选
FEISHU_VERIFICATION_TOKEN=可选
```

4. 在飞书开放平台配置 Event 订阅和 Webhook 地址

### Q: 如何配置 QQ 官方机器人？

**A:**

1. 在 [QQ 开放平台](https://q.qq.com/) 创建机器人应用
2. 获取 AppID 和 AppSecret
3. 进入 Web 后台 → 频道管理 → 从预设添加 → 选择 **QQ Lobster Bot**
4. 填写 AppID 和 AppSecret，保存
5. WebSocket 连接会自动建立

也可以通过环境变量配置：

```env
QQBOT_APP_ID=你的AppID
QQBOT_APP_SECRET=你的AppSecret
```

详见 [QQ 官方机器人适配器文档](./nbot/channels/qqbot.md)。

### Q: QQ 官方机器人和 NapCat QQ 有什么区别？

**A:** 两者是完全独立的 QQ 接入方式：

| 对比项 | QQ 官方机器人 (qqbot) | NapCat QQ (qq) |
|--------|----------------------|----------------|
| 账号类型 | 机器人应用（需申请） | 个人 QQ 号 |
| 部署方式 | 直连官方 API | 需部署 NapCat |
| 消息限制 | 2000 字符 | 4500 字符 |
| 文件发送 | 不支持 | 支持 |
| 群聊触发 | 需 @机器人 | 支持主动接收 |

可以根据需求选择，两者可以同时启用。

### Q: QQ 和 Web 频道的会话是否共享？

**A:** 会话相互独立。QQ 频道和 Web 频道有不同的会话存储，互不影响。但角色卡、记忆、知识库等是全局共享的。

---

## 角色情感引擎

### Q: 什么是角色情感引擎？

**A:** 角色情感引擎（Character Runtime）是 NekoBot 的核心特性之一，让 AI 角色具备动态的情绪、关系和记忆：

- **情绪系统**：角色有心情（开心、难过、生气等）和情绪强度
- **六维关系**：好感、信任、熟悉度、依赖度、安全感、嫉妒
- **每轮更新**：每次对话后自动更新状态
- **AI 评估**：每 6 回合调用 AI 自动调整情绪和关系

### Q: 如何创建角色卡？

**A:** 两种方式：

**方法一：Web 后台**

1. 进入"角色管理"页面
2. 点击"创建角色"
3. 填写角色名称、描述、性格、背景设定等
4. 保存后自动生成角色卡

**方法二：通过 MCP 工具**

```bash
# 使用 MCP 客户端创建
mcp> call web_create_character {"name": "猫娘", "personality": "温柔黏人", "scenario": "咖啡馆"}
```

### Q: 如何编辑角色卡？

**A:** Web 后台 → 角色管理 → 选择角色 → 编辑。可以修改：

- 基本信息（名称、描述、头像、立绘）
- 性格特征
- 背景设定
- 行为规则
- 系统提示词
- 开场白
- 标签

也可以通过 MCP 工具 `web_update_character` 编辑。

### Q: 角色数据存储在哪里？

**A:** 角色数据存储在 `data/character/` 目录：

```
data/character/
├── profiles.json          # 角色卡
├── states.json            # 角色运行时状态
├── relationships.json     # 关系状态
├── memories.json          # 角色记忆
├── events.json            # 事件记录
└── debug_snapshots.json   # 调试快照
```

**警告**：不要在手运行时编辑这些文件，可能导致数据损坏。

### Q: 如何查看角色当前的情绪和关系？

**A:** Web 后台 → 角色管理 → 选择角色 → 详情页面。可以查看：

- 当前心情和情绪强度
- 六维关系数值
- 最近的状态变化历史
- 记忆列表

对 QQ/Telegram/飞书频道，可通过"个性旅程"页面查看时间线。

### Q: 什么是世界书（World Book）？

**A:** 世界书是基于关键词匹配的世界观设定注入系统。为角色绑定世界观设定，当用户消息命中关键词时自动注入到提示词栈中。

创建步骤：

1. Web 后台 → 世界书 → 创建世界书
2. 填写名称、描述
3. 关联角色（可选，空表示全局生效）
4. 添加条目：设置关键词和注入内容
5. 保存后启用

### Q: 角色情绪变化太快/太慢怎么办？

**A:** 情绪变化由状态机控制，主要参数：

- **情绪惯性**：情绪不会一句话突变
- **每轮变化限幅**：避免暴涨暴跌
- **数值边界**：所有关系值在 0-100 范围内

这些参数在 `nbot/character/state_machine.py` 中定义，后续版本将支持 Web 配置。

---

## 记忆与知识库

### Q: 记忆和知识库有什么区别？

| 维度 | 记忆 | 知识库 |
|------|------|--------|
| 用途 | 记录用户偏好和对话历史 | 存储领域知识文档 |
| 作用域 | 按角色+用户隔离 | 全局 |
| 检索方式 | 关键词匹配 | 向量检索 (ChromaDB) |
| 存储位置 | `data/memories.json` | `data/knowledge/` |
| 管理页面 | Web 后台 → 记忆管理 | Web 后台 → 知识库 |

### Q: 如何添加记忆？

**A:** 三种方式：

1. **自动记忆**：AI 每 6 回合自动抽取重要信息保存为记忆
2. **手动 Web 添加**：Web 后台 → 记忆管理 → 添加记忆
3. **MCP 工具**：`web_add_memory`

### Q: 如何配置知识库？

**A:**

1. Web 后台 → 知识库
2. 点击"添加文档"或批量导入
3. 填写标题、内容、标签
4. 系统自动向量化存储
5. AI 在对话中自动检索相关内容

### Q: 记忆会自动过期吗？

**A:** 支持短期记忆（short）和长期记忆（long）两种类型：

- **短期记忆**：默认 7 天过期
- **长期记忆**：不过期
- 可在添加记忆时指定 `expire_days` 参数

---

## MCP 集成

### Q: 什么是 MCP？

**A:** MCP (Model Context Protocol) 是 Anthropic 推出的开放标准，允许 AI 智能体通过标准协议调用外部工具。NekoBot 内置 MCP Server，将 Gateway 和 Web 管理能力暴露给 Claude Code、Cursor、ChatGPT Agent 等外部 AI 智能体。

### Q: 如何启动 MCP Server？

**A:**

```bash
# 仅 MCP Server（推荐用于 Claude Code / Cursor）
python bot.py --mcp-only

# Bot + MCP + Web
python bot.py --mcp
```

### Q: 如何连接 Claude Code？

**A:** 在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "nekobot": {
      "command": "python",
      "args": ["bot.py", "--mcp-only"],
      "env": { "PYTHONPATH": "." }
    }
  }
}
```

### Q: MCP 工具调用返回 permission_denied？

**A:**

1. 检查 `config.ini` 中 `[mcp]` 段开启 `admin = true`
2. 确认已**重启 MCP Server**（配置不支持热更新）
3. 对于发送消息等操作，还需要开启对应工具：`send_message_enabled = true`

---

## 性能与排错

### Q: Bot 响应慢怎么办？

**A:** 按优先级优化：

1. **检查网络延迟**：AI API 的响应时间是最大瓶颈
2. **使用国内 API**：如 MiniMax、SiliconFlow 等国内服务商
3. **减少历史消息**：调整 `MAX_HISTORY_LENGTH`（默认 50）
4. **关闭角色引擎**：角色引擎会额外消耗 Token
5. **关闭自动记忆**：设置 `NBOT_AUTO_MEMORY_ENABLED=0`

### Q: Token 消耗太快怎么办？

**A:**

1. 在 AI 模型中设置较低的 `max_tokens` 值
2. 使用成本更低的模型（如 GPT-4o-mini 替代 GPT-4o）
3. 设置 Token 使用上限（故障转移队列）
4. 在 Web 后台 → Token 用量页面监控消耗
5. 减少 `MAX_HISTORY_LENGTH` 减少上下文长度

### Q: 日志在哪里查看？

**A:**

- **Web 后台**：系统日志页面
- **Gateway 事件日志**：Web 后台 → Gateway 日志
- **控制台输出**：启动 Bot 的终端窗口
- **日志文件**：`data/web/` 目录下的日志文件

### Q: 如何彻底重置所有配置？

**A:**

1. 停止 Bot
2. 删除 `data/` 目录（备份重要数据后）
3. 删除 `resources/config/message_filter.json`（如果有）
4. 重新启动 Bot，系统会自动初始化

### Q: Bot 启动后频繁断开重连？

**A:** 常见原因：

1. **WebSocket 不稳定**：检查 NapCat 网络连接
2. **内存不足**：减少模型并发数
3. **Token 超限**：检查是否达到 API 使用限额
4. **操作系统限制**：Linux 下检查文件描述符限制：`ulimit -n`

### Q: 如何备份和恢复数据？

**A:**

1. 停止 Bot
2. 备份整个 `data/` 目录
3. 备份 `resources/config/` 目录
4. 备份 `.env` 配置文件
5. 恢复时：停止 Bot，复制备份文件到对应位置，重新启动

Web 后台也支持配置导入导出（ZIP 格式打包）。
