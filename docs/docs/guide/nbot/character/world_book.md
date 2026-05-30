# 世界书 (World Book)

世界书是实时情感引擎的扩展模块，允许为角色绑定世界观设定，并在用户消息匹配关键词时自动注入到提示词栈中。

## 概述

世界书系统由三个模块组成：

- **world_book_matcher.py** — 多源上下文召回匹配器，支持用户消息 / 助手回复 / 历史上下文 / 场景状态多种触发源
- **world_book_injector.py** — PromptStack 注入器，将命中条目格式化后注册到提示词栈
- **storage/world_book_store.py** — JSON 持久化层，管理世界书及条目的 CRUD

```
当前用户消息
+ 最近助手回复
+ 最近对话历史
+ 角色场景状态
+ 已激活条目
  ↓
WorldBookStore.list_all()              # 加载所有世界书
  ↓
match_entries_v2(context, books, id)   # 多源召回匹配
  ↓
inject_world_book(stack, entries)      # 注入 PromptStack (priority=65)
  ↓
stack.render() → system prompt         # 合成最终提示词
```

## 数据模型

### WorldBookEntry — 世界书条目

```python
@dataclass
class WorldBookEntry:
    id: str = ""                      # 条目唯一标识
    name: str = ""                    # 条目名称
    keywords: List[str] = []          # 关键词列表
    content: str = ""                 # 命中时注入的内容
    enabled: bool = True              # 是否启用
    priority: int = 0                 # 优先级（越高越优先注入）
    case_sensitive: bool = False      # 是否区分大小写
    match_mode: str = "any"           # "any" = 任一命中, "all" = 全部命中

    # 多源召回扩展字段
    trigger_sources: List[str] = ["user"]  # 允许的触发源
    always_on: bool = False           # 是否常驻注入（不需要关键词触发）
    state_triggers: Dict = {}         # 场景状态触发条件
    cooldown_turns: int = 0           # 命中后冷却轮数（0=无冷却）
    max_injections_per_session: int = 0  # 单会话最多注入次数（0=不限）
    tags: List[str] = []              # 标签，用于分类与调试
    entry_type: str = "lore"          # 条目类型
    weight: int = 0                   # 额外权重

    created_at: str = ""
    updated_at: str = ""
```

### trigger_sources 可选值

| 值 | 说明 | 基础分 |
|---|---|---|
| `user` | 当前用户消息触发 | 50 |
| `assistant_recent` | 最近助手回复触发 | 30 |
| `history` | 最近对话历史触发 | 20 |
| `scene_state` | 角色场景状态触发 | 45 |
| — | `always_on=True` 常驻注入 | 100 |

### entry_type 可选值

| 值 | 说明 | 排序优先级 |
|---|---|---|
| `relationship` | 角色与用户关系 | 90 |
| `rule` | 世界规则 | 80 |
| `location` | 地点 | 70 |
| `event` | 剧情事件 | 60 |
| `npc` | NPC 角色 | 50 |
| `faction` | 阵营/组织 | 45 |
| `lore` | 世界观设定（默认） | 40 |
| `style` | 叙事风格 | 35 |
| `secret` | 隐藏真相 | 30 |

### WorldBook — 世界书

```python
@dataclass
class WorldBook:
    id: str = ""                      # 世界书唯一标识
    name: str = ""                    # 世界书名称
    description: str = ""             # 描述
    character_ids: List[str] = []     # 关联角色 ID 列表（空 = 全局生效）
    entries: List[WorldBookEntry] = [] # 条目列表
    enabled: bool = True              # 是否启用
    created_at: str = ""
    updated_at: str = ""
```

## 多源上下文召回

### 召回上下文 — WorldBookRecallContext

描述本轮世界书匹配可使用的所有信息：

