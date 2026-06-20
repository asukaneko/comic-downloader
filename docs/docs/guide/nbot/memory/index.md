# memory - MemoryFS 记忆逻辑文件系统

## 概述

`memory` 模块实现 MemoryFS 记忆逻辑文件系统，作为现有 PromptManager 记忆系统的上层组织层。通过 `path` 字段把记忆条目组织成角色可读的逻辑视图，支持用户关系摘要、日记、剧情摘要三层必读注入到 Prompt。

**核心特性：**
- **逻辑文件系统** - 使用路径组织记忆，支持层次化结构
- **三层必读注入** - 用户关系摘要 + 当前剧情摘要 + 最近日记摘要
- **智能截断** - 按条目数截断，避免切断单条记忆
- **持久化存储** - 独立持久化到 `memory_fs.json`

## 路径规范

MemoryFS 使用类似文件系统的路径组织记忆：

```
characters/{char_id}/general.md           # 角色通用信息
characters/{char_id}/users/{user_id}.md   # 对特定用户的关系摘要
characters/{char_id}/diary/daily.md       # 最近日常日记
characters/{char_id}/diary/weekly.md      # 本周摘要
characters/{char_id}/plot/{conv_id}.md    # 剧情摘要
characters/{char_id}/world/events.md      # 世界事件记录
```

## 核心类

### MemoryFile

记忆文件数据模型。

```python
from nbot.memory.models import MemoryFile

mf = MemoryFile(
    path="characters/neko_girl/users/user_123.md",
    character_id="neko_girl",
    target_id="user_123",
    title="用户关系摘要",
    content="用户喜欢动漫，性格内向...",
    summary="与用户的互动记录",
    tags=["relationship", "user"],
    importance=0.8,
)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `path` | `str` | 逻辑路径（唯一标识） |
| `character_id` | `str` | 关联角色 ID |
| `target_id` | `str` | 目标用户/会话 ID |
| `title` | `str` | 文件标题 |
| `content` | `str` | 文件内容 |
| `summary` | `str` | 内容摘要 |
| `tags` | `List[str]` | 标签列表 |
| `importance` | `float` | 重要性权重（0-1） |
| `version` | `int` | 版本号（自动递增） |
| `source_event_id` | `str` | 来源事件 ID |
| `memory_ids` | `List[str]` | 关联的记忆 ID 列表 |

### MemoryFS

记忆逻辑文件系统管理器。

```python
from nbot.memory import get_memory_fs

# 获取全局单例
fs = get_memory_fs(data_dir="data/web")

# 读取记忆文件
user_mf = fs.read_user("neko_girl", "user_123")
diary_mf = fs.read_diary("neko_girl")
plot_mf = fs.read_plot("neko_girl", "conv_abc")

# 写入记忆文件
fs.write(
    path="characters/neko_girl/users/user_123.md",
    character_id="neko_girl",
    target_id="user_123",
    title="用户关系摘要",
    content="用户喜欢动漫，性格内向...",
    importance=0.8,
)

# 追加日记内容
fs.write(
    path="characters/neko_girl/diary/daily.md",
    character_id="neko_girl",
    content="今天和用户聊了关于动漫的话题",
    append=True,
)
```

## 核心接口

### read(path)

读取逻辑路径对应的记忆文件。

```python
mf = fs.read("characters/neko_girl/users/user_123.md")
if mf:
    print(mf.content)
```

### write(path, **kwargs)

写入或更新逻辑路径的记忆文件。

**参数：**
- `character_id` - 角色 ID
- `target_id` - 目标 ID
- `title` - 标题
- `content` - 内容
- `summary` - 摘要
- `tags` - 标签列表
- `importance` - 重要性权重
- `source_event_id` - 来源事件 ID
- `memory_ids` - 关联记忆 ID 列表
- `append` - 是否追加模式（用于日记）

```python
# 写入新文件
fs.write(
    path="characters/neko_girl/users/user_123.md",
    character_id="neko_girl",
    target_id="user_123",
    title="用户关系摘要",
    content="用户喜欢动漫",
    importance=0.8,
)

# 追加日记内容
fs.write(
    path="characters/neko_girl/diary/daily.md",
    content="今天天气很好",
    append=True,
)
```

### delete(path)

删除逻辑路径的记忆文件。

```python
fs.delete("characters/neko_girl/users/user_123.md")
```

### list_for_character(char_id)

列出指定角色的所有逻辑文件，按重要性降序。

```python
files = fs.list_for_character("neko_girl")
for mf in files:
    print(f"{mf.path}: {mf.title} (importance={mf.importance})")
```

### build_prompt_context(char_id, user_id, conversation_id)

按三层读取策略构建 Prompt 注入文本（必读层）。

**必读层：**
1. 用户关系摘要 - `characters/{char_id}/users/{user_id}.md`
2. 当前剧情摘要 - `characters/{char_id}/plot/{conv_id}.md`
3. 最近日记摘要 - `characters/{char_id}/diary/daily.md`

```python
# 构建 Prompt 上下文
context = fs.build_prompt_context(
    char_id="neko_girl",
    user_id="user_123",
    conversation_id="conv_abc",
)

