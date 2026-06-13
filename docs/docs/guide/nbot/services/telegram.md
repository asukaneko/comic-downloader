# telegram - Telegram 集成

## 概述

`telegram_service.py` 提供 Telegram Bot 集成，支持 Webhook 和轮询两种模式。消息通过 Telegram Bot API 收发，内部经 `TelegramChannelAdapter` 解析后走统一 AI 管道。

## Token 解析

```python
from nbot.services.telegram_service import resolve_telegram_token

token = resolve_telegram_token(config)
# 优先级: config["bot_token_env"] 指向的环境变量 > config["bot_token"] > TELEGRAM_BOT_TOKEN
```

## 消息发送

### 文本消息

```python
from nbot.services.telegram_service import send_telegram_message

result = send_telegram_message(
    token, chat_id, "你好",
    reply_to_message_id=12345
)
```

文本自动截断至 4096 字符，禁用网页预览。

### 图片发送

```python
# 通过 URL 或 file_id
from nbot.services.telegram_service import send_telegram_photo

send_telegram_photo(token, chat_id, photo_url, caption="图片说明")

# 通过本地文件上传
from nbot.services.telegram_service import send_telegram_photo_file

send_telegram_photo_file(token, chat_id, "local/image.jpg")
```

### 文件发送

```python
from nbot.services.telegram_service import (
    send_telegram_document,
    send_telegram_document_file,
)

# URL/file_id
send_telegram_document(token, chat_id, doc_url)

# 本地上传
send_telegram_document_file(token, chat_id, "local/file.pdf", filename="report.pdf")
```

### 附件批量发送

```python
from nbot.services.telegram_service import _send_telegram_attachments

_send_telegram_attachments(token, chat_id, attachments, caption=caption)
```

根据附件 `type` 字段分发：`image` 走 `sendPhoto`，其余走 `sendDocument`。支持 data URL、HTTP URL 和本地路径。第一个附件携带 caption，后续附件独立发送。

## Webhook 配置

```python
from nbot.services.telegram_service import set_telegram_webhook

result = set_telegram_webhook(config, "https://your.domain/webhook/telegram")
```

可选配置 `secret_token` 用于 Webhook 请求验证：
- `config["secret_token"]` — 直接指定
- `config["secret_token_env"]` — 从环境变量读取

## 管道回调

`TelegramCallbacks`（`nbot/services/telegram_service.py:239`）：

| 方法 | 说明 |
|------|------|
| `get_system_prompt()` | 从 server personality 读取 |
| `get_workspace_context()` | 会话 ID 前缀 `telegram:` |
| `get_character_context()` | 通过 `get_telegram_character_context()` 获取角色上下文 |
| `send_response()` | 先发送附件（含 caption），文本超 1024 字符时单独再发 |

附件和文本分离发送的原因：Telegram 的 caption 限制为 1024 字符。

## 入口函数

```python
from nbot.services.telegram_service import answer_telegram_update

result = answer_telegram_update(server, channel, update)
```

流程：
1. `TelegramChannelAdapter.parse_update()` 解析 Telegram Update 对象
2. 解析 Bot Token
3. `handle_tool_confirmation()` 检测确认/拒绝命令
4. 构建 `ChatRequest`（附件中注入 `bot_token` 供下载中间件使用）
5. 注入运行时 AI 配置到 context metadata
6. 执行 `AIPipeline.process()`
7. 返回 `{"ok": True, "result": final_content}`

## 附件解析

Telegram 的附件通过 `TelegramChannelAdapter` 将 `photo`、`document`、`voice`、`video`、`audio` 等字段转为统一附件格式。`answer_telegram_update()` 在每个附件中注入 `bot_token`，供 `AttachmentResolver` 下载文件时使用。

## 相关页面

- [feishu - 飞书集成](./feishu.md) — 飞书类似的消息处理架构
- [ai - AI 客户端](./ai.md) — AI 管道核心
