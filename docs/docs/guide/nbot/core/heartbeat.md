# heartbeat - 心跳思考

## 概述

`heartbeat.py` 实现 NekoBot 的主动消息推送能力（"心跳思考"）。通过 AI 驱动决策，自动判断是否适合向用户发起主动聊天，模拟真人的自然互动节奏。

## 核心类

### HeartbeatCore

```python
class HeartbeatCore:
    def __init__(self, bot_api)
    def load_user_profile(self, user_id) -> dict
    def save_user_profile(self, user_id, profile_data)
    async def update_profile_if_needed(self, user_id, history)
    async def process_user(self, user_id, interval) -> float | None
```

## 工作流程

`process_user(user_id, interval)` 是核心方法：

```
1. 加载用户历史消息（最近 20 条）
2. 加载用户画像（saved_message/profiles/{user_id}.json）
3. 组装系统提示词（角色设定 + 用户画像 + 决策指令）
4. 调用 AI 模型进行"心跳思考"
5. 解析 JSON 响应，决定是否主动发消息
6. 更新用户画像（可选）
7. 返回下次心跳间隔
```

### AI 决策输出格式

AI 必须返回纯 JSON：

```json
{
    "should_chat": true,
    "thought": "用户已经忙完了工作...",
    "messages": ["忙完啦？今天天气不错，出去走走吗？"],
    "next_interval": 4.0,
    "update_profile": {"work_hours": "9-18"}
}
```

- `should_chat` — 是否发起聊天
- `thought` — AI 的思考过程（日志记录用）
- `messages` — 1-3 条要发送的消息
- `next_interval` — 下次心跳间隔（小时）
- `update_profile` — 可选，新识别的用户画像信息

## 用户画像

用户画像保存为 `saved_message/profiles/{user_id}.json`，在心跳思考过程中由 AI 自动识别和更新。画像内容由 AI 自行决定，例如工作时间、兴趣爱好、生活规律等。

```json
{
    "work_hours": "9-18",
    "interests": ["摄影", "咖啡"],
    "timezone": "UTC+8"
}
```

## 消息发送

当 AI 决定发起聊天时，通过 `bot_api.post_private_msg()` 发送私聊消息。每次发送前随机等待 1-5 秒，避免消息排队。

```python
await asyncio.sleep(random.uniform(1, 5))
await self.bot_api.post_private_msg(int(user_id), text=msg_text)
```

## 使用示例

```python
from nbot.core.heartbeat import HeartbeatCore

async def heartbeat_loop(bot_api):
    core = HeartbeatCore(bot_api)
    interval = 2.0  # 初始间隔 2 小时

    while True:
        for user_id in active_users:
            next_interval = await core.process_user(user_id, interval)
            if next_interval:
                interval = next_interval

        await asyncio.sleep(interval * 3600)
```

## 设计原则

1. **AI 驱动** - 是否主动聊天由 AI 根据历史记录和用户画像自主决策
2. **自然节奏** - 通过可变的 `next_interval` 避免机械打卡感
3. **画像自学习** - AI 在每次心跳中自动更新用户画像，越聊越了解用户
4. **JSON 修复** - 使用 `json_repair` 库处理 AI 输出的不标准 JSON
5. **安全下限** - 最小心跳间隔限制为 0.1 小时（6 分钟），防止循环过快
