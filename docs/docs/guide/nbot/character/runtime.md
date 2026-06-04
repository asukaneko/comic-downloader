# 运行时引擎 (CharacterRuntime)

CharacterRuntime 是角色模拟的编排中心，负责协调各个模块完成角色模拟的完整生命周期。

## 职责

`CharacterRuntime` 只做角色模拟编排，不直接处理 HTTP / Socket / QQ。

```python
class CharacterRuntime:
    def __init__(
        self,
        profile_repo,        # 角色卡仓库
        state_repo,          # 状态仓库
        relationship_repo,   # 关系仓库
        memory_service,      # 记忆服务
        signal_analyzer,     # 信号分析器
        planner,             # 反应计划生成器
        prompt_builder,      # 提示词构建器
        state_machine,       # 状态机
        world_book_store,    # 世界书存储（可选）
    )
```

## before_turn

每轮对话前的角色模拟编排。

```python
def before_turn(self, chat_request, identity: CharacterIdentity) -> CharacterTurnContext:
    """
    Args:
        chat_request: 统一聊天请求
        identity: 角色身份标识

    Returns:
        CharacterTurnContext 包含本轮所有角色上下文
    """
```

### 执行流程

```
before_turn
├── 读取角色卡 (profile_repo.get)
├── 读取或创建角色运行时状态 (state_repo.get_or_create)
├── 读取或创建关系状态 (relationship_repo.get_or_create)
├── 检索相关记忆 (memory_service.search)
├── 分析用户输入信号 (signal_analyzer.analyze)
├── 生成反应计划 (planner.plan)
├── 世界书关键词匹配 (_match_world_books)
└── 编译提示词 (_build_prompt，含世界书注入)
```

### 代码示例

```python
from nbot.character.runtime import CharacterRuntime
from nbot.character.models import CharacterIdentity

# 创建身份标识
identity = CharacterIdentity(
    character_id="neko_girl",
    target_id="user_123",
    scope_id="web:session_456",
    channel="web"
)

# 执行 before_turn
turn_context = runtime.before_turn(chat_request, identity)

# 使用 turn_context
print(turn_context.profile.name)           # 角色名称
print(turn_context.state.mood)             # 当前心情
print(turn_context.relationship.affection) # 好感度
print(turn_context.plan.visible_emotion)   # 计划表现的情绪
print(turn_context.prompt_text)            # 编译后的提示词
print(turn_context.world_book_entries)     # 命中的世界书条目
```

## after_turn

每轮对话后的状态更新。

```python
def after_turn(self, chat_request, result, turn_context: CharacterTurnContext) -> None:
    """
    Args:
        chat_request: 统一聊天请求
        result: PipelineResult
        turn_context: before_turn 返回的上下文
    """
```

### 执行流程

```
after_turn
├── 应用状态变化 (state_machine.apply)
│   ├── 更新角色状态
│   └── 更新关系状态
├── 周期 AI 状态评估 (auto_state.update_state_from_recent_turns)
│   ├── 每 6 回合汇总近期对话
│   ├── 调用当前 AI 输出情绪/关系增量
│   └── 限幅后应用到状态与六维关系
├── 保存状态
│   ├── state_repo.save
│   └── relationship_repo.save
└── 记忆抽取 (memory_service.extract_and_save_if_needed)
```

### 自动状态评估

`after_turn` 中除了每轮的 `StateMachine` 外，还会接入 `AutoState`：

- 按 `character_id + scope_id + target_id` 独立计数，互不串扰
- 实际计数键会同时纳入 `target_id`、`session_id` / `conversation_id`、`scope_id`，避免不同角色、用户、会话混在一起
- 遇到错误回复、heartbeat、`skip_auto_memory` 或 `skip_auto_state` 标记时不会计入缓冲
- 累积 6 回合用户消息与角色回复后触发
- 调用当前运行时 AI 配置，请模型只返回 JSON
- 支持调整 `mood`、`mood_intensity_delta`、`energy_delta`
- 支持调整六维关系：`affection`、`trust`、`familiarity`、`dependency`、`security`、`jealousy`
- 写回前会限制情绪强度在 `0.0-1.0`、关系值在 `0-100`，并限制单次变化幅度

可以通过环境变量关闭：

```bash
NBOT_AUTO_CHARACTER_STATE_ENABLED=0
```

也可以在 `data/settings.json` 的 `features.auto_character_state` 中关闭。

### 代码示例

```python
# 模型调用完成后
result = await model.chat(messages)

# 执行 after_turn 更新状态
runtime.after_turn(chat_request, result, turn_context)

# 状态已自动保存
```

## 完整使用示例

