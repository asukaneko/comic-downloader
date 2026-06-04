# 多频道角色运行时

NekoBot 的角色运行时系统支持多频道接入，让 Web、QQ、飞书、Telegram 等频道都能使用同一套角色卡、世界书、记忆和状态系统。

## 架构概览

```text
外部平台事件
  ↓
ChannelAdapter：频道输入/输出适配
  ↓
CharacterRuntimeDispatcher：统一角色运行调度
  ↓
CharacterRuntime：角色卡、世界书、记忆、事件、提示词栈
```

## 支持的频道

| 频道 | 状态 | 触发策略 | 记忆作用域 |
|------|------|----------|-----------|
| Web | ✅ 已支持 | always | conversation |
| QQ | ✅ 已支持 | mention_or_private | group_user |
| 飞书 | ✅ 已支持 | mention_or_private | chat_user |
| Telegram | ✅ 已支持 | private_or_reply | chat_user |

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
# 触发策略
trigger = mention_or_private
# 记忆作用域
memory_scope = group_user

[character_runtime_feishu]
enabled = true
trigger = mention_or_private
memory_scope = chat_user

[character_runtime_telegram]
enabled = true
trigger = private_or_reply
memory_scope = chat_user
```

### 触发策略

| 策略 | 说明 |
|------|------|
| `always` | 所有消息都进入角色运行时 |
| `private_only` | 只有私聊进入 |
| `mention_only` | 只有被 @ 时进入 |
| `mention_or_private` | 私聊总是进入，群聊被 @ 时进入 |
| `keyword` | 命中特定关键词时进入 |
| `manual` | 需要显式命令开启 |

### 记忆作用域

| 作用域 | 说明 | 适用场景 |
|--------|------|----------|
| `conversation` | 按会话隔离 | Web |
| `user` | 按用户隔离 | 私聊 |
| `group` | 按群隔离 | 群共享角色状态 |
| `group_user` | 按群+用户隔离 | QQ 群聊 |
| `chat_user` | 按 chat+user 隔离 | 飞书、Telegram |
| `thread` | 按话题隔离 | 论坛式频道 |

## 新增频道接入

### 1. 实现 CharacterChannelAdapter 协议

```python
from nbot.character.channel_adapter import CharacterChannelAdapter
from nbot.character.channel_context import ChannelRuntimeContext, ChannelRenderPolicy
from nbot.character.runtime_request import CharacterRuntimeResult


class MyChannelAdapter(BaseChannelAdapter, CharacterChannelAdapter):
    channel_name = "my_channel"

    def build_runtime_context(self, chat_request) -> ChannelRuntimeContext:
        return ChannelRuntimeContext(
            channel=self.channel_name,
            conversation_id=chat_request.conversation_id,
            scene="private",
            user_id=chat_request.user_id or "",
        )

    def get_render_policy(self, context: ChannelRuntimeContext) -> ChannelRenderPolicy:
        return ChannelRenderPolicy(
            supports_markdown=True,
            max_text_length=2000,
        )

    def select_character_id(self, context: ChannelRuntimeContext) -> str | None:
        return None  # 使用默认角色

    def resolve_memory_scope(self, context: ChannelRuntimeContext) -> str:
        return "conversation"

    def render_result(
        self,
        result: CharacterRuntimeResult,
        context: ChannelRuntimeContext,
    ) -> list[dict]:
        return [{"type": "text", "content": result.text}]
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

### 3. 添加适配器函数（可选）

在 `nbot/character/adapters/nekobot.py` 中添加：

```python
def get_my_channel_character_context(
    user_id: str,
    personality_name: str = "default",
) -> CharacterIdentity:
    return CharacterIdentity(
        character_id=personality_name,
        target_id=str(user_id),
        scope_id=f"my_channel:{user_id}",
        channel="my_channel",
    )
```

### 4. 配置启用

在 `config.ini` 中添加：

```ini
[character_runtime_my_channel]
enabled = true
trigger = always
memory_scope = conversation
```

## 核心数据结构

### ChannelRuntimeContext

统一频道运行上下文，表达"这条消息来自哪个频道、哪个会话"。

```python
@dataclass
class ChannelRuntimeContext:
    channel: str           # 频道标识
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

### CharacterRuntimeRequest

统一角色运行请求。

```python
@dataclass
class CharacterRuntimeRequest:
    context: ChannelRuntimeContext
    content: str
    sender: str
    user_id: str = ""
    attachments: list = field(default_factory=list)
    character_id: str | None = None
    parent_message_id: str | None = None
    metadata: dict = field(default_factory=dict)
```

### CharacterRuntimeResult

统一角色运行结果。

```python
@dataclass
class CharacterRuntimeResult:
    text: str
    assistant_message: dict
    memory_updates: list = field(default_factory=list)
    events: list = field(default_factory=list)
    tool_call_history: list = field(default_factory=list)
    state_patch: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
```

## 测试

运行角色运行时测试：

```bash
pytest tests/test_qq_character_runtime.py -v
pytest tests/test_character_relationship_initial_state.py -v
```
