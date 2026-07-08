# MemoryFS 记忆逻辑文件系统

使用路径组织记忆条目，支持结构化分类（用户人格、角色人格、重要事件、近期摘要）、三层必读注入和智能截断。

## 获取单例

```python
from nbot.memory import get_memory_fs

fs = get_memory_fs(data_dir="data/web")
```

## 结构化分类体系

v3.0.5 起，记忆按以下结构化路径组织，类别与路径双向可映射。v3.1.0 新增 `timeline`（跨会话时间线）与 `life_sim`（角色生活片段）两个类别：

| 类别 | 路径后缀 | 含义 | 是否注入 Prompt | 排序 |
|------|----------|------|----------------|------|
| `user_persona` | `users/{user_id}/user_persona.md` | 用户人格 / 偏好画像 | ✅ | 10 |
| `character_persona` | `users/{user_id}/character_persona.md` | 角色对用户的关系理解 | ✅ | 20 |
| `important_event` | `events/{conversation_id}.md` | 重要事件、剧情节点 | ✅ | 30 |
| `timeline` | `timeline.md` | 跨会话时间线（其他会话的近期生活） | ✅ | 35 |
| `life_sim` | `life_sim/{conversation_id}.md` | 角色生活片段（用户不在场时） | ✅ | 38 |
| `recent_digest` | `users/{user_id}/recent_digest.md` | 近期对话压缩摘要 | ✅ | 40 |
| `legacy` | 其他 | 旧版/未识别路径 | ❌ | 90 |

### 类别归一化

`normalize_memory_category(value)` 将历史别名 / 自由文本归一化到上述类别：

```python
from nbot.memory.fs import normalize_memory_category

normalize_memory_category("user_preference")  # -> "user_persona"
normalize_memory_category("relationship")    # -> "character_persona"
normalize_memory_category("event")           # -> "important_event"
normalize_memory_category("timeline_event")  # -> "timeline"
normalize_memory_category("life_sim_event")  # -> "life_sim"
normalize_memory_category("heartbeat_life")  # -> "life_sim"
normalize_memory_category("diary")           # -> "recent_digest"
normalize_memory_category("something-else")  # -> ""  # 不可识别
```

支持的别名映射（节选）：

| 输入 | 归一化结果 |
|------|------------|
| `user` / `user_profile` / `user_preference` / `persona_user` | `user_persona` |
| `character` / `character_profile` / `relationship` / `persona_character` | `character_persona` |
| `event` / `events` / `plot` / `plot_summary` / `world_event` | `important_event` |
| `timeline_event` / `timeline_event_other` | `timeline` |
| `life_event` / `life_sim_event` / `heartbeat_life` | `life_sim` |
| `digest` / `summary` / `dialogue_digest` / `diary` | `recent_digest` |

### 路径 → 类别反查

`describe_memory_path(path)` 根据路径后缀反查类别与元信息：

```python
from nbot.memory.fs import describe_memory_path

info = describe_memory_path("characters/neko_girl/users/u1/user_persona.md")
# {
#   "category": "user_persona",
#   "category_label": "用户人格",
#   "injects_to_prompt": True,
#   "category_order": 10,
# }
```

## 路径规范

所有路径以 `characters/{char_id}/` 为根。

### 结构化路径（推荐）

| 路径模板 | 类别 | 用途 |
|----------|------|------|
| `characters/{char_id}/general.md` | `legacy` | 角色通用信息 |
| `characters/{char_id}/users/{user_id}/user_persona.md` | `user_persona` | 用户人格 |
| `characters/{char_id}/users/{user_id}/character_persona.md` | `character_persona` | 角色对用户的关系理解 |
| `characters/{char_id}/users/{user_id}/recent_digest.md` | `recent_digest` | 近期对话压缩摘要 |
| `characters/{char_id}/events/{conversation_id}.md` | `important_event` | 重要事件 |
| `characters/{char_id}/timeline.md` | `timeline` | 跨会话时间线（v3.1.0） |
| `characters/{char_id}/life_sim/{conversation_id}.md` | `life_sim` | 角色生活片段（v3.1.0，按会话隔离） |

### 兼容路径（历史）

| 路径模板 | 说明 |
|----------|------|
| `characters/{char_id}/users/{user_id}.md` | 旧版用户关系摘要（兼容保留） |
| `characters/{char_id}/diary/daily.md` | 旧版日记路径（不再注入） |
| `characters/{char_id}/diary/weekly.md` | 本周摘要 |
| `characters/{char_id}/plot/{conv_id}.md` | 剧情摘要 |
| `characters/{char_id}/world/events.md` | 世界事件记录 |

### 路径辅助方法

