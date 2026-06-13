# TTS 语音处理

## 概述

Gateway TTS 处理器负责在文字回复投递成功后，根据每会话的 TTS 开关状态生成语音文件并通过 QQ Bot API 发送语音消息。

## 处理流程

TTS 处理发生在回复投递管线末尾，不作为独立步骤出现在主管线状态表中：

```
Delivery.send_response()
  ├── 发送文字回复到目标频道
  ├── 投递成功 → 调用 TTS 处理器（如果已注册）
  │     ├── 检查频道（仅处理 qq 频道）
  │     ├── 检查 TTS 开关状态
  │     ├── 调用 generate_tts_audio() 生成语音
  │     └── 通过 OneBot API 发送语音消息
  └── 返回 delivery 结果
```

```python
# delivery.py 中的调用点
if self._tts_handler and final_status in ("delivered", "built") and content:
    await self._tts_handler(
        channel_id=channel_id,
        conversation_id=chat_request.conversation_id,
        content=content,
        metadata={"trace_id": trace_id, ...},
    )
```

## GatewayTTSHandler

### 构造函数

```python
class GatewayTTSHandler:
    def __init__(self, switch_manager, qq_bot=None):
        self._switch = switch_manager
        self._qq_bot = qq_bot
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `switch_manager` | SwitchManager | 开关管理器，用于查询 TTS 状态 |
| `qq_bot` | Bot | QQ Bot 实例，用于发送语音消息（支持延迟注入） |

### 延迟注入

`qq_bot` 支持延迟注入，适用于 `qq_bot` 初始化晚于 Gateway 的场景：

```python
handler = GatewayTTSHandler(switch_manager)
# 稍后注入
handler.set_qq_bot(qq_bot)
```

### handle_tts

```python
async def handle_tts(
    self,
    *,
    channel_id: str,
    conversation_id: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
```

处理步骤：

1. **频道过滤**：仅处理 `channel_id == "qq"`，其他频道直接跳过并记录 debug 日志。
2. **TTS 开关检查**：调用 `self._switch.get_switch_state('tts', conversation_id=conversation_id)`。如果返回 `False` 则跳过。
3. **Bot 可用性检查**：`self._qq_bot` 为 `None` 时记录警告并跳过。
4. **语音生成**：调用 `generate_tts_audio(content)` 生成音频文件，返回文件路径。
5. **发送语音**：构建 `MessageChain([Record(audio_path)])`，通过 OneBot API 发送。

## 频道特定配置

当前 TTS 仅支持 QQ 频道，通过 `conversation_id` 区分群聊和私聊：

| 会话类型 | conversation_id 格式 | 发送 API |
|----------|---------------------|----------|
| 群聊 | `qq:group:{group_id}` | `post_group_msg` |
| 私聊 | `qq:private:{user_id}` | `post_private_msg` |

## Switch Manager 集成

### TTS 开关注册

在应用层注册 `tts` 开关：

```python
switch.add_switch('tts', default_value=False, description='TTS语音开关')
```

### 开关查询逻辑

`SwitchManager.get_switch_state()` 的查询顺序：

1. 精确 `conversation_id` 匹配（如 `qq:group:123456`）
2. 用户级匹配（私有会话中的 `user_id`）
3. 群组级匹配（群聊中的 `group_id`）
4. 返回 `switch_configs` 中的默认值（首次使用为 `False`）

### 开关切换

```python
# 通过对话 ID 切换
switch.toggle_switch('tts', conversation_id=conversation_id)

# 通过群组切换
switch.toggle_switch('tts', group_id=str(group_id))

# 通过用户切换
switch.toggle_switch('tts', user_id=str(user_id))
```

开关状态持久化到 `switches.json` 文件。

## 注册 TTS 处理器

```python
from nbot.gateway.tts_handler import create_tts_handler

# 创建 TTS 处理器
tts_handler = create_tts_handler(switch_manager, qq_bot)

# 注册到 Gateway 的 Delivery 层
gateway.delivery.register_tts_handler(tts_handler.handle_tts)
```

Web 端初始化示例（来自 `nbot/web/server.py`）：

```python
from nbot.gateway.tts_handler import create_tts_handler

self._tts_handler = create_tts_handler(switch_manager, self.qq_bot)
gateway.delivery.register_tts_handler(self._tts_handler.handle_tts)
```

## 错误处理

| 场景 | 行为 | 日志级别 |
|------|------|----------|
| 非 QQ 频道 | 静默跳过 | DEBUG |
| TTS 未启用 | 静默跳过 | DEBUG |
| QQ Bot 未初始化 | 跳过，记录警告 | WARNING |
| 语音生成失败 | 跳过，记录警告 | WARNING |
| 音频文件不存在 | 记录错误 | ERROR |
| 无效 conversation_id | 记录警告 | WARNING |
| API 发送异常 | 捕获异常，记录错误 | ERROR |

## 最佳实践

- **默认关闭**：TTS 开关默认值为 `False`，用户/群组需主动开启，避免不必要的 API 调用和费用。
- **长文本截断**：`generate_tts_audio()` 内部应根据 TTS 服务的字符限制对长文本进行截断或分段。
- **异步不阻塞**：TTS 处理在 `delivery.send_response()` 内同步等待，如果 TTS 生成耗时较长，建议改为后台任务。