# 注入到 Prompt
system_prompt = f"""
你是 neko_girl。

{context}

请根据以上信息与用户对话。
"""
```

## 路径辅助方法

| 方法 | 路径模板 | 说明 |
|------|---------|------|
| `path_user(char_id, user_id)` | `characters/{char_id}/users/{user_id}.md` | 用户关系摘要 |
| `path_diary_daily(char_id)` | `characters/{char_id}/diary/daily.md` | 每日日记 |
| `path_diary_weekly(char_id)` | `characters/{char_id}/diary/weekly.md` | 每周摘要 |
| `path_plot(char_id, conv_id)` | `characters/{char_id}/plot/{conv_id}.md` | 剧情摘要 |
| `path_world_events(char_id)` | `characters/{char_id}/world/events.md` | 世界事件 |
| `path_general(char_id)` | `characters/{char_id}/general.md` | 通用信息 |

## 截断策略

MemoryFS 实现智能截断，防止记忆文件无限膨胀：

| 路径类型 | 最大条目数 | 最大字符数 |
|----------|-----------|-----------|
| `diary` | 30 条 | 4000 字符 |
| `plot` | 50 条 | 4000 字符 |
| 其他 | 不限 | 4000 字符 |

**截断规则：**
- 按条目从旧到新丢弃，保留最近的条目
- 不会切断单条记忆（按 `\n\n` 分割）
- 超出字符限制时继续丢弃旧条目

## 与 CharacterRuntime 集成

MemoryFS 已集成到 `CharacterRuntime`，在 `before_turn` 阶段自动注入：

```python
class CharacterRuntime:
    def _inject_memory_fs(self, turn_context, identity):
        """注入 MemoryFS 必读层到 Prompt"""
        memory_fs = get_memory_fs()
        context = memory_fs.build_prompt_context(
            char_id=identity.character_id,
            user_id=identity.target_id,
            conversation_id=turn_context.conversation_id,
        )
        if context:
            turn_context.prompt_text += f"\n\n【记忆文件系统】\n{context}"
```

## 与 Review Pipeline 集成

Review Pipeline 可以将审查结果写入 MemoryFS：

```python
from nbot.memory import get_memory_fs
from nbot.review.models import ReviewOutput

def apply_review_to_memory_fs(review_output: ReviewOutput, character_id: str, user_id: str):
    """将 Review 结果写入 MemoryFS"""
    fs = get_memory_fs()
    
    if review_output.should_write_memory:
        fs.write(
            path=fs.path_user(character_id, user_id),
            character_id=character_id,
            target_id=user_id,
            content=review_output.memory_content,
            importance=review_output.importance,
        )
```

## Web API

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/review/memory-fs` | 获取 MemoryFS 文件列表 |
| GET | `/api/review/memory-fs?path=<path>` | 获取指定路径的文件内容 |

## 数据存储

```
data/web/
└── memory_fs.json    # MemoryFS 索引文件（path → MemoryFile）
```

## 目录结构

```
nbot/memory/
├── __init__.py    # 模块入口
├── fs.py          # MemoryFS 实现
└── models.py      # MemoryFile 数据模型
```

## 使用示例

### 基本使用

```python
from nbot.memory import get_memory_fs

# 获取全局单例
fs = get_memory_fs()

# 写入用户关系摘要
fs.write(
    path=fs.path_user("neko_girl", "user_123"),
    character_id="neko_girl",
    target_id="user_123",
    title="用户关系摘要",
    content="用户喜欢动漫，性格内向，最近在看《进击的巨人》",
    importance=0.8,
)

# 追加日记
fs.write(
    path=fs.path_diary_daily("neko_girl"),
    character_id="neko_girl",
    content="今天和用户聊了关于动漫的话题，用户很开心",
    append=True,
)

# 写入剧情摘要
fs.write(
    path=fs.path_plot("neko_girl", "conv_abc"),
    character_id="neko_girl",
    content="剧情进展到关键时刻，用户选择了勇敢面对",
    importance=0.9,
)

# 构建 Prompt 上下文
context = fs.build_prompt_context("neko_girl", "user_123", "conv_abc")
print(context)
```

### 查询角色的所有记忆文件

```python
files = fs.list_for_character("neko_girl")
for mf in files:
    print(f"路径: {mf.path}")
    print(f"标题: {mf.title}")
    print(f"重要性: {mf.importance}")
    print(f"版本: {mf.version}")
    print("---")
```

## 最佳实践

1. **路径规范** - 严格遵循路径模板，确保一致性
2. **重要性设置** - 根据内容重要性设置合理的 `importance` 值
3. **追加模式** - 日记类内容使用 `append=True`，避免覆盖
4. **定期清理** - 对于不再需要的记忆文件，及时删除
5. **Prompt 注入** - 使用 `build_prompt_context()` 获取必读层内容
