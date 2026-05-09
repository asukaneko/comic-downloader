# 实时情感引擎

实时情感引擎（Character Runtime）是 NekoBot 的核心特性之一，它让 AI 角色具备"活人感"——角色不再只是静态的提示词，而是拥有动态的情绪、关系和记忆。

## 概述

实时情感引擎是一个独立的角色模拟层，位于 AI Pipeline 中间，负责：

- **before_turn**: 读取角色卡、状态、关系、记忆，分析用户输入信号，生成 ReactionPlan，编译提示词
- **after_turn**: 更新情绪、关系，写入事件，抽取记忆

```
ChatRequest
  ↓
AIPipeline
  ↓
CharacterRuntime.before_turn()
  ├── 读取角色卡
  ├── 读取角色状态
  ├── 读取关系状态
  ├── 检索相关记忆
  ├── 分析用户输入信号
  ├── 生成 ReactionPlan
  └── 注册 PromptStack 注入项
  ↓
模型调用 / 工具调用
  ↓
CharacterRuntime.after_turn()
  ├── 更新情绪
  ├── 更新关系
  ├── 写入事件
  ├── 抽取记忆
  └── 保存运行时状态
  ↓
ChatResponse
```

## 核心模块

### 1. 数据模型 ([models.md](./models.md))

定义角色引擎的所有数据结构：

- **CharacterProfile** - 静态角色卡
- **CharacterState** - 角色运行时状态
- **RelationshipState** - 关系状态
- **CharacterMemory** - 角色记忆
- **ReactionPlan** - 反应计划
- **CharacterIdentity** - 角色身份标识

### 2. 动态提示词栈 ([prompt_stack.md](./prompt_stack.md))

PromptStack 是实时情感引擎的核心机制，允许任意模块在任意阶段注册提示词注入项，最终统一合成为本轮顶部 system prompt。

**核心原则：**
- 动态注入只在本轮请求生效，不写入历史消息
- 按优先级排序合成
- 可调试、可观察

### 3. 运行时引擎 ([runtime.md](./runtime.md))

CharacterRuntime 是角色模拟的编排中心，协调各个模块完成角色模拟的完整生命周期。

### 4. 反应计划生成器 ([planner.md](./planner.md))

根据角色状态、关系、信号和记忆，生成本轮的 ReactionPlan，控制角色的回复策略。

### 5. 状态机 ([state_machine.md](./state_machine.md))

负责根据信号和反应计划更新角色状态和关系状态：

- **情绪惯性**: 情绪不会一句话突变
- **数值边界**: 所有关系值在 0-100 范围内
- **每轮变化限幅**: 避免暴涨暴跌

### 6. 信号分析器 ([policies.md](./policies.md))

分析用户输入中的情绪信号，为 ReactionPlanner 和 StateMachine 提供输入。

### 7. 角色记忆服务 ([memory.md](./memory.md))

按角色+用户隔离的记忆检索与存储。

### 8. 数据仓库 ([repository.md](./repository.md))

通过 repository 接口访问存储层，业务逻辑不直接读写 JSON。

## 目录结构

```
nbot/character/
├── __init__.py          # 模块入口
├── models.py            # 数据模型
├── compiler.py          # 角色提示词编译器
├── prompt_stack.py      # 动态提示词栈
├── prompt_builder.py    # 提示词构建器
├── runtime.py           # 运行时引擎
├── planner.py           # 反应计划生成器
├── state_machine.py     # 状态机
├── policies.py          # 信号分析器
├── memory.py            # 角色记忆服务
├── repository.py        # 数据仓库接口
├── events.py            # 事件系统与调试快照
├── storage/             # 存储实现
│   ├── __init__.py
│   └── json_store.py    # JSON 文件存储
└── adapters/            # 适配器
    ├── __init__.py
    └── nekobot.py       # NekoBot 桥接适配器
```

## 数据存储

实时情感引擎的数据存储在 `data/character/` 目录：

```
data/character/
├── profiles.json        # 角色卡
├── states.json          # 角色状态
├── relationships.json   # 关系状态
├── memories.json        # 角色记忆
├── events.json          # 事件记录
└── debug_snapshots.json # 调试快照
```

## 使用示例

### 基本使用

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

# 初始化运行时
runtime = CharacterRuntime(
    profile_repo=ProfileRepository(base_dir),
    state_repo=CharacterStateRepository(base_dir),
    relationship_repo=RelationshipRepository(base_dir),
    memory_service=PromptManagerMemoryAdapter(),
    signal_analyzer=SignalAnalyzer(),
    planner=ReactionPlanner(),
    state_machine=StateMachine(),
)

# before_turn: 准备角色上下文
turn_context = runtime.before_turn(chat_request, identity)

# ... 模型调用 ...

# after_turn: 更新状态
runtime.after_turn(chat_request, result, turn_context)
```

### 使用 PromptStack

```python
from nbot.character.prompt_stack import PromptStack

stack = PromptStack()

# 注册提示词注入项
stack.add(
    key="character.runtime_state",
    content="当前心情: 开心\n情绪强度: 0.8",
    priority=PromptStack.PRIORITY_CHARACTER_STATE,
)

stack.add(
    key="character.relationship",
    content="好感: 75/100\n信任: 60/100",
    priority=PromptStack.PRIORITY_CHARACTER_RELATIONSHIP,
)

# 合成最终提示词
composed_prompt = stack.render(base_prompt)
```

## 调试

实时情感引擎支持完整的调试能力，每轮保存调试快照：

```json
{
  "prompt_injections": [],  // 本轮注入的提示词
  "reaction_plan": {},      // 反应计划
  "state_before": {},       // 变化前状态
  "state_after": {},        // 变化后状态
  "relationship_before": {},
  "relationship_after": {},
  "retrieved_memories": [], // 命中的记忆
  "signals": {}             // 检测到的信号
}
```

通过 `CharacterEventLogger` 可以获取调试快照：

```python
from nbot.character.events import CharacterEventLogger

logger = CharacterEventLogger(base_dir)
snapshot = logger.get_latest_debug_snapshot(scope_id)
```

## 与旧系统的兼容性

实时情感引擎设计为可选中间层，默认启用但不会影响现有功能：

- 不启用时，聊天行为与之前完全一致
- 启用时，通过 PromptStack 注入动态提示词
- 旧 personality 数据自动迁移到新的 character 系统
- 记忆系统通过 adapter 保持兼容

## 后续规划

- [ ] SQLite 存储支持
- [ ] LLM 驱动的 ReactionPlanner
- [ ] 主动消息生成
- [ ] 长期事件线
- [ ] 角色间关系
