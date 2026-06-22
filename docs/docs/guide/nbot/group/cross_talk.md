# CrossTalk @mention 跨角色对话

当一轮对话中所有角色发言完毕后，解析回复中的 `@角色名`，触发被 @ 角色的额外对话。对话同步队列执行，每条完成后加入历史再处理下一条。

## 工作流程

```
一轮角色发言完毕
  │
  ▼
collect_mentions_from_round()
  ├── 收集所有已发言角色
  ├── 解析每条回复中的 @mention
  └── 排除已发言角色，返回有序去重列表
  │
  ▼
process_cross_talk()
  ├── 为每个被 @ 角色（最多 max_mentions 个）：
  │   ├── 构建 PipelineContext
  │   ├── 设置 cross_talk_triggered = True（防递归）
  │   ├── 调用 pipeline.process() 获取回复
  │   ├── 通过回调发送消息
  │   └── 将回复加入历史，处理下一个
  └── 返回所有跨角色对话的助手消息
```

## collect_mentions_from_round()

从一轮回复中收集所有被 @ 的角色 ID。

```python
from nbot.group.cross_talk import collect_mentions_from_round

mentions = collect_mentions_from_round(
    round_responses=[
        {"role": "assistant", "content": "@char_b 你觉得呢？", "sender": "char_a"},
        {"role": "assistant", "content": "好的", "sender": "char_c"},
    ],
    character_ids=["char_a", "char_b", "char_c"],
    character_profiles=profiles,
)
# 返回: ["char_b"]  （char_a 和 char_c 已发言，被排除）
```

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `round_responses` | `list[dict]` | 本轮回复列表，每条含 `{role, content, sender}` |
| `character_ids` | `list[str]` | 群聊中所有有效角色 ID |
| `character_profiles` | `dict[str, dict]` | 角色档案字典 `{id: profile_dict}` |

### 行为

1. 构建 `sender_name → character_id` 映射（大小写不敏感）
2. 收集所有已发言角色
3. 解析每条回复中的 `@mention`（使用 `SpeakerScheduler.parse_mentions()`）
4. 排除已发言角色，返回有序去重列表

## process_cross_talk()

顺序处理 @mention 跨角色对话。

```python
from nbot.group.cross_talk import process_cross_talk

results = process_cross_talk(
    mentions=["char_b", "char_d"],
    max_mentions=5,
    pipeline=ai_pipeline,
    callbacks=callbacks,
    group_context=group_context,
    base_metadata=base_metadata,
    chat_request=chat_request,
    adapter=channel_adapter,
)
# 返回: [{"role": "assistant", "content": "...", "sender": "char_b"}, ...]
```

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `mentions` | `list[str]` | 被 @ 的角色 ID 列表（有序） |
| `max_mentions` | `int` | 最多处理的 @mention 数量 |
| `pipeline` | `AIPipeline` | AI Pipeline 实例 |
| `callbacks` | `PipelineCallbacks` | 回调实例 |
| `group_context` | `dict` | 群聊上下文字典 |
| `base_metadata` | `dict` | 原始轮次的 metadata 基础副本 |
| `chat_request` | `ChatRequest` | 原始聊天请求 |
| `adapter` | `ChannelAdapter` | 频道适配器 |
| `build_cross_talk_context` | `Callable` | 可选：构建跨角色对话上下文的回调 |
| `send_cross_talk_message` | `Callable` | 可选：发送跨角色对话消息的回调 |

### 防递归机制

被 @ 角色的 metadata 中设置 `cross_talk_triggered = True`，防止递归触发进一步的 @mention。跨角色对话中产生的 @mention 不会再次触发 CrossTalk。

## 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `GroupConfig.cross_talk_max_mentions` | `5` | 每轮最多处理的 @mention 数量 |
| `DEFAULT_MAX_MENTIONS` | `5` | 模块级默认值 |

## 错误处理

- 单个角色的跨角色对话失败时，记录错误日志并跳过，不影响其他角色
- `send_cross_talk_message` 回调失败时，记录错误并继续
- 最终返回成功生成的助手消息列表
