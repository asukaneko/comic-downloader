# 多频道角色运行时

NekoBot 的角色运行时系统支持多频道接入，让 Web、QQ、飞书、Telegram 等频道都能使用同一套角色卡、世界书、记忆和状态系统。

## 架构概览

```text
外部平台事件
  ↓
ChannelAdapter（频道输入/输出适配）
  ├── parse_event() → 原始事件解析
  └── build_runtime_context() → ChannelRuntimeContext
  ↓
CharacterRuntimeContextDispatcher（统一调度）
  ├── is_enabled() → 频道/全局开关
  ├── _should_trigger() → 触发策略判断
  ├── resolve_memory_scope() → 记忆作用域（配置优先于 adapter）
  └── build_scope_id() → 构建隔离 key
  ↓
CharacterRuntime（角色卡、世界书、记忆、事件、提示词栈）
  ↓
Pipeline（AI 调用、after_turn、token 统计）
```

## 支持的频道

| 频道 | adapter 实现 | 默认触发策略 | 默认记忆作用域 | 说明 |
|------|-------------|-------------|--------------|------|
| Web | 未实现协议 | always | conversation | Web 有独立运行路径，不经过 dispatcher |
| QQ | ✅ `QQChannelAdapter` | mention_or_private | group (群) / user (私) | `is_mentioned` 从 CQ 码 `at` 段检测 |
| 飞书 | ✅ `FeishuChannelAdapter` | always | group (群) / user (私) | 暂无 `is_mentioned` 检测 |
| Telegram | ✅ `TelegramChannelAdapter` | private_or_reply | group (群) / user (私) | `is_reply_to_bot` 从 `reply_to_message.from.is_bot` 检测 |

## 配置说明

### config.ini 配置

```ini
[character_runtime]
# 全局默认是否启用角色运行时
default_enabled = true
# 默认角色卡 ID（留空则使用当前激活的角色）
default_character_id =

[character_runtime_qq]
# QQ 频道是否启用角色运行时
enabled = true
# 触发策略：mention_or_private 表示私聊总是触发，群聊被 @ 时触发
trigger = mention_or_private
# 记忆作用域：group_user = 群内每个用户独立关系状态
memory_scope = group_user
# 是否启用旧版 personality.json prompt（过渡期使用）
legacy_prompt_enabled = false

[character_runtime_feishu]
enabled = true
trigger = always
memory_scope = group

[character_runtime_telegram]
enabled = true
trigger = private_or_reply
memory_scope = group
```

### 触发策略

| 策略 | 说明 | 适用频道 |
|------|------|----------|
| `always` | 所有消息都进入角色运行时 | 飞书、Web |
| `private_only` | 只有私聊进入 | — |
| `mention_only` | 只有被 @ 时进入 | QQ（严格模式） |
| `mention_or_private` | 私聊总是进入，群聊被 @ 时进入 | QQ（推荐） |
| `private_or_reply` | 私聊总是进入，群聊回复机器人时进入 | Telegram |
| `keyword` | 命中 `trigger_keywords` 列表中的关键词时进入 | 任意频道 |
| `manual` | 需要 `chat_request.character_mode=True` 显式开启 | 调试用 |

### 记忆作用域

| 作用域 | 说明 | scope_id 格式 | 适用场景 |
|--------|------|--------------|----------|
| `conversation` | 按会话隔离 | `{channel}:conversation:{conversation_id}` | Web |
| `user` | 按用户隔离 | `{channel}:user:{user_id}` | 私聊 |
| `group` | 按群隔离 | `{channel}:group:{group_id}` | 群共享角色状态 |
| `group_user` | 按群+用户隔离 | `{channel}:group:{group_id}:user:{user_id}` | QQ 群聊（推荐） |
| `chat_user` | 按 chat+user 隔离 | `{channel}:chat:{conversation_id}:user:{user_id}` | 飞书、Telegram |
| `thread` | 按话题隔离 | `{channel}:chat:{conversation_id}:thread:{thread_id}` | 论坛式频道 |

### is_enabled 逻辑

频道显式配置优先于全局默认：

- `enabled = true` → 无论全局设置如何，该频道启用
- `enabled = false` → 无论全局设置如何，该频道禁用
- 未配置 → 使用 `default_enabled`

## 数据流：channel 与 scene 的区别

Pipeline 中有两个关键概念容易混淆：

- **channel**（频道标识）：`qq` / `telegram` / `feishu` / `web` — 决定读取哪个频道的配置
- **scene**（场景类型）：`private` / `group` / `thread` — 决定触发策略和记忆作用域

Pipeline 通过 `ctx.metadata["source"]` 获取 channel，通过 `ctx.metadata["channel_type"]` 获取 scene。

> ⚠️ QQ worker 设置 `channel_type = "private"/"group"`（scene），`source = "qq"`（channel）。
> Telegram/Feishu worker 设置 `channel_type = "telegram"/"feishu"`（channel），`source` 同值。
> Pipeline 优先使用 `source` 作为 channel。

## 核心数据结构

### ChannelRuntimeContext

统一频道运行上下文，表达"这条消息来自哪个频道、哪个会话"。

```python
@dataclass
class ChannelRuntimeContext:
    channel: str           # 频道标识 (qq/telegram/feishu/web)
    conversation_id: str   # 会话 ID
    scene: str             # 场景: private/group/thread/web_session
    user_id: str = ""      # 用户 ID
    user_display_name: str = ""
    group_id: str = ""     # 群组 ID
    group_name: str = ""
    thread_id: str = ""    # 话题 ID
    raw_event_id: str = ""
    metadata: dict = field(default_factory=dict)
```

### ChannelRenderPolicy

频道输出渲染策略，描述频道的输出能力。

