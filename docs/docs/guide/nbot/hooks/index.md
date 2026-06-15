# hooks - 钩子事件驱动系统

## 概述

`hooks` 是 NekoBot 3.0 的核心模块之一，提供对话生命周期的事件驱动自动化能力。通过在 AI Pipeline 的 27 个关键检查点插入事件，用户可以定义 Hook（钩子）在特定条件下自动执行动作——注入提示词、修改状态、写入记忆、触发工作流等。

**核心设计原则：**
- 事件驱动：Pipeline 在关键节点发出 `RuntimeEvent`，Hook 通过模式匹配订阅事件
- 条件过滤：支持身份、频道、情绪、关系阈值、时间段等多维条件（AND 逻辑）
- 安全限制：每轮最多触发 20 个 Hook，事件链最大深度 5 层，防止失控
- 可扩展：内置 8 种动作类型，支持通过 `register()` 注册自定义动作

## 架构总览

```
AIPipeline
  │
  ├── conversation.before_receive
  ├── pipeline.before_attachments / after
  ├── pipeline.before_knowledge / after
  │
  ├── CharacterRuntime.before_turn
  │   ├── character.before_turn.started
  │   ├── character.before_turn.after_profile_load
  │   ├── character.before_turn.after_memory_retrieve
  │   ├── character.before_turn.after_world_book_match
  │   ├── character.before_turn.after_reaction_plan
  │   └── character.before_turn.finished
  │
  ├── pipeline.before_prompt_render / after
  ├── pipeline.before_model_call / after / stream_chunk
  ├── pipeline.before_reply_send / after
  │
  ├── CharacterRuntime.after_turn
  │   ├── character.after_turn.started
  │   ├── character.after_turn.after_state_update
  │   └── character.after_turn.finished
  │
  ├── memory.after_extract
  ├── state.changed / relationship.changed
  └── tool.before_call / after_call

         │  每个检查点发出 RuntimeEvent
         ▼
┌─────────────────────────────────────────────┐
│              HookManager                     │
│  emit_event(event)                           │
│    ├── match: 事件模式 + 作用域过滤          │
│    ├── evaluate: ConditionEvaluator          │
│    ├── execute: ActionExecutor               │
│    └── log: HookExecutionLog                 │
└─────────────────────────────────────────────┘
```

## 核心类

### RuntimeEvent

事件数据对象，表示 Pipeline 中的一个检查点事件。

```python
from nbot.hooks import RuntimeEvent

event = RuntimeEvent(
    type="character.before_turn.finished",
    source="character_runtime",
    conversation_id="conv_abc123",
    character_id="char_xyz",
    user_id="user_001",
    payload={"mood": "happy", "energy": 85},
)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | `str` | 事件类型，支持通配符匹配 |
| `source` | `str` | 事件来源标识 |
| `conversation_id` | `str` | 会话 ID |
| `character_id` | `str` | 角色 ID（可选） |
| `user_id` | `str` | 用户 ID（可选） |
| `group_id` | `str` | 群聊 ID（可选） |
| `payload` | `dict` | 事件负载数据 |
| `metadata` | `dict` | 附加元数据 |

### ConversationHook

钩子定义，监听特定事件并执行一组动作。

```python
from nbot.hooks import ConversationHook

hook = ConversationHook(
    name="开心时注入撒娇提示词",
    event="character.before_turn.finished",
    scope="character",
    character_id="char_xyz",
    conditions={"mood_is": "happy", "affection_gte": 70},
    actions=[
        {"type": "prompt_inject", "key": "mood_hint", "content": "角色心情很好，倾向于撒娇", "priority": 50},
        {"type": "state_delta", "field": "energy", "delta": 5},
    ],
    enabled=True,
    priority=10,
)
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | `str` | - | 钩子名称 |
| `event` | `str` | - | 监听的事件类型，支持通配符（如 `character.*`） |
| `scope` | `str` | `"global"` | 作用域：`global` / `character` / `conversation` / `user` |
| `conditions` | `dict` | `{}` | 触发条件（AND 逻辑） |
| `actions` | `list[dict]` | - | 要执行的动作列表 |
| `enabled` | `bool` | `True` | 是否启用 |
| `priority` | `int` | `0` | 优先级（数值越小越先执行） |
| `timeout_ms` | `int` | `3000` | 单次执行超时（毫秒） |
| `max_retries` | `int` | `0` | 失败重试次数（失败、超时、部分失败均会重试） |
| `permissions` | `dict` | `{}` | 权限限制（见下表） |

**permissions 字段说明：**

| 键 | 类型 | 说明 | 示例 |
|----|------|------|------|
| `channels` | `list[str]` | 白名单：只允许这些频道触发 | `["web", "qq"]` |
| `deny_channels` | `list[str]` | 黑名单：禁止这些频道触发 | `["telegram"]` |

### HookExecutionLog

执行日志，记录每次 Hook 触发的结果。

| 字段 | 类型 | 说明 |
|------|------|------|
| `hook_id` | `str` | 触发的 Hook ID |
| `event_id` | `str` | 触发事件 ID |
| `status` | `str` | `success` / `partial` / `failed` / `skipped` / `timeout` |
| `actions_executed` | `int` | 已执行的动作数 |
| `error` | `str` | 错误信息（可选） |
| `duration_ms` | `int` | 执行耗时（毫秒） |