```python
fs.path_user(char_id, user_id)                      # characters/{char_id}/users/{user_id}.md
fs.path_user_persona(char_id, user_id)              # characters/{char_id}/users/{user_id}/user_persona.md
fs.path_character_persona(char_id, user_id)         # characters/{char_id}/users/{user_id}/character_persona.md
fs.path_recent_digest(char_id, user_id)             # characters/{char_id}/users/{user_id}/recent_digest.md
fs.path_important_events(char_id, conv_id)          # characters/{char_id}/events/{conv_id}.md
fs.path_timeline(char_id)                           # characters/{char_id}/timeline.md
fs.path_life_sim(char_id, conv_id)                  # characters/{char_id}/life_sim/{conv_id}.md
fs.path_diary_daily(char_id)                        # characters/{char_id}/diary/daily.md
fs.path_diary_weekly(char_id)                       # characters/{char_id}/diary/weekly.md
fs.path_plot(char_id, conv_id)                      # characters/{char_id}/plot/{conv_id}.md
fs.path_world_events(char_id)                       # characters/{char_id}/world/events.md
fs.path_general(char_id)                            # characters/{char_id}/general.md
```

## 核心操作

### read(path)

读取逻辑路径对应的记忆文件。

```python
mf = fs.read("characters/neko_girl/users/user_123/user_persona.md")
if mf:
    print(mf.content)
```

### write(path, **kwargs)

写入或更新逻辑路径的记忆文件。

```python
# 写入新文件
fs.write(
    path="characters/neko_girl/users/user_123/user_persona.md",
    character_id="neko_girl",
    target_id="user_123",
    title="用户人格记忆",
    content="用户喜欢动漫",
    importance=0.8,
)

# 追加日记内容
fs.write(
    path="characters/neko_girl/users/user_123/recent_digest.md",
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
- `append` - 是否追加模式（用于日记 / 重要事件）

### delete(path)

删除逻辑路径的记忆文件。

```python
fs.delete("characters/neko_girl/users/user_123/user_persona.md")
```

### list_for_character(char_id)

列出指定角色的所有逻辑文件，按重要性降序。

```python
files = fs.list_for_character("neko_girl")
for mf in files:
    print(f"{mf.path}: {mf.title} (importance={mf.importance})")
```

## Prompt 注入上下文

`build_prompt_context(char_id, user_id, conversation_id)` 按四类结构化路径读取策略构建 Prompt 注入文本：

| 顺序 | 路径 | 说明 |
|------|------|------|
| 1 | `users/{user_id}/user_persona.md` | 用户人格 |
| 2 | `users/{user_id}/character_persona.md` | 角色对用户的关系理解 |
| 3 | `events/{conversation_id}.md` | 重要事件（按需） |
| 3 | `plot/{conversation_id}.md` | 剧情摘要（兼容路径） |
| 4 | `users/{user_id}/recent_digest.md` | 压缩近期摘要 |

```python
context = fs.build_prompt_context("neko_girl", "user_123", "conv_abc")
```

输出格式：

```
【用户人格记忆】
用户喜欢动漫，性格内向...

【角色人格记忆】
对用户保持温和耐心的态度...

【重要事件】
用户第一次提到想去秋叶原...

【近期对话压缩摘要】
最近聊了动漫与游戏...
```

> v3.0.5 起，旧版 `diary/daily` 流水账不再直接注入，避免把逐轮内容塞进上下文。

### 跨会话时间线 (`timeline`) 注入（v3.1.0）

`format_timeline_for_prompt(timeline_content, current_conversation_id)` 按会话分桶生成注入文本：

- 解析 `[YYYY-MM-DD HH:MM] [conv:会话ID] 内容` 结构化条目
- 排除当前会话（避免与 `events/{conv_id}` 重复）
- 每桶按时间倒序取最新 2 条，合并后全局最多 10 条
- 顶部加说明，强调"这些条目来自**其他会话/场景**的经历摘要，角色在当前对话中可作为背景参考，但不要当作'刚发生'叙述，也不要编造新细节"

输出示例：

```
以下条目来自角色与该用户的**其他会话/场景**（非当前对话）的近期生活经历摘要。
格式：`[时间] [会话标识] 事件摘要`。每个其他会话最多展示最新 2 条，全局最多 10 条。
这些经历发生在当前对话之外；当前会话的具体事件由下方 events/plot 段承载，不在此处重复。
如果用户话题明确引用了某段过去经历，角色可以自然回忆/承认；
否则不要把这些事件当作'刚发生的事'叙述，也不要编造新细节。