```python
@dataclass
class ChannelRenderPolicy:
    supports_stream: bool = False      # 流式输出
    supports_markdown: bool = True     # Markdown
    supports_image: bool = False       # 图片
    supports_file: bool = False        # 文件
    supports_quote_reply: bool = False # 引用回复
    supports_at: bool = False          # @ 提及
    max_text_length: int | None = None # 最大文本长度
    split_strategy: str = "paragraph"  # 分段策略
```

各频道渲染策略：

| 频道 | markdown | image | max_text_length | split_strategy |
|------|----------|-------|-----------------|----------------|
| QQ | ❌ | ✅ | 4500 | paragraph |
| Telegram | ✅ | ✅ | 4096 | paragraph |
| 飞书 | ✅ | ✅ | 4000 | paragraph |

## CharacterChannelAdapter 协议

频道实现此协议即可接入角色运行时：

```python
@runtime_checkable
class CharacterChannelAdapter(Protocol):
    channel_name: str

    def build_runtime_context(self, chat_request) -> ChannelRuntimeContext: ...
    def get_render_policy(self, context) -> ChannelRenderPolicy: ...
    def select_character_id(self, context) -> str | None: ...
    def resolve_memory_scope(self, context) -> str: ...
    def render_result(self, result, context) -> list[dict]: ...
```

Pipeline 在 `_phase_character_runtime_before_turn` 中优先调用 `ctx.adapter.build_runtime_context()`，仅在 adapter 不支持时 fallback 手动构造。

## 触发数据来源

触发策略依赖 adapter 在 `parse_event()` 中写入的标记字段：

| 字段 | 写入位置 | 检测方式 |
|------|---------|---------|
| `is_mentioned` | QQ `parse_event()` → 返回 dict + `metadata["is_mentioned"]` | CQ 码 `at` 段匹配 `bot_uin` 或 `self_id` 或 `at_all` |
| `is_reply_to_bot` | Telegram `parse_update()` → 返回 dict + `metadata["is_reply_to_bot"]` | `reply_to_message.from.is_bot` |

Dispatcher 通过 `_get_meta_field()` 同时检查 `chat_request` 属性和 `metadata` 字典，确保无论 adapter 如何传递数据都能正确读取。

## 新增频道接入

### 1. 实现 CharacterChannelAdapter 协议

```python
from nbot.channels.base import BaseChannelAdapter
from nbot.character.channel_adapter import CharacterChannelAdapter
from nbot.character.channel_context import ChannelRuntimeContext, ChannelRenderPolicy


class MyChannelAdapter(BaseChannelAdapter):
    channel_name = "my_channel"

    # --- CharacterChannelAdapter 协议方法 ---

    def build_runtime_context(self, chat_request) -> ChannelRuntimeContext:
        meta = getattr(chat_request, "metadata", {}) or {}
        return ChannelRuntimeContext(
            channel=self.channel_name,
            conversation_id=getattr(chat_request, "conversation_id", "") or "",
            scene="private" if not meta.get("group_id") else "group",
            user_id=getattr(chat_request, "user_id", "") or "",
            group_id=meta.get("group_id", ""),
        )

    def get_render_policy(self, context: ChannelRuntimeContext) -> ChannelRenderPolicy:
        return ChannelRenderPolicy(
            supports_markdown=True,
            max_text_length=2000,
        )

    def select_character_id(self, context: ChannelRuntimeContext) -> str | None:
        return None  # 使用默认角色

    def resolve_memory_scope(self, context: ChannelRuntimeContext) -> str:
        return "user" if context.scene == "private" else "group"

    def render_result(self, result, context: ChannelRuntimeContext) -> list[dict]:
        text = getattr(result, "text", "") or ""
        if not text:
            return []
        return [{"type": "text", "content": text}]
```

### 2. 在 Callbacks 中添加角色运行时方法

```python
class MyChannelCallbacks(PipelineCallbacks):
    def get_character_context(self, ctx):
        from nbot.character.adapters.nekobot import get_my_channel_character_context
        return get_my_channel_character_context(
            user_id=self.user_id,
            personality_name=self.personality_name,
        )

    def get_character_runtime(self, ctx):
        from nbot.character.adapters.nekobot import get_character_runtime_from_server
        return get_character_runtime_from_server(self.server)
```

### 3. 在 worker 中设置正确的 metadata

```python
ctx = PipelineContext(chat_request=chat_request, adapter=adapter)
ctx.metadata["channel_type"] = "private" if not group_id else "group"  # scene
ctx.metadata["source"] = "my_channel"  # channel（用于读取配置）
```

### 4. 配置启用

在 `config.ini` 中添加：

```ini
[character_runtime_my_channel]
enabled = true
trigger = always
memory_scope = conversation
```

## 测试

运行角色运行时测试：

```bash
# dispatcher 单元测试（scope_id、is_enabled、触发策略、adapter 协议）
pytest tests/test_character_dispatcher.py -v

# 角色运行时集成测试
pytest tests/test_qq_character_runtime.py -v
pytest tests/test_character_relationship_initial_state.py -v
```

测试覆盖范围（59 个用例）：
- `build_scope_id` 9 种场景（6 种 scope + unknown/empty_user/empty_group）
- `is_enabled` 5 种场景（channel 覆盖全局、未配置跟随全局、未知频道）
- `_should_trigger` 8 种策略（always/private_only/mention_only/mention_or_private/private_or_reply/keyword/manual/unknown）
- `_get_meta_field` 6 种场景（属性/字典/优先级/默认值/无 metadata/回复标记）
- adapter 协议：QQ 7 个、Telegram 5 个、飞书 4 个
- `render_result` 3 个（正常/空文本/不泄露 prompt_text）
