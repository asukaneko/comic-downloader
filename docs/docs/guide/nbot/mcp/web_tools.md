# Web MCP Tools 参考

## 概述

Web MCP Tools 暴露了 NekoBot Web 后台的核心功能，允许 AI Agent 通过 MCP 协议管理会话、角色卡、世界书、记忆、知识库和 AI 模型。

所有工具返回 JSON 字符串，包含 `ok` 字段表示是否成功。

## 安全流程

每个操作型工具统一走以下流程：

1. **权限检查** — `check_permission` 校验当前 scope
2. **工具启用检查** — `is_tool_enabled` 检查配置中是否启用
3. **高危确认** — 需要 `confirm=true` 才能执行
4. **输入校验** — Pydantic Schema 校验所有参数
5. **执行 + 审计** — 执行操作并记录审计日志

## 数据存储

| 数据 | 文件路径 | 格式 |
|------|----------|------|
| 会话 | `data/sessions.json` | `dict[session_id, session]` |
| 记忆 | `data/memories.json` | `list[memory]` |
| AI 模型 | `data/ai_models.json` | `list[model]` |
| 角色卡 | `data/character/profiles/*.json` | 每个角色一个 JSON 文件 |
| 世界书 | `data/character/world_books/*.json` | 每个世界书一个 JSON 文件 |
| 知识库 | `data/knowledge/documents/*.json` | 每篇文档一个 JSON 文件 |
| Token 用量 | `data/token_stats.json` | `dict[model_name, stats]` |

写入操作使用原子写入（临时文件 + `os.replace`），并持有进程内线程锁保证并发安全。

---

## 会话 Tools

### web_list_sessions

列出所有 Web 会话。

**输入**：无参数

**输出示例**：
```json
{
  "ok": true,
  "count": 3,
  "sessions": [
    {
      "id": "a1b2c3d4-...",
      "name": "测试会话",
      "type": "web",
      "sender_name": "用户",
      "character_id": "char-001",
      "message_count": 12,
      "created_at": "2026-06-01T10:00:00",
      "archived": false,
      "session_mode": "character"
    }
  ]
}
```

### web_get_session

获取会话详情。

**输入**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| session_id | string | 是 | 会话 ID（UUID 格式） |

**输出示例**：
```json
{
  "ok": true,
  "session": {
    "id": "a1b2c3d4-...",
    "name": "测试会话",
    "type": "web",
    "sender_name": "用户",
    "character_id": "char-001",
    "system_prompt": "你是一个助手",
    "scenario": "",
    "message_count": 12,
    "messages": ["...最近20条..."],
    "created_at": "2026-06-01T10:00:00",
    "archived": false,
    "session_mode": "character",
    "tags": []
  }
}
```

### web_create_session

创建新的 Web 会话。

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| name | string | 否 | "" | 会话名称（空则自动生成） |
| session_mode | string | 否 | "character" | 会话模式：`character` / `agent` |
| sender_name | string | 否 | "" | 发送者名称 |
| system_prompt | string | 否 | "" | 系统提示词 |
| first_message | string | 否 | "" | 开场白 |
| character_id | string | 否 | "" | 绑定的角色卡 ID |
| confirm | bool | 否 | false | 高危确认 |

**输出示例**：
```json
{
  "ok": true,
  "session_id": "a1b2c3d4-...",
  "name": "测试会话"
}
```

### web_send_message

向指定会话发送一条用户消息。

::: warning
消息会被追加到会话的消息列表中，但 **不会触发 AI 回复**。需要通过 Web 端触发 AI 生成。
:::

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| session_id | string | 是 | - | 会话 ID |
| content | string | 是 | - | 消息内容 |
| sender | string | 否 | "mcp_user" | 发送者标识 |
| confirm | bool | 否 | false | 高危确认 |

**输出示例**：
```json
{
  "ok": true,
  "message_id": "msg-uuid-...",
  "session_id": "a1b2c3d4-..."
}
```

### web_get_messages

获取会话的消息列表。

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| session_id | string | 是 | - | 会话 ID |
| limit | int | 否 | 50 | 返回数量上限 |

**输出示例**：
```json
{
  "ok": true,
  "count": 10,
  "total": 50,
  "messages": ["...最近N条（排除系统消息）..."]
}
```