```python
@dataclass
class WorldBookRecallContext:
    latest_user_message: str = ""     # 当前用户消息
    recent_messages: List[Dict] = []  # 最近若干轮聊天
    assistant_recent_text: str = ""   # 最近助手回复拼接文本
    history_text: str = ""            # 最近上下文拼接文本
    scene: Dict[str, Any] = {}        # 当前角色场景状态
    active_entry_ids: List[str] = []  # 最近几轮已激活的条目
    character_id: str = ""            # 当前角色 ID
    target_id: str = ""               # 当前用户 ID
    scope_id: str = ""                # 当前会话 ID
```

### 召回配置 — WorldBookRecallConfig

```python
@dataclass
class WorldBookRecallConfig:
    recent_message_limit: int = 6     # 检索最近消息条数
    max_history_chars: int = 2000     # 历史文本最大字符数
    max_total_chars: int = 3000       # 注入总字符上限
    max_entries: int = 8              # 最大注入条目数
    max_always_chars: int = 800       # 常驻条目字符上限
    max_scene_chars: int = 1000       # 场景条目字符上限
    max_keyword_chars: int = 1200     # 关键词条目字符上限
    max_assistant_triggered_entries: int = 3  # 助手回复每轮最多触发条数
    min_assistant_priority: int = 20  # 助手回复触发的最低优先级
    enable_assistant_trigger: bool = True
    enable_history_trigger: bool = True
    enable_scene_trigger: bool = True
    enable_cooldown: bool = True
```

### 匹配流程 — match_entries_v2

```python
def match_entries_v2(
    context: WorldBookRecallContext,
    world_books: List[WorldBook],
    character_id: Optional[str] = None,
    config: Optional[WorldBookRecallConfig] = None,
) -> List[WorldBookMatchResult]:
```

流程：

1. 跳过已禁用的世界书
2. 角色过滤（支持 UUID / 名称双向解析）
3. 遍历每个条目：
   - 常驻条目（`always_on=True`）直接加入，得分 100 + priority + weight
   - 分别检测 user / assistant_recent / history / scene_state 四个触发源
   - 每个命中源累加对应基础分
   - 最终得分 = 各源基础分 + priority + weight
4. 排序：score 降序 → priority 降序 → entry_type 优先级降序 → 内容长度升序
5. 裁剪至 `max_entries`

### 匹配结果 — WorldBookMatchResult

```python
@dataclass
class WorldBookMatchResult:
    entry: WorldBookEntry             # 命中的条目
    trigger_sources: List[str] = []   # 本次命中的触发源
    matched_keywords: List[str] = []  # 命中的关键词
    score: int = 0                    # 总得分
```

### 防止世界书爆炸

- `assistant_recent` 只能触发 `priority >= 20` 的条目
- `assistant_recent` 每轮最多新增 3 个条目
- `assistant_recent` 不触发 `entry_type = secret` 的条目
- 冷却机制：命中后需间隔 `cooldown_turns` 轮才能再次触发

### 场景状态触发

当条目的 `trigger_sources` 包含 `"scene_state"` 时，系统用 `state_triggers` 匹配 `CharacterState.scene`：

```json
{
  "trigger_sources": ["user", "scene_state"],
  "state_triggers": {
    "location": ["白塔", "观星塔"],
    "arc": ["命运循环", "火种仪式"]
  }
}
```

匹配逻辑：如果 `scene.location` 的值在 `["白塔", "观星塔"]` 中，则命中。

## 向后兼容

旧的 `match_entries()` 接口保留，内部包装为 `match_entries_v2()`：

```python
def match_entries(user_message, world_books, character_id=None, max_total_chars=3000):
    context = WorldBookRecallContext(latest_user_message=user_message)
    config = WorldBookRecallConfig(max_total_chars=max_total_chars)
    return [m.entry for m in match_entries_v2(context, world_books, character_id, config)]
```

## PromptStack 注入

注入逻辑位于 `world_book_injector.py`：

```python
def inject_world_book(
    stack: PromptStack,
    entries: List[WorldBookEntry],
    max_total_chars: int = 3000,
) -> None:
```

### 注入规则

