# feishu - 飞书集成

## 概述

`feishu_service.py` 和 `feishu_chat_service.py` 提供飞书（Lark）频道集成。前者处理 Webhook 事件回调（轻量级管道），后者支持 WebSocket 长连接（完整 Web 级功能，含会话管理、知识库、工具调用）。

## 凭证解析

`resolve_feishu_credentials()` 从频道配置或环境变量读取应用凭证：

```python
from nbot.services.feishu_service import resolve_feishu_credentials

credentials = resolve_feishu_credentials(channel_config)
# {
#   "app_id": "cli_xxx",
#   "app_secret": "xxx",
#   "encrypt_key": "xxx",
#   "verification_token": "xxx"
# }
```

优先级：环境变量名→直接值→默认环境变量。`resolve_config_secret()` 统一处理该逻辑。

## 事件验证

飞书在配置事件订阅时发送 URL 验证请求，服务端需正确响应 challenge。

### 签名验证

```python
from nbot.services.feishu_service import verify_feishu_request

is_valid = verify_feishu_request(
    config, signature, timestamp, nonce, body
)
```

算法：`SHA256(timestamp + nonce + encrypt_key + body)`。未配置 `encrypt_key` 时跳过验证。

### Token 验证

```python
from nbot.services.feishu_service import verify_feishu_token

is_valid = verify_feishu_token(config, token)
```

### Challenge 处理

```python
from nbot.services.feishu_service import handle_feishu_challenge

response = handle_feishu_challenge(config, data)
# 返回 {"challenge": "xxx"} 完成验证
```

## Tenant Access Token 管理

```python
from nbot.services.feishu_service import get_tenant_access_token

token = get_tenant_access_token(app_id, app_secret)
```

内部调用 `open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal`。返回的 token 用于后续所有 API 调用。

## 消息发送

### 文本消息

```python
from nbot.services.feishu_service import send_feishu_message

result = send_feishu_message(
    token, chat_id, "你好",
    reply_message_id="om_xxx",
    msg_type="text"
)
```

支持回复线程（通过 `reply_message_id` 设为 `root_id`）。

### 图片和文件

图片/文件发送由 `feishu_chat_service.py` 中 `FeishuChatCallbacks.send_response()` 处理，通过 `feishu_ws_service` 的 `send_feishu_image()` / `send_feishu_file()` 实现。支持 data URL、HTTP URL 自动下载到本地临时文件后上传。

## 管道回调

### FeishuCallbacks（Webhook）

用于 Webhook 频道的轻量管道。`nbot/services/feishu_service.py:207`：

| 方法 | 说明 |
|------|------|
| `get_system_prompt()` | 从 server personality 读取 |
| `get_workspace_context()` | 会话 ID 前缀 `feishu:` |
| `get_character_context()` | 通过 `get_feishu_character_context()` 获取角色上下文 |
| `send_response()` | 调用 `send_feishu_message()` 发送回复 |

### FeishuChatCallbacks（WS）

用于 WebSocket 频道的完整管道。`nbot/services/feishu_chat_service.py:31`：

| 方法 | 说明 |
|------|------|
| `load_messages()` | 加载最近 20 条会话历史 |
| `get_system_prompt()` | 优先使用会话级 prompt，回退到 server personality |
| `save_assistant_message()` | 保存 AI 回复到会话 |
| `search_knowledge()` | 集成知识库搜索 |
| `send_response()` | 发送文本 + 附件（图片/文件） |

## FeishuChatService

`nbot/services/feishu_chat_service.py:220` 提供完整 Web 级功能：

- `_get_or_create_session()` — 基于 `chat_id + channel_id` 生成稳定会话 ID，支持 web session 绑定（`/new_agent`）
- `handle_message()` — 入口方法，检查命令或触发 AI 响应
- `_handle_command()` — 通过 `FeishuMessageAdapter` 模拟 QQ Bot 接口执行命令
- `_trigger_ai_response()` — 在后台线程运行 `_process_ai_response()`，含 Gateway 事件记录

## 入口函数

### Webhook 模式

```python
from nbot.services.feishu_service import answer_feishu_event

result = answer_feishu_event(server, channel, event)
```

流程：解析事件→获取 token→确认/拒绝工具调用→构建 ChatRequest→执行管道→返回结果。

### WS 模式

`FeishuChatService.handle_message()` 管理完整生命周期：消息解析→会话管理→命令分发/AI 响应→Gateway 日志。

## 相关页面

- [telegram - Telegram 集成](./telegram.md) — 类似的多通道消息处理
- [ai - AI 客户端](./ai.md) — AI 管道核心
