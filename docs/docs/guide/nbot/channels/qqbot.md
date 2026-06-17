# qqbot - QQ 官方机器人适配器

## 概述

`qqbot.py` 实现 QQ 官方机器人（Lobster Bot）频道的适配器，基于 QQ 官方 Bot API 通过 WebSocket 长连接接收消息。

与 NapCat/OneBot 的 `qq` 适配器不同，`qqbot` 适配器直接对接 QQ 开放平台，无需部署 NapCat 等第三方框架。

## QQBot vs NapCat 对比

| 特性 | qqbot（官方 Bot） | qq（NapCat） |
|------|-------------------|-------------|
| 协议 | QQ 官方 Bot API | OneBot v11 |
| 传输方式 | WebSocket 长连接 | WebSocket (NapCat) |
| 框架依赖 | 无，直连 QQ 服务器 | 需要 NapCat |
| 认证方式 | AppID + AppSecret | QQ 号 + Token |
| 消息长度限制 | 2000 字符 | 4500 字符 |
| 文件发送 | ❌ 不支持 | ✅ 支持 |
| 私聊支持 | ✅ C2C / 私信 | ✅ |
| 群聊支持 | ✅ 需 @机器人 | ✅ 支持主动接收 |
| 会话 ID 前缀 | `qqbot:` | `qq:` |
| Markdown 渲染 | ❌ | ❌ |

::: tip 选择建议
- 如果你已有 QQ 开放平台的机器人应用，使用 `qqbot`
- 如果你想使用 QQ 个人号登录，使用 `qq`（NapCat）
:::

## QQBotChannelAdapter

```python
from nbot.channels.qqbot import QQBotChannelAdapter

adapter = QQBotChannelAdapter(bot_appid="your_app_id")
```

## 能力声明

```python
def get_capabilities(self) -> ChannelCapabilities:
    return ChannelCapabilities(
        supports_stream=False,           # 不支持流式
        supports_progress_updates=False, # 不支持进度更新
        supports_file_send=False,        # 不支持文件发送
        supports_stop=False              # 不支持停止
    )
```

## 事件处理

### 支持的事件类型

| 事件类型 | 场景 | 说明 |
|---------|------|------|
| `C2C_MESSAGE_CREATE` | 私聊 | 用户私聊机器人 |
| `DIRECT_MESSAGE_CREATE` | 私信 | 用户私信机器人 |
| `GROUP_AT_MESSAGE_CREATE` | 群聊 | 用户在群内 @机器人 |
| `GROUP_MESSAGE_CREATE` | 群聊 | 群内普通消息（需检测 @） |
| `AT_MESSAGE_CREATE` | 群聊 | @提及事件 |

### 私聊消息解析

```python
def _parse_private_message(self, event_type, data, raw_event):
    """解析私聊消息"""
    # 提取 user_openid 作为用户标识
    # 构建 conversation_id: qqbot:private:{user_id}
    # 提取附件（图片/文件）
```

### 群聊消息解析

```python
def _parse_group_message(self, event_type, data, raw_event):
    """解析群聊消息"""
    # 提取 group_openid 和 member_openid
    # 构建 conversation_id: qqbot:group:{group_id}
    # 检测是否 @机器人
    # GROUP_MESSAGE_CREATE 未 @ 时忽略
```

### @提及检测

群聊中，适配器通过以下方式检测是否 @了机器人：

1. **事件类型**：`GROUP_AT_MESSAGE_CREATE` 和 `AT_MESSAGE_CREATE` 自动视为已 @
2. **mentions 数组**：检查 `mentions` 字段中的 `bot_appid` 或 `is_bot` 标记
3. **内容匹配**：检查消息内容中是否包含 `bot_appid`

```python
def _is_bot_mentioned(self, data, content):
    """检测是否 @了机器人"""
    mentions = data.get("mentions") or []
    for item in mentions:
        # 匹配 bot_appid
        # 检查 bot/is_bot 标记
    # 回退：检查内容中是否包含 bot_appid
```

## 消息发送

### REST API 发送

消息通过 QQ 官方 REST API 发送，自动携带 `QQBot {token}` 认证头：