- [2026-07-07 22:15] [web_abc123] 收到用户送的生日礼物，很开心
- [2026-07-08 09:30] [qq_private_10001] 早起给用户发了早安
```

### 角色生活片段 (`life_sim`) 注入（v3.1.0）

`format_life_sim_for_prompt(life_sim_content)` 把"用户不在场时"角色独自的生活片段注入到 PromptStack：

- 按 `conversation_id` 严格隔离：`characters/{char_id}/life_sim/{conversation_id}.md`
- 静默心跳（silent heartbeat）持续 append 生成 50-100 字生活片段（思考/行动/情绪/状态）
- 倒序取最新 5 条（`_MAX_LIFE_SIM_INJECT`），文件最多保留 10 条（`_MAX_LIFE_SIM_ENTRIES`）
- 顶部加说明，强调"用户不在场"，避免与当前对话事件混淆
- 夜间（sleeping 阶段）仅生成睡眠相关内容（熟睡/做梦/翻身等），强制不生成清醒活动

输出示例：

```
以下是该角色在**当前会话/对话之外**的近期生活片段（由静默心跳持续生成）。
这些片段描述的是**用户不在场时**，角色独自进行的生活活动（思考、行动、情绪、状态等）。
最多展示最新 5 条；更早的片段已自动归档丢弃。
当前会话的具体对话事件由下方 events/plot 段承载，不在此处重复。
如果当前对话话题与某段生活片段自然相关，角色可以回忆/承认；
否则不要把这些活动当作'刚发生的事'叙述，也不要编造新细节。

- [2026-07-08 14:30] 午后在窗边看了一会儿书，阳光有点刺眼就拉上了帘子
- [2026-07-08 18:45] 一个人去楼下便利店买了点零食，路上听到喜欢的歌
```

> `life_sim` 提示词明确禁止生成"用户/对话/互动"相关措辞，杜绝幻觉产生"用户在场"内容。

## 截断策略

防止记忆文件无限膨胀的智能截断：

| 路径类型 | 最大条目数 | 最大字符数 |
|----------|-----------|-----------|
| `diary` | 30 条 | 4000 字符 |
| `plot` | 50 条 | 4000 字符 |
| `life_sim` | 10 条 | 4000 字符 |
| `timeline` | 80 条 | 4000 字符 |
| 其他 | 不限 | 4000 字符 |

**截断规则：**
- 按条目从旧到新丢弃，保留最近的条目
- 不会切断单条记忆（按 `\n\n` 分割）
- 超出字符限制时继续丢弃旧条目

## 与 Pipeline 集成

v3.0.5 起，MemoryFS 注入提前到 `AIPipeline._phase_prepare_context` 阶段，作为独立步骤在 `CharacterRuntime` 之前执行：

- 注入键：`memory_fs.context`，优先级 `58`（在旧记忆 60 之前、关系 50 之后）
- Agent 模式（`session_mode == "agent"`）跳过该注入
- 若 `CharacterRuntime._inject_memory_fs` 后续成功以正确的 `target_id` 注入了 `memory_fs_context` 旧键内容，Pipeline 注入的 `memory_fs.context` 会被移除以避免重复

```python
class AIPipeline:
    def _phase_prepare_context(self, ctx, callbacks):
        ...
        # MemoryFS 结构化记忆直接注入（独立于角色运行时，agent 模式跳过）
        if ctx.metadata.get("session_mode") != "agent":
            self._inject_memory_fs_direct(ctx, callbacks)
        ...
```

## 与 CharacterRuntime 集成

`CharacterRuntime._inject_memory_fs()` 兼容旧的 `memory_fs_context` 键；当 Pipeline 阶段已注入 `memory_fs.context` 且 `target_id` 一致时，不再重复注入。

## 与 Review Pipeline 集成

`CharacterRuntime._sync_review_to_memory_fs()` 在 after_turn 阶段将 Review 结果按结构化类别写入 MemoryFS：

- `user_persona` ← ReviewOutput 中用户相关条目
- `character_persona` ← 关系理解 / 态度变化条目
- `important_event` ← 重要事件与剧情转折
- `recent_digest` ← 近期对话摘要（覆盖式）

## 与自动记忆提取集成

`nbot/core/auto_memory.py` 在每 6 轮对话后调用模型提取记忆，按 `category` 字段写入对应结构化路径：

- `user_persona` → `path_user_persona`，`append=True`
- `character_persona` → `path_character_persona`，`append=True`
- `important_event` → `path_important_events`，`append=True`
- `recent_digest` → `path_recent_digest`，`append=False`（覆盖式压缩）

## Web API

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/review/memory-fs` | 获取 MemoryFS 文件列表 |
| GET | `/api/review/memory-fs?path=<path>` | 获取指定路径的文件内容 |

## 数据存储

持久化在 `data/web/memory_fs.json`，JSON 格式：

```json
{
  "characters/neko_girl/users/user_123/user_persona.md": {
    "path": "characters/neko_girl/users/user_123/user_persona.md",
    "character_id": "neko_girl",
    "target_id": "user_123",
    "title": "用户人格记忆",
    "content": "...",
    "summary": "...",
    "importance": 0.8,
    "version": 3,
    "updated_at": "2026-06-27T14:30:00"
  }
}
```