### web_delete_session

删除指定会话。**永久删除，不可恢复。**

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| session_id | string | 是 | - | 会话 ID |
| confirm | bool | 否 | false | 高危确认 |

**输出示例**：
```json
{
  "ok": true,
  "session_id": "a1b2c3d4-..."
}
```

---

## 角色卡 Tools

### web_list_characters

列出所有角色卡。

**输入**：无参数

**输出示例**：
```json
{
  "ok": true,
  "count": 2,
  "characters": [
    {
      "id": "char-001",
      "name": "小助手",
      "description": "一个友好的 AI 助手",
      "personality": "温柔、耐心",
      "scenario": "日常对话",
      "tags": ["助手", "日常"],
      "created_at": "2026-06-01T10:00:00"
    }
  ]
}
```

### web_get_character

获取角色卡详情。

**输入**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| character_id | string | 是 | 角色卡 ID |

**输出示例**：
```json
{
  "ok": true,
  "character": {
    "id": "char-001",
    "name": "小助手",
    "description": "...",
    "personality": "...",
    "scenario": "...",
    "system_prompt": "...",
    "first_message": "...",
    "rules": ["保持友好", "不说脏话"],
    "tags": ["助手"],
    "created_at": "...",
    "updated_at": "..."
  }
}
```

### web_create_character

创建新角色卡。

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| name | string | 是 | - | 角色名称 |
| description | string | 否 | "" | 角色描述 |
| personality | string | 否 | "" | 性格特征 |
| scenario | string | 否 | "" | 场景设定 |
| system_prompt | string | 否 | "" | 系统提示词 |
| first_message | string | 否 | "" | 开场白 |
| rules | string | 否 | "" | 规则（逗号分隔） |
| tags | string | 否 | "" | 标签（逗号分隔） |
| confirm | bool | 否 | false | 高危确认 |

**输出示例**：
```json
{
  "ok": true,
  "character_id": "char-uuid-...",
  "name": "小助手"
}
```

### web_update_character

更新角色卡。只更新传入的字段，未传入的字段保持不变。

::: tip 字段更新语义
- 字段值为 `null`（JSON）或不传 → **不更新**
- 字段值为空字符串 `""` 或空列表 `[]` → **清空该字段**
:::

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| character_id | string | 是 | - | 角色卡 ID |
| name | string | 否 | null | 角色名称 |
| description | string | 否 | null | 角色描述 |
| personality | string | 否 | null | 性格特征 |
| scenario | string | 否 | null | 场景设定 |
| system_prompt | string | 否 | null | 系统提示词 |
| first_message | string | 否 | null | 开场白 |
| rules | string | 否 | null | 规则（逗号分隔） |
| tags | string | 否 | null | 标签（逗号分隔） |
| confirm | bool | 否 | false | 高危确认 |

**输出示例**：
```json
{
  "ok": true,
  "character_id": "char-001",
  "name": "新名字"
}
```

### web_delete_character

删除角色卡。**永久删除，不可恢复。**

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| character_id | string | 是 | - | 角色卡 ID |
| confirm | bool | 否 | false | 高危确认 |

**输出示例**：
```json
{
  "ok": true,
  "character_id": "char-001"
}
```

---

## 世界书 Tools

### web_list_world_books

列出所有世界书。

**输入**：无参数

**输出示例**：
```json
{
  "ok": true,
  "count": 1,
  "world_books": [
    {
      "id": "book-001",
      "name": "奇幻世界观",
      "description": "一个剑与魔法的世界",
      "entry_count": 15,
      "character_ids": ["char-001"],
      "enabled": true,
      "created_at": "2026-06-01T10:00:00"
    }
  ]
}
```

### web_get_world_book

获取世界书详情（包含所有条目）。

**输入**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| book_id | string | 是 | 世界书 ID |

**输出示例**：
```json
{
  "ok": true,
  "world_book": {
    "id": "book-001",
    "name": "奇幻世界观",
    "description": "...",
    "character_ids": ["char-001"],
    "entries": [
      {
        "id": "entry-001",
        "name": "王国历史",
        "keywords": ["王国", "历史"],
        "content": "王国建立于...",
        "priority": 50,
        "entry_type": "lore",
        "always_on": false,
        "enabled": true,
        "match_mode": "any"
      }
    ],
    "enabled": true,
    "created_at": "...",
    "updated_at": "..."
  }
}
```