```python
# 私聊
POST https://api.sgroup.qq.com/v2/users/{user_openid}/messages

# 群聊
POST https://api.sgroup.qq.com/v2/groups/{group_openid}/messages
```

### 消息长度限制

单条消息最大 **2000 字符**，超出部分会被截断。如需发送长文本，适配器会按段落自动分割。

### 引用回复

发送消息时如果携带了 `msg_id`，会自动以引用回复的方式发送，方便用户追溯上下文。

## 附件处理

适配器支持接收图片和文件附件：

```python
@staticmethod
def _extract_attachments(data):
    """提取附件列表"""
    for item in data.get("attachments", []):
        content_type = item.get("content_type") or item.get("mime_type")
        # image/* → type: "image"
        # 其他 → type: "file"
```

::: warning 限制
当前版本仅支持**接收**附件，不支持通过 Bot API 发送文件。图片可通过消息中的 URL 查看。
:::

## 角色运行时集成

`QQBotChannelAdapter` 完整实现了 `CharacterChannelAdapter` 协议，可接入角色运行时系统。

### 运行时上下文

```python
def build_runtime_context(self, chat_request) -> ChannelRuntimeContext:
    return ChannelRuntimeContext(
        channel="qqbot",
        conversation_id="qqbot:group:{group_id}",  # 或 qqbot:private:{user_id}
        scene="group",  # 或 "private"
        user_id="{user_openid}",
        group_id="{group_openid}",  # 仅群聊
    )
```

### 渲染策略

```python
def get_render_policy(self, context) -> ChannelRenderPolicy:
    return ChannelRenderPolicy(
        supports_stream=False,
        supports_markdown=False,    # QQ Bot 不支持 Markdown
        supports_image=True,        # 支持图片
        supports_file=False,        # 不支持文件
        supports_quote_reply=True,  # 支持引用回复
        supports_at=True,           # 支持 @提及
        max_text_length=2000,       # 最大 2000 字符
        split_strategy="paragraph", # 按段落分割
    )
```

### 记忆作用域

| 场景 | 作用域 | scope_id 格式 |
|------|--------|--------------|
| 私聊 | `user` | `qqbot:user:{user_openid}` |
| 群聊 | `group` | `qqbot:group:{group_openid}` |

## WebSocket 服务

`QQBotWebSocketService` 管理与 QQ 服务器的 WebSocket 长连接生命周期。

### 连接流程

```text
1. 获取 App Access Token（POST https://bots.qq.com/app/getAppAccessToken）
2. 获取 Gateway URL（GET /gateway/bot）
3. 建立 WebSocket 连接
4. 接收 OP_HELLO，获取心跳间隔
5. 发送 OP_IDENTIFY（携带 token、intents、shard）
6. 启动心跳线程（定期发送 OP_HEARTBEAT）
7. 接收 OP_DISPATCH 事件并处理
```

### Intents 配置

默认订阅以下事件意图：

| Intent | 值 | 说明 |
|--------|-----|------|
| `INTENTS_PUBLIC_MESSAGES` | `1 << 30` | 公域消息事件 |
| `INTENTS_PUBLIC_GROUP_MESSAGES` | `1 << 25` | 群消息事件 |
| `INTENTS_PUBLIC_C2C_MESSAGES` | `1 << 26` | C2C 私聊事件 |

默认 Intents 值为三者按位或的结果。可在频道配置中通过 `intents` 字段自定义。

### 心跳机制

- 心跳间隔由服务器在 `OP_HELLO` 中下发（默认 45000ms）
- 客户端定期发送 `OP_HEARTBEAT`，携带最新序列号
- 服务器回复 `OP_HEARTBEAT_ACK` 确认

## 配置

### Web 界面配置（推荐）

1. 进入 Web 后台 → 频道管理
2. 点击"从预设添加"，选择 **QQ Lobster Bot**
3. 填写 `app_id` 和 `app_secret`
4. 保存后自动启动 WebSocket 连接

预设配置：