### HookManager

中央协调器，负责 Hook 的 CRUD、事件匹配、条件评估和动作执行。通过 `get_hook_manager()` 获取全局单例。

```python
from nbot.hooks.manager import get_hook_manager

manager = get_hook_manager(data_dir="data")

# 添加 Hook
manager.add_hook(hook)

# 发出事件（通常由 Pipeline 自动调用）
logs = await manager.emit_event(event, context={})

# 查询执行日志
logs = manager.get_execution_logs(hook_id="hk_...", limit=20)

# 统计信息
stats = manager.get_stats()
```

**安全常量：**

| 常量 | 值 | 说明 |
|------|-----|------|
| `_MAX_HOOKS_PER_TURN` | 20 | 每轮最多触发的 Hook 数 |
| `_MAX_EVENT_CHAIN_DEPTH` | 5 | 事件链最大嵌套深度 |

## 条件系统

`ConditionEvaluator` 评估 Hook 的触发条件，所有条件之间为 AND 逻辑（全部满足才触发）。

### 支持的条件类型

| 条件键 | 类型 | 说明 |
|--------|------|------|
| `character_id` | `str` | 匹配角色 ID |
| `user_id` | `str` | 匹配用户 ID |
| `channel` | `str` | 匹配频道（`qq` / `web` / `telegram`） |
| `mood_is` | `str` | 角色心情等于指定值 |
| `mood_is_not` | `str` | 角色心情不等于指定值 |
| `affection_gte` / `affection_lte` | `float` | 好感度阈值 |
| `trust_gte` / `trust_lte` | `float` | 信任度阈值 |
| `familiarity_gte` / `familiarity_lte` | `float` | 熟悉度阈值 |
| `dependency_gte` / `dependency_lte` | `float` | 依赖度阈值 |
| `security_gte` / `security_lte` | `float` | 安全感阈值 |
| `jealousy_gte` / `jealousy_lte` | `float` | 嫉妒度阈值 |
| `energy_gte` / `energy_lte` | `float` | 精力阈值 |
| `time_range` | `[str, str]` | 时间段限制，格式 `["HH:MM", "HH:MM"]`，支持跨午夜 |
| `event_source` | `str` | 匹配事件来源 |

### 条件示例

```json
{
  "mood_is": "happy",
  "affection_gte": 60,
  "channel": "qq",
  "time_range": ["08:00", "22:00"]
}
```

## 动作系统

`ActionExecutor` 执行 Hook 定义的动作。内置 8 种动作类型，可通过 `register()` 扩展。

### 内置动作类型

| 动作类型 | 说明 | 关键参数 |
|----------|------|----------|
| `prompt_inject` | 注入提示词到 PromptStack | `key`, `content`, `priority`, `scope` |
| `state_delta` | 修改角色状态字段 | `field`, `delta`（mood_intensity 限 0-1，energy 限 0-100） |
| `relationship_delta` | 修改关系字段 | `field`, `delta`（限 0-100） |
| `memory_write` | 写入角色记忆 | `content`, `memory_type` |
| `log` | 写入日志 | `message`, `level` |
| `message` | 追加消息到上下文 | `content` |
| `workflow` | 触发工作流执行 | `workflow_id`, `params` |
| `world_book_add` | 添加世界书条目 | `book_id`, `content`, `keywords` |

> **参数兼容**：`state_delta` 和 `relationship_delta` 同时支持 `payload` 格式（如 `{"payload": {"energy": -5}}`）。
> `memory_write` 同时支持 `mem_type` 字段名。`workflow` 同时支持 `workflow` 字段名。

### 动作示例

```json
[
  {"type": "prompt_inject", "key": "mood_hint", "content": "角色很开心", "priority": 50},
  {"type": "state_delta", "field": "energy", "delta": -10},
  {"type": "relationship_delta", "field": "affection", "delta": 5},
  {"type": "memory_write", "content": "用户说了一句很暖心的话", "memory_type": "relationship"},
  {"type": "log", "message": "好感度变化触发", "level": "info"}
]
```

### 扩展自定义动作

```python
from nbot.hooks.actions import ActionExecutor

async def my_custom_action(params, context):
    # 自定义逻辑
    return {"success": True, "detail": "done"}

ActionExecutor.register("my_action", my_custom_action)
```

## 事件总线

`ConversationEventBus` 是会话级事件总线，独立于 Gateway 的 EventBus，用于模块间的事件通信。

```python
from nbot.hooks.event_bus import ConversationEventBus, HookEventType

bus = ConversationEventBus()

# 订阅事件（支持通配符）
bus.subscribe("character.*", callback=my_handler, name="character_watcher")

# 发出事件
delivered = bus.emit(event)

# 查询历史
history = bus.get_history(event_type="character.before_turn.finished", limit=50)
```

### 事件类型一览

