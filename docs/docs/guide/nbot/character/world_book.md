# 世界书 (World Book)

世界书是实时情感引擎的扩展模块，允许为角色绑定世界观设定，并在用户消息匹配关键词时自动注入到提示词栈中。

## 概述

世界书系统由三个模块组成：

- **world_book_matcher.py** — 关键词匹配器，扫描用户消息并返回命中的世界书条目
- **world_book_injector.py** — PromptStack 注入器，将命中条目格式化后注册到提示词栈
- **storage/world_book_store.py** — JSON 持久化层，管理世界书及条目的 CRUD

```
用户消息
  ↓
WorldBookStore.list_all()          # 加载所有世界书
  ↓
match_entries(message, books, id)  # 关键词匹配
  ↓
inject_world_book(stack, entries)  # 注入 PromptStack (priority=65)
  ↓
stack.render() → system prompt     # 合成最终提示词
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
    created_at: str = ""
    updated_at: str = ""
```

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

## 关键词匹配

匹配逻辑位于 `world_book_matcher.py`：

```python
def match_entries(
    user_message: str,
    world_books: List[WorldBook],
    character_id: Optional[str] = None,
    max_total_chars: int = 3000,
) -> List[WorldBookEntry]:
```

### 匹配规则

1. 跳过已禁用的世界书 (`enabled=False`)
2. 角色过滤：`character_ids` 为空表示全局生效；否则检查 `character_id` 是否在列表中
   - 支持 UUID 和角色名称混合匹配（自动解析 `custom_personality_presets.json` 中的 UUID）
3. 跳过已禁用的条目或没有关键词的条目
4. 对每个关键词执行子串匹配 (`keyword in message`)
5. 根据 `match_mode` 判断：
   - `"any"`：任一关键词命中即匹配
   - `"all"`：所有关键词都命中才匹配
6. 命中条目按 `priority` 降序排列，总内容不超过 `max_total_chars`（默认 3000 字符）

### UUID / 角色名称解析

前端绑定角色时可能使用预设 UUID 或角色名称。匹配器内置双向解析：

- 读取 `data/web/custom_personality_presets.json` 建立 UUID → 名称映射
- 读取 `data/character/profiles.json` 获取所有角色名称
- 结果带 mtime 缓存，文件未修改时不重复读取

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
65  world_book              # 世界书 ← 新增
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
          "name": "...",
          "keywords": ["关键词1", "关键词2"],
          "content": "命中的世界设定文本...",
          "enabled": true,
          "priority": 0,
          "case_sensitive": false,
          "match_mode": "any"
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
def before_turn(self, chat_request, identity):
    ...
    # 世界书关键词匹配
    world_book_entries = self._match_world_books(identity, chat_request)

    # 编译提示词（包含世界书注入）
    prompt_text = self._build_prompt(
        profile, state, relationship, memories, plan,
        world_book_entries=world_book_entries,
    )
```

在 `AIPipeline._phase_character_runtime_before_turn()` 中注入 PromptStack：

```python
# ai_pipeline.py
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
| POST | `/api/world-books/test-match` | 测试关键词匹配 |

### 测试匹配接口

```bash
curl -X POST /api/world-books/test-match \
  -H "Content-Type: application/json" \
  -d '{"message": "你好世界", "character_id": "角色名"}'
```

返回：

```json
{
  "success": true,
  "matches": [
    {
      "world_book_name": "...",
      "entry_name": "...",
      "matched_keywords": ["关键词1"],
      "content_preview": "..."
    }
  ]
}
```

## 使用示例

### 创建世界书并绑定角色

```python
from nbot.character.storage.world_book_store import WorldBookStore

store = WorldBookStore(base_dir)

# 创建世界书
book = store.create(
    name="东方幻想乡",
    description="东方 Project 世界观设定",
    character_ids=["某角色名称"],
)

# 添加条目
store.add_entry(book.id, {
    "name": "博丽神社",
    "keywords": ["神社", "博丽", "灵梦"],
    "content": "博丽神社是幻想乡中的一座神社，位于博丽大结界边界附近...",
    "match_mode": "any",
    "priority": 10,
})
```

### 手动匹配与注入

```python
from nbot.character.world_book_matcher import match_entries
from nbot.character.world_book_injector import inject_world_book
from nbot.character.prompt_stack import PromptStack

# 匹配
world_books = store.list_all()
entries = match_entries("灵梦今天在神社", world_books, character_id="某角色名称")

# 注入
stack = PromptStack()
inject_world_book(stack, entries)
prompt = stack.render(base_prompt)
```