1. 单条内容超过 2000 字符时截断
2. 总内容超过 3000 字符时停止添加后续条目
3. 格式化为 `【条目名称】\n内容`，多个条目用空行分隔
4. 添加头部 `以下是在当前对话中触发的世界观设定：`
5. 注册到 PromptStack：
   - key: `"world_book"`
   - priority: `PRIORITY_WORLD_BOOK` = 65
   - scope: `"turn"`（仅本轮生效）

### 优先级位置

```
10  global.safety           # 安全规则
20  app.behavior            # 应用行为
30  character.profile       # 角色卡
40  character.runtime_state # 角色运行时状态
50  character.relationship  # 关系状态
55  character.reaction_plan # 反应计划
60  character.memories      # 角色记忆
65  world_book              # 世界书
70  knowledge.rag           # 知识库
80  tool.instructions       # 工具说明
```

## 存储层

`WorldBookStore` 基于 `JsonStore`，数据存储在 `data/world_books.json`：

```python
class WorldBookStore:
    def __init__(self, base_dir: str):
        self._store = JsonStore(os.path.join(base_dir, "data", "world_books.json"))

    def list_all() -> List[WorldBook]        # 列出所有世界书
    def get(book_id) -> Optional[WorldBook]   # 获取单个世界书
    def create(name, ...) -> WorldBook        # 创建世界书
    def update(book_id, **kwargs)             # 更新世界书元信息
    def delete(book_id) -> bool               # 删除世界书

    def list_entries(book_id)                 # 列出条目
    def add_entry(book_id, entry_data)        # 添加条目
    def update_entry(book_id, entry_id, ...)  # 更新条目
    def delete_entry(book_id, entry_id)       # 删除条目
    def batch_add_entries(book_id, entries)   # 批量添加
```

### 存储格式

```json
{
  "world_books": {
    "<book_id>": {
      "id": "...",
      "name": "...",
      "description": "...",
      "character_ids": ["角色名称"],
      "entries": {
        "<entry_id>": {
          "id": "...",
          "name": "白塔旧誓",
          "keywords": ["白塔", "旧日誓约"],
          "content": "白塔是上一轮命运循环中...",
          "enabled": true,
          "priority": 80,
          "case_sensitive": false,
          "match_mode": "any",
          "trigger_sources": ["user", "assistant_recent", "scene_state"],
          "always_on": false,
          "state_triggers": {
            "location": ["白塔", "观星塔"]
          },
          "cooldown_turns": 2,
          "entry_type": "event",
          "weight": 0,
          "tags": ["风堇", "翁法罗斯"]
        }
      },
      "enabled": true
    }
  }
}
```

## 运行时集成

在 `CharacterRuntime.before_turn()` 中自动调用：

```python
# runtime.py
def before_turn(self, chat_request, identity, recent_messages=None):
    ...
    # 世界书多源上下文召回
    world_book_entries = self._match_world_books(
        identity, chat_request, state=state, recent_messages=recent_messages
    )

    # 编译提示词（包含世界书注入）
    prompt_text = self._build_prompt(
        profile, state, relationship, memories, plan,
        world_book_entries=world_book_entries,
    )
```

在 `AIPipeline._phase_character_runtime_before_turn()` 中注入 PromptStack：

```python
# ai_pipeline.py
# 加载最近消息用于世界书多源召回
recent_messages = callbacks.load_messages(ctx) or []
turn = runtime.before_turn(ctx.chat_request, identity, recent_messages=recent_messages)

if turn.world_book_entries:
    from nbot.character.world_book_injector import inject_world_book
    inject_world_book(ctx.prompt_stack, turn.world_book_entries)
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/world-books` | 列出所有世界书 |
| POST | `/api/world-books` | 创建世界书 |
| GET | `/api/world-books/<book_id>` | 获取单个世界书 |
| PUT | `/api/world-books/<book_id>` | 更新世界书 |
| DELETE | `/api/world-books/<book_id>` | 删除世界书 |
| GET | `/api/world-books/<book_id>/entries` | 列出条目 |
| POST | `/api/world-books/<book_id>/entries` | 添加条目 |
| PUT | `/api/world-books/<book_id>/entries/<entry_id>` | 更新条目 |
| DELETE | `/api/world-books/<book_id>/entries/<entry_id>` | 删除条目 |
| POST | `/api/world-books/<book_id>/entries/batch` | 批量添加条目 |
| POST | `/api/world-books/<book_id>/ai-generate` | AI 生成条目 |
| POST | `/api/world-books/test-match` | 测试关键词匹配 |