> **别名兼容**：文档中的 `pipeline.before_model_call` 等名称可直接用于 Hook 的 `event` 字段，
> 系统会自动映射到代码实际 emit 的事件名（如 `model.before_call`）。两种写法均可生效。

| 分类 | 代码事件名 | 文档别名（也可用） |
|------|----------|----------|
| **会话入口** | `conversation.before_receive` | — |
| **附件处理** | `pipeline.before_attachments`, `pipeline.after_attachments` | — |
| **知识检索** | `pipeline.before_knowledge`, `pipeline.after_knowledge` | — |
| **角色 before_turn** | `character.before_turn.started`, `character.after_profile_load`, `character.after_memory_retrieve`, `character.after_world_book_match`, `character.after_reaction_plan`, `character.before_turn.finished` | `character.before_turn.after_memory_retrieve` 等 |
| **模型调用** | `model.before_call`, `model.after_call`, `model.on_stream_chunk`（仅首块） | `pipeline.before_model_call`, `pipeline.after_model_call`, `pipeline.stream_chunk` |
| **回复发送** | `reply.before_send`, `reply.after_send` | `pipeline.before_reply_send`, `pipeline.after_reply_send` |
| **提示词渲染** | `prompt.before_render`, `prompt.after_render` | `pipeline.before_prompt_render`, `pipeline.after_prompt_render` |
| **角色 after_turn** | `character.after_turn.started`, `character.after_state_update`, `character.after_turn.finished` | `character.after_turn.after_state_update` |
| **记忆抽取** | `memory.after_extract` | — |
| **状态变化** | `state.changed`, `relationship.changed` | — |
| **工具调用** | `tool.before_call`, `tool.after_call` | — |

**当前已实际 emit 的事件**：`conversation.before_receive`、`pipeline.before/after_attachments`、`pipeline.before/after_knowledge`、`prompt.before_render`、`prompt.after_render`、`model.before_call`、`model.on_stream_chunk`（首块）、`model.after_call`、`reply.before_send`、`reply.after_send`、`tool.before_call`、`tool.after_call`，以及 CharacterRuntime 的 `character.after_memory_retrieve`、`character.after_world_book_match`、`character.after_reaction_plan`、`character.before_turn.finished`、`character.after_turn.started`、`character.after_state_update`、`character.after_turn.finished`、`state.changed`、`relationship.changed`、`memory.after_extract`。

## Web API

Hook 系统通过 Web 后台提供完整的管理接口：

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/hooks` | 列出所有 Hook（支持 `scope`、`event`、`enabled` 过滤） |
| POST | `/api/hooks` | 创建 Hook（需 `name` + `event`） |
| GET | `/api/hooks/<hook_id>` | 获取单个 Hook |
| PUT | `/api/hooks/<hook_id>` | 更新 Hook |
| DELETE | `/api/hooks/<hook_id>` | 删除 Hook |
| POST | `/api/hooks/<hook_id>/toggle` | 启用/禁用 Hook |
| POST | `/api/hooks/test` | 发送模拟事件测试 Hook 触发 |
| GET | `/api/hooks/logs` | 查询执行日志 |
| GET | `/api/hooks/events` | 查询事件总线历史 |
| GET | `/api/hooks/stats` | 查询统计信息 |

## 目录结构

```
nbot/hooks/
├── __init__.py        # 模块入口，导出 ConversationHook / HookExecutionLog / RuntimeEvent
├── models.py          # 数据模型定义
├── manager.py         # HookManager 中央协调器
├── event_bus.py       # ConversationEventBus 会话级事件总线
├── conditions.py      # ConditionEvaluator 条件评估器
└── actions.py         # ActionExecutor 动作执行器
```

## 数据存储

```
data/web/
├── hooks.json         # Hook 定义（持久化）
└── hooks_logs.json    # 执行日志（持久化，最多 500 条，裁剪到 250 条）
```
```

## 使用示例

### 自动情绪联动

当角色心情变为伤心时，自动注入安慰提示词并降低精力：

```json
{
  "name": "伤心时注入安慰提示",
  "event": "character.before_turn.finished",
  "conditions": {"mood_is": "sad"},
  "actions": [
    {"type": "prompt_inject", "key": "comfort", "content": "角色正在伤心，回复应温柔安慰", "priority": 30},
    {"type": "state_delta", "field": "energy", "delta": -5}
  ]
}
```

### 好感度里程碑

当好感度超过 80 时，写入长期记忆并触发世界书更新：

```json
{
  "name": "好感度突破80",
  "event": "relationship.changed",
  "conditions": {"affection_gte": 80},
  "actions": [
    {"type": "memory_write", "content": "好感度达到了80，关系进入亲密阶段", "memory_type": "long"},
    {"type": "world_book_add", "content": "用户与角色关系亲密", "keywords": "亲密,好感"}
  ]
}
```

### 定时晚安

在晚间时段自动注入睡前提示：

```json
{
  "name": "晚间睡前模式",
  "event": "character.before_turn.finished",
  "conditions": {"time_range": ["22:00", "06:00"]},
  "actions": [
    {"type": "prompt_inject", "key": "night_mode", "content": "现在是深夜，角色可能困倦，语气温柔", "priority": 20}
  ]
}
```