```python
from nbot.character.runtime import CharacterRuntime
from nbot.character.repository import (
    ProfileRepository,
    CharacterStateRepository,
    RelationshipRepository,
)
from nbot.character.policies import SignalAnalyzer
from nbot.character.planner import ReactionPlanner
from nbot.character.state_machine import StateMachine
from nbot.character.memory import PromptManagerMemoryAdapter
from nbot.character.models import CharacterIdentity
from nbot.character.storage.world_book_store import WorldBookStore

# 初始化运行时
runtime = CharacterRuntime(
    profile_repo=ProfileRepository(base_dir),
    state_repo=CharacterStateRepository(base_dir),
    relationship_repo=RelationshipRepository(base_dir),
    memory_service=PromptManagerMemoryAdapter(),
    signal_analyzer=SignalAnalyzer(),
    planner=ReactionPlanner(),
    prompt_builder=None,  # 使用默认
    state_machine=StateMachine(),
    world_book_store=WorldBookStore(base_dir),
)

# 创建身份标识
identity = CharacterIdentity(
    character_id="neko_girl",
    target_id="user_123",
    scope_id="web:session_456",
    channel="web"
)

# before_turn: 准备角色上下文
turn_context = runtime.before_turn(chat_request, identity)

# 使用编译后的提示词
messages = [
    {"role": "system", "content": turn_context.prompt_text},
    *history_messages,
]

# 调用模型
result = await model.chat(messages)

# after_turn: 更新状态
runtime.after_turn(chat_request, result, turn_context)
```

## 可选依赖

所有依赖都是可选的，如果某个模块为 None，则跳过对应功能：

```python
# 最小化运行时（只编译角色卡）
runtime = CharacterRuntime(
    profile_repo=profile_repo,
)

# 完整运行时
runtime = CharacterRuntime(
    profile_repo=profile_repo,
    state_repo=state_repo,
    relationship_repo=relationship_repo,
    memory_service=memory_service,
    signal_analyzer=signal_analyzer,
    planner=planner,
    prompt_builder=prompt_builder,
    state_machine=state_machine,
)
```

## 错误处理

运行时内部已经处理了各模块的异常，不会因为某个模块失败而导致整体失败：

```python
# _search_memories 内部捕获异常
def _search_memories(self, identity, chat_request):
    try:
        return self.memory_service.search(...)
    except Exception:
        return []  # 失败返回空列表

# _analyze_signals 内部捕获异常
def _analyze_signals(self, chat_request, state, relationship):
    try:
        return self.signal_analyzer.analyze(...)
    except Exception:
        return None  # 失败返回 None
```

## 与 Pipeline 集成

Pipeline 通过 `CharacterRuntimeContextDispatcher` 统一处理频道配置，然后调用 `CharacterRuntime`：

```python
class AIPipeline:
    def _phase_character_runtime_before_turn(self, ctx, callbacks):
        # 1. 获取运行时和身份（由 callbacks 提供）
        runtime = callbacks.get_character_runtime(ctx)
        identity = callbacks.get_character_context(ctx)
        if not runtime or not identity:
            return

        # 2. 通过 dispatcher 检查配置
        from nbot.character.dispatcher import CharacterRuntimeContextDispatcher, build_scope_id
        config = get_character_runtime_config()
        dispatcher = CharacterRuntimeContextDispatcher(runtime=runtime, config=config)

        # 3. 优先使用 adapter 构建频道上下文
        if ctx.adapter and hasattr(ctx.adapter, "build_runtime_context"):
            runtime_ctx = ctx.adapter.build_runtime_context(ctx.chat_request)
        else:
            runtime_ctx = ChannelRuntimeContext(...)  # fallback

        # 4. is_enabled / trigger / scope_id 检查
        if not dispatcher.is_enabled(runtime_ctx):
            return
        trigger = dispatcher.get_trigger_strategy(runtime_ctx)
        if not dispatcher._should_trigger(trigger, runtime_ctx, ctx.chat_request):
            return
        memory_scope = dispatcher.get_memory_scope(runtime_ctx)
        identity.scope_id = build_scope_id(runtime_ctx, memory_scope)

        # 5. 执行 before_turn
        turn = runtime.before_turn(ctx.chat_request, identity)
        ctx.character_turn = turn

        # 6. 注入 PromptStack
        build_character_injections(ctx.prompt_stack, ...)

    def _phase_character_runtime_after_turn(self, ctx, callbacks, result):
        runtime = callbacks.get_character_runtime(ctx)
        identity = callbacks.get_character_context(ctx)
        if not runtime or not identity or not ctx.character_turn:
            return
        runtime.after_turn(
            chat_request=ctx.chat_request,
            result=result,
            turn_context=ctx.character_turn,
        )
```

> ⚠️ channel 与 scene 的区别：`channel` 是频道标识（qq/telegram/feishu/web），`scene` 是场景类型（private/group）。
> Pipeline 通过 `ctx.metadata["source"]` 获取 channel，`ctx.metadata["channel_type"]` 获取 scene。
> 详见 [channel-runtime.md](./channel-runtime.md)。

## 性能考虑

- **状态缓存**: repository 内部有缓存机制，避免频繁文件 IO
- **记忆检索**: 限制返回数量（默认 8 条）
- **周期评估**: AutoState 每 6 回合才调用一次模型，避免每轮额外增加延迟
- **异步友好**: 不阻塞主线程，可在异步环境中使用