### web_create_world_book

创建新世界书。

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| name | string | 是 | - | 世界书名称 |
| description | string | 否 | "" | 描述 |
| character_ids | string | 否 | "" | 绑定的角色 ID（逗号分隔） |
| confirm | bool | 否 | false | 高危确认 |

**输出示例**：
```json
{
  "ok": true,
  "book_id": "book-uuid-...",
  "name": "奇幻世界观"
}
```

### web_add_world_book_entry

为世界书添加条目。

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| book_id | string | 是 | - | 世界书 ID |
| content | string | 是 | - | 条目内容 |
| name | string | 否 | "" | 条目名称 |
| keywords | string | 否 | "" | 关键词（逗号分隔） |
| priority | int | 否 | 50 | 优先级（数值越小越优先） |
| entry_type | string | 否 | "lore" | 条目类型：`lore` / `location` / `npc` / `item` / `event` / `rule` |
| always_on | bool | 否 | false | 是否始终激活 |
| confirm | bool | 否 | false | 高危确认 |

**输出示例**：
```json
{
  "ok": true,
  "entry_id": "entry-uuid-...",
  "book_id": "book-001"
}
```

### web_delete_world_book

删除世界书。**永久删除，不可恢复。**

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| book_id | string | 是 | - | 世界书 ID |
| confirm | bool | 否 | false | 高危确认 |

**输出示例**：
```json
{
  "ok": true,
  "book_id": "book-001"
}
```

---

## 记忆 Tools

### web_list_memories

列出记忆。可按条件筛选。

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| target_id | string | 否 | "" | 按目标 ID 筛选 |
| character_name | string | 否 | "" | 按角色名筛选 |
| mem_type | string | 否 | "all" | 记忆类型：`all` / `long` / `short` |

