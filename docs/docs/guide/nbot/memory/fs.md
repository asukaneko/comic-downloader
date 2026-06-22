# MemoryFS 记忆逻辑文件系统

使用路径组织记忆条目，支持层次化结构、三层必读注入和智能截断。

## 获取单例

```python
from nbot.memory import get_memory_fs

fs = get_memory_fs(data_dir="data/web")
```

## 路径规范

所有路径以 `characters/{char_id}/` 为根：

| 路径模板 | 说明 | 示例 |
|----------|------|------|
| `characters/{char_id}/general.md` | 角色通用信息 | `characters/neko_girl/general.md` |
| `characters/{char_id}/users/{user_id}.md` | 对特定用户的关系摘要 | `characters/neko_girl/users/user_123.md` |
| `characters/{char_id}/diary/daily.md` | 最近日常日记 | `characters/neko_girl/diary/daily.md` |
| `characters/{char_id}/diary/weekly.md` | 本周摘要 | `characters/neko_girl/diary/weekly.md` |
| `characters/{char_id}/plot/{conv_id}.md` | 剧情摘要 | `characters/neko_girl/plot/conv_abc.md` |
| `characters/{char_id}/world/events.md` | 世界事件记录 | `characters/neko_girl/world/events.md` |

### 路径辅助方法

```python
fs.path_user(char_id, user_id)          # characters/{char_id}/users/{user_id}.md
fs.path_diary_daily(char_id)            # characters/{char_id}/diary/daily.md
fs.path_diary_weekly(char_id)           # characters/{char_id}/diary/weekly.md
fs.path_plot(char_id, conv_id)          # characters/{char_id}/plot/{conv_id}.md
fs.path_world_events(char_id)           # characters/{char_id}/world/events.md
fs.path_general(char_id)                # characters/{char_id}/general.md
```

## 核心操作

### read(path)

读取逻辑路径对应的记忆文件。

```python
mf = fs.read("characters/neko_girl/users/user_123.md")
if mf:
    print(mf.content)
```

### write(path, **kwargs)

写入或更新逻辑路径的记忆文件。

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
    character_id="neko_girl",
    content="今天和用户聊了关于动漫的话题",
    append=True,
)
```

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

## 三层必读注入

`build_prompt_context(char_id, user_id, conversation_id)` 按三层读取策略构建 Prompt 注入文本：

| 层级 | 路径 | 说明 |
|------|------|------|
| 1 | `users/{user_id}.md` | 用户关系摘要 |
| 2 | `plot/{conv_id}.md` | 当前剧情摘要 |
| 3 | `diary/daily.md` | 最近日记摘要 |

```python
context = fs.build_prompt_context("neko_girl", "user_123", "conv_abc")
```

输出格式：

```
## 用户关系
用户喜欢动漫，性格内向...

## 当前剧情
剧情进展到关键时刻...

## 最近日记
今天和用户聊了关于动漫的话题...
```

## 截断策略

防止记忆文件无限膨胀的智能截断：

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

在 `before_turn` 阶段自动注入：

```python
class CharacterRuntime:
    def _inject_memory_fs(self, turn_context, identity):
        memory_fs = get_memory_fs()
        context = memory_fs.build_prompt_context(
            char_id=identity.character_id,
            user_id=identity.target_id,
            conversation_id=turn_context.conversation_id,
        )
        if context:
            turn_context.prompt_stack.add_injection(
                key="memory_fs_context",
                content=context,
                priority=200,
            )
```

## 与 Review Pipeline 集成

`CharacterRuntime._sync_review_to_memory_fs()` 在 after_turn 阶段将 Review 结果写入 MemoryFS：
1. 用户关系摘要（来自 ReviewOutput.memory_items）
2. 日记条目（每轮追加）
3. 剧情摘要（当 plot_update 产生时）

## Web API

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/review/memory-fs` | 获取 MemoryFS 文件列表 |
| GET | `/api/review/memory-fs?path=<path>` | 获取指定路径的文件内容 |

## 数据存储

持久化在 `data/web/memory_fs.json`，JSON 格式：

```json
{
  "characters/neko_girl/users/user_123.md": {
    "path": "characters/neko_girl/users/user_123.md",
    "character_id": "neko_girl",
    "target_id": "user_123",
    "title": "用户关系摘要",
    "content": "...",
    "importance": 0.8,
    "version": 3,
    "updated_at": "2026-06-22T14:30:00"
  }
}
```