```json
{
  "id": "qqbot",
  "name": "QQ Lobster Bot",
  "type": "qqbot",
  "transport": "websocket",
  "config": {
    "app_id": "",
    "app_secret": "",
    "sandbox": false,
    "api_base": ""
  }
}
```

### 环境变量配置

推荐通过环境变量传入敏感凭证，避免明文写入配置文件：

```env
# QQ 官方机器人配置
QQBOT_APP_ID=你的AppID
QQBOT_APP_SECRET=你的AppSecret
```

也可以在频道配置中使用 `app_id_env` / `app_secret_env` 指定自定义环境变量名：

```json
{
  "config": {
    "app_id_env": "MY_CUSTOM_APP_ID_ENV",
    "app_secret_env": "MY_CUSTOM_APP_SECRET_ENV"
  }
}
```

凭证解析优先级：
1. `app_id_env` / `app_secret_env` 指定的环境变量
2. `app_id` / `app_secret` 配置值
3. `QQBOT_APP_ID` / `QQBOT_APP_SECRET` 默认环境变量

### 沙箱模式

开发测试时可启用沙箱模式，使用沙箱 API 地址：

```json
{
  "config": {
    "sandbox": true
  }
}
```

| 模式 | API 地址 |
|------|---------|
| 生产（默认） | `https://api.sgroup.qq.com` |
| 沙箱 | `https://sandbox.api.sgroup.qq.com` |

也可以通过 `api_base` 字段自定义 API 地址。

## Web 管理 API

QQBot 频道提供专用的 REST API 用于生命周期管理：

```http
POST /api/channels/qqbot/<channel_id>/start    # 启动 WebSocket 连接
POST /api/channels/qqbot/<channel_id>/stop      # 停止 WebSocket 连接
GET  /api/channels/qqbot/<channel_id>/status    # 查询连接状态
POST /api/channels/<channel_id>/toggle          # 启用/禁用频道
```

## 会话管理

QQBot 消息会自动创建 Web UI 可见的会话：

- **私聊会话**：`qqbot:private:{user_openid}`，显示为 `QQBot private {user_id前8位}`
- **群聊会话**：qqbot:group:{group_openid}`，显示为 `QQBot group {group_id前8位}`

会话数据保存在 `server.sessions` 中，可在 Web 后台的会话管理页面查看和编辑。

## 命令支持

QQBot 适配器兼容现有的命令系统。以 `/` 开头的消息会自动匹配命令处理器：

```text
用户发送: /help
→ 匹配到 help 命令
→ 在独立线程中执行命令
→ 通过 QQ Bot API 回复结果
```

命令执行使用 `QQBotMessageAdapter` 模拟消息对象，兼容 `nbot.commands` 模块的接口。

## 获取 AppID 和 AppSecret

1. 前往 [QQ 开放平台](https://q.qq.com/) 注册并创建机器人应用
2. 在应用详情页获取 **AppID** 和 **AppSecret**
3. 确保机器人已开通所需的权限（公域消息、群消息、C2C 消息）
4. 将凭证配置到 NekoBot 中

::: warning 安全提示
不要将 AppSecret 直接写入配置文件或提交到 Git 仓库。推荐使用环境变量或 Web 后台的频道管理页面配置。
:::

## 故障排查

### Q: WebSocket 连接失败

**A:** 检查以下配置：

1. `app_id` 和 `app_secret` 是否正确
2. 机器人应用是否已审核通过
3. 网络是否能访问 `api.sgroup.qq.com`
4. 如果使用沙箱模式，确认沙箱环境已正确配置

### Q: 收不到群消息

**A:** QQ 官方机器人在群聊中默认需要 @机器人 才会收到消息。确认：

1. 机器人已加入目标群
2. 用户在群内 @了机器人
3. 机器人已开通群消息相关权限

### Q: 私聊无响应

**A:** 确认：

1. 机器人已开通 C2C 消息权限
2. 用户已向机器人发送过首条消息（部分场景需要用户先发起）
3. 检查 Web 后台日志是否有错误信息

### Q: 消息被截断

**A:** QQ Bot API 单条消息上限为 2000 字符。超出部分会被自动截断。如果需要发送长文本，系统会按段落自动分割发送。