### 测试匹配接口

支持两种模式：简单模式（仅用户消息）和多源模式（含最近消息和场景状态）。

**简单模式**（向后兼容）：

```bash
curl -X POST /api/world-books/test-match \
  -H "Content-Type: application/json" \
  -d '{"message": "你好世界", "character_id": "角色名"}'
```

**多源模式**：

```bash
curl -X POST /api/world-books/test-match \
  -H "Content-Type: application/json" \
  -d '{
    "message": "进去看看",
    "character_id": "风堇",
    "recent_messages": [
      {"role": "assistant", "content": "你们抵达了白塔门前，风堇望着塔顶的火种纹章沉默。"}
    ],
    "scene": {
      "location": "白塔",
      "arc": "火种仪式前夕"
    }
  }'
```

返回（多源模式）：

```json
{
  "success": true,
  "matches": [
    {
      "world_book_name": "翁法罗斯",
      "entry_name": "白塔旧誓",
      "entry_id": "white_tower_oath",
      "matched_keywords": ["白塔"],
      "trigger_sources": ["assistant_recent", "scene_state"],
      "score": 155,
      "content_preview": "白塔是上一轮命运循环中..."
    }
  ]
}
```

### 条目更新接口

支持所有新字段：

```bash
curl -X PUT /api/world-books/<book_id>/entries/<entry_id> \
  -H "Content-Type: application/json" \
  -d '{
    "name": "白塔旧誓",
    "entry_type": "event",
    "trigger_sources": ["user", "assistant_recent", "scene_state"],
    "state_triggers": {"location": ["白塔"]},
    "cooldown_turns": 2,
    "weight": 10
  }'
```

## 使用示例

### 创建世界书并添加多源召回条目

```python
from nbot.character.storage.world_book_store import WorldBookStore

store = WorldBookStore(base_dir)

# 创建世界书
book = store.create(
    name="翁法罗斯",
    description="崩坏：星穹铁道世界观设定",
    character_ids=["风堇"],
)

# 添加地点条目（支持助手回复和场景状态触发）
store.add_entry(book.id, {
    "name": "白塔旧誓",
    "keywords": ["白塔", "旧日誓约", "观星塔"],
    "content": "白塔是上一轮命运循环中风堇与用户分别的地方...",
    "match_mode": "any",
    "priority": 80,
    "entry_type": "event",
    "trigger_sources": ["user", "assistant_recent", "history", "scene_state"],
    "state_triggers": {"location": ["白塔", "观星塔"]},
    "cooldown_turns": 2,
})

# 添加常驻规则条目
store.add_entry(book.id, {
    "name": "世界基础规则",
    "keywords": [],
    "content": "这是一个命运循环的世界，每次循环会重置大部分记忆...",
    "always_on": True,
    "entry_type": "rule",
    "priority": 90,
})
```

### 手动匹配与注入（V2）

```python
from nbot.character.world_book_matcher import WorldBookRecallContext, match_entries_v2
from nbot.character.world_book_injector import inject_world_book
from nbot.character.prompt_stack import PromptStack

# 构建召回上下文
context = WorldBookRecallContext(
    latest_user_message="进去看看",
    recent_messages=[
        {"role": "assistant", "content": "你们抵达了白塔门前。"}
    ],
    scene={"location": "白塔", "arc": "火种仪式前夕"},
)

# 多源召回匹配
world_books = store.list_all()
results = match_entries_v2(context, world_books, character_id="风堇")

for r in results:
    print(f"{r.entry.name}: score={r.score}, sources={r.trigger_sources}")

# 注入
stack = PromptStack()
inject_world_book(stack, [r.entry for r in results])
prompt = stack.render(base_prompt)
```