**输出示例**：
```json
{
  "ok": true,
  "count": 5,
  "memories": [
    {
      "id": "mem-001",
      "title": "用户喜欢猫",
      "content": "用户在对话中提到喜欢猫",
      "target_id": "session-001",
      "character_name": "小助手",
      "type": "long",
      "expire_days": 30,
      "priority": "normal",
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

### web_add_memory

添加记忆。

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| title | string | 是 | - | 记忆标题 |
| content | string | 是 | - | 记忆内容 |
| target_id | string | 否 | "" | 关联的目标 ID |
| character_name | string | 否 | "" | 关联的角色名 |
| mem_type | string | 否 | "long" | 记忆类型：`long`（长期）/ `short`（短期） |
| expire_days | int | 否 | 7 | 过期天数 |
| confirm | bool | 否 | false | 高危确认 |

**输出示例**：
```json
{
  "ok": true,
  "memory_id": "mem-uuid-..."
}
```

### web_update_memory

更新记忆。只更新传入的字段。

::: tip 字段更新语义
与 `web_update_character` 相同：`null` = 不更新，空字符串 = 清空。
:::

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| memory_id | string | 是 | - | 记忆 ID |
| title | string | 否 | null | 标题 |
| content | string | 否 | null | 内容 |
| mem_type | string | 否 | null | 类型：`long` / `short` |
| target_id | string | 否 | null | 关联目标 ID |
| character_name | string | 否 | null | 关联角色名 |
| confirm | bool | 否 | false | 高危确认 |

**输出示例**：
```json
{
  "ok": true,
  "memory_id": "mem-001"
}
```

### web_delete_memory

删除记忆。**永久删除，不可恢复。**

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| memory_id | string | 是 | - | 记忆 ID |
| confirm | bool | 否 | false | 高危确认 |

**输出示例**：
```json
{
  "ok": true,
  "memory_id": "mem-001"
}
```

---

## 知识库 Tools

### web_list_knowledge

列出知识库文档。

**输入**：无参数

**输出示例**：
```json
{
  "ok": true,
  "count": 3,
  "documents": [
    {
      "id": "doc-001",
      "title": "API 文档",
      "source": "内部 wiki",
      "tags": ["api", "技术"],
      "size": 1234,
      "preview": "这是文档的前200字...",
      "created_at": "2026-06-01T10:00:00"
    }
  ]
}
```

### web_search_knowledge

搜索知识库。基于关键词匹配，返回最相关的结果。

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| query | string | 是 | - | 搜索关键词 |
| top_k | int | 否 | 5 | 返回数量上限 |

**输出示例**：
```json
{
  "ok": true,
  "query": "API",
  "count": 2,
  "results": [
    {
      "doc_id": "doc-001",
      "title": "API 文档",
      "score": 15,
      "preview": "..."
    }
  ]
}
```

### web_add_knowledge

添加知识库文档。

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| title | string | 是 | - | 文档标题 |
| content | string | 是 | - | 文档内容 |
| source | string | 否 | "" | 来源 |
| tags | string | 否 | "" | 标签（逗号分隔） |
| confirm | bool | 否 | false | 高危确认 |

**输出示例**：
```json
{
  "ok": true,
  "doc_id": "doc-uuid-...",
  "title": "API 文档"
}
```

### web_delete_knowledge

删除知识库文档。**永久删除，不可恢复。**

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| doc_id | string | 是 | - | 文档 ID |
| confirm | bool | 否 | false | 高危确认 |

**输出示例**：
```json
{
  "ok": true,
  "doc_id": "doc-001"
}
```

---

## AI 模型 Tools

### web_list_ai_models

列出所有 AI 模型配置。

::: warning
API Key 会被脱敏显示为 `********`。
:::

**输入**：无参数

**输出示例**：
```json
{
  "ok": true,
  "count": 2,
  "models": [
    {
      "id": "model-001",
      "name": "GPT-4o",
      "provider": "openai",
      "model": "gpt-4o",
      "purpose": "chat",
      "enabled": true,
      "base_url": "https://api.openai.com/v1",
      "temperature": 0.7,
      "max_tokens": 2000,
      "priority": 10,
      "input_price": 0.005,
      "output_price": 0.015
    }
  ]
}
```

### web_get_active_models

获取各用途的当前活跃模型。按 `priority`（数值越小优先级越高）排序，每个用途取优先级最高的启用模型。

**输入**：无参数

**输出示例**：
```json
{
  "ok": true,
  "active_models": {
    "chat": {
      "id": "model-001",
      "name": "GPT-4o",
      "model": "gpt-4o",
      "provider": "openai",
      "purpose": "chat",
      "priority": 10
    },
    "vision": {
      "id": "model-002",
      "name": "GPT-4o Vision",
      "model": "gpt-4o",
      "provider": "openai",
      "purpose": "vision",
      "priority": 10
    }
  }
}
```

### web_get_token_usage

获取 Token 用量统计。

**输入**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| model_name | string | 否 | "" | 指定模型名（空则返回所有） |

**输出示例（指定模型）**：
```json
{
  "ok": true,
  "model_name": "gpt-4o",
  "usage": {
    "input_tokens": 100000,
    "output_tokens": 50000,
    "requests": 200
  }
}
```

**输出示例（所有模型）**：
```json
{
  "ok": true,
  "total": {
    "input_tokens": 500000,
    "output_tokens": 200000,
    "total_tokens": 700000,
    "requests": 1000
  },
  "by_model": {
    "gpt-4o": {
      "input_tokens": 100000,
      "output_tokens": 50000,
      "total_tokens": 150000,
      "requests": 200
    }
  }
}
```

---

## 权限模型

Web Tools 遵循与 Gateway Tools 相同的权限体系：

| 等级 | 权限 | 说明 |
|------|------|------|
| 只读 | web.read | 查询会话、角色、记忆、模型等 |
| 操作 | web.write | 创建、更新、删除操作 |
| 超级管理 | admin | 全部能力 |

本地 stdio 模式默认具有所有权限。

## 错误格式

所有工具返回统一的错误格式：

```json
{
  "ok": false,
  "error": {
    "code": "invalid_input",
    "message": "session_id → String should match pattern '^[a-zA-Z0-9_-]{1,128}$'"
  }
}
```

常见错误码：

| 错误码 | 说明 |
|--------|------|
| `permission_denied` | 无权限执行该操作 |
| `tool_disabled` | 工具在配置中被禁用 |
| `confirmation_required` | 需要 `confirm=true` |
| `invalid_input` | 输入参数校验失败 |
| `not_found` | 资源不存在 |
| `save_failed` | 文件保存失败 |
