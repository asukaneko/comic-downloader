# 动作参考

Hook 触发后执行的动作列表。每个 Hook 可定义多个动作，按数组顺序依次执行。

## 动作通用结构

每个动作是一个 JSON 对象，必须包含 `type` 字段：

```json
{
  "type": "动作类型",
  ...其他参数
}
```

## 内置动作类型

### 1. prompt_inject — 注入提示词

向 PromptStack 注入额外提示词，影响当前回合的 AI 回复。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `type` | `str` | ✅ | — | 固定为 `"prompt_inject"` |
| `key` | `str` | — | `"hook_{event_id前8位}"` | 注入的唯一标识 key |
| `content` | `str` | ✅ | — | 要注入的提示词文本 |
| `priority` | `int` | — | `55` | 优先级，数值越小优先级越高 |
| `scope` | `str` | — | `"turn"` | 生命周期：`"turn"` 表示仅当前回合 |

```json
{
  "type": "prompt_inject",
  "key": "mood_hint",
  "content": "角色心情很好，倾向于撒娇和主动",
  "priority": 30,
  "scope": "turn"
}
```

### 2. state_delta — 修改角色状态

修改角色的状态字段（精力、心情等）。支持两种参数格式。

**格式一（推荐）：** 使用 `field` + `delta`

```json
{
  "type": "state_delta",
  "field": "energy",
  "delta": -5
}
```

**格式二：** 使用 `payload` 字典（可同时修改多个字段）

```json
{
  "type": "state_delta",
  "payload": {
    "energy": -5,
    "mood": "happy"
  }
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `str` | ✅ | 固定为 `"state_delta"` |
| `field` | `str` | 格式一必填 | 状态字段名 |
| `delta` | `number` | 格式一必填 | 变化量（正数增加，负数减少） |
| `payload` | `dict` | 格式二必填 | `{字段名: 变化量}` 字典 |

**字段处理规则：**

| 字段 | 处理方式 | 范围限制 |
|------|---------|---------|
| `mood` | 直接替换为字符串值 | — |
| `mood_intensity` | 加法叠加 | 限值 0.0 ~ 1.0 |
| `energy` | 加法叠加 | 限值 0 ~ 100 |
| 其他字段 | 直接 `setattr` 赋值 | — |

### 3. relationship_delta — 修改关系属性

修改角色与用户的关系属性。参数格式与 `state_delta` 相同。

**格式一：**

```json
{
  "type": "relationship_delta",
  "field": "affection",
  "delta": 2
}
```

**格式二：**

```json
{
  "type": "relationship_delta",
  "payload": {
    "affection": 2,
    "trust": 1
  }
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `str` | ✅ | 固定为 `"relationship_delta"` |
| `field` | `str` | 格式一必填 | 关系字段名 |
| `delta` | `number` | 格式一必填 | 变化量 |
| `payload` | `dict` | 格式二必填 | `{字段名: 变化量}` 字典 |

**合法字段名：**

| 字段 | 含义 |
|------|------|
| `affection` | 好感度 |
| `trust` | 信任度 |
| `familiarity` | 熟悉度 |
| `dependency` | 依赖度 |
| `security` | 安全感 |
| `jealousy` | 嫉妒度 |

所有关系字段自动限值 0 ~ 100。

### 4. memory_write — 写入记忆

向角色记忆系统写入一条记忆。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `type` | `str` | ✅ | — | 固定为 `"memory_write"` |
| `title` | `str` | — | `""` | 记忆标题 |
| `content` | `str` | ✅ | — | 记忆内容 |
| `mem_type` | `str` | — | `"long"` | 记忆类型：`"long"` 或 `"short"` |

> 兼容：`memory_type` 字段名等效于 `mem_type`。

```json
{
  "type": "memory_write",
  "title": "好感度里程碑",
  "content": "好感度达到了80，关系进入亲密阶段",
  "mem_type": "long"
}
```

### 5. log — 写入日志

向应用日志输出一条消息。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `type` | `str` | ✅ | — | 固定为 `"log"` |
| `level` | `str` | — | `"info"` | 日志级别：`debug` / `info` / `warning` / `error` |
| `message` | `str` | ✅ | — | 日志消息 |

```json
{
  "type": "log",
  "level": "info",
  "message": "好感度变化触发 Hook"
}
```

### 6. message — 追加消息

向当前对话上下文追加一条消息。消息会加入 `ctx["hook_messages"]` 列表。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `str` | ✅ | 固定为 `"message"` |
| `content` | `str` | ✅ | 消息内容 |

```json
{
  "type": "message",
  "content": "触发了特殊事件"
}
```

### 7. workflow — 触发工作流

异步触发一个工作流执行。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `str` | ✅ | 固定为 `"workflow"` |
| `workflow` | `str` | ✅ | 工作流名称 |

> 兼容：`workflow_id` 字段名等效于 `workflow`。

```json
{
  "type": "workflow",
  "workflow": "wf_goodnight_event"
}
```

### 8. world_book_add — 添加世界书条目

向指定世界书添加一个新条目。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `type` | `str` | ✅ | — | 固定为 `"world_book_add"` |
| `book_id` | `str` | ✅ | — | 目标世界书 ID |
| `content` | `str` | ✅ | — | 条目内容 |
| `name` | `str` | — | `""` | 条目名称 |
| `keywords` | `list[str]` | — | `[]` | 触发关键词列表 |
| `entry_type` | `str` | — | `"event"` | 条目类型 |
| `priority` | `int` | — | `50` | 优先级 |
| `always_on` | `bool` | — | `false` | 是否始终激活 |
| `tags` | `list[str]` | — | `[]` | 标签列表 |

```json
{
  "type": "world_book_add",
  "book_id": "wb_lore_book",
  "name": "关系里程碑",
  "content": "用户与角色关系进入亲密阶段",
  "keywords": ["亲密", "好感"],
  "entry_type": "event",
  "priority": 80
}
```

## 执行结果状态

每个动作执行后返回 `ActionResult`：

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | `bool` | 是否执行成功 |
| `action_type` | `str` | 动作类型 |
| `detail` | `str` | 执行详情或错误信息 |
| `output` | `Any` | 输出数据（可选） |

## 执行日志状态

Hook 整体执行后记录的状态：

| 状态 | 含义 |
|------|------|
| `success` | 所有动作执行成功 |
| `partial` | 部分动作执行失败 |
| `failed` | 执行异常 |
| `timeout` | 执行超时（超过 `timeout_ms`） |
| `skipped` | 被跳过 |
| `denied` | 权限不足 |

## 扩展自定义动作

通过 `ActionExecutor.register()` 注册自定义动作类型：

```python
from nbot.hooks.actions import ActionExecutor

async def my_notification(action, event, ctx):
    """发送自定义通知"""
    target = action.get("target", "")
    content = action.get("content", "")
    # 实现通知逻辑...
    return ActionResult(success=True, action_type="notification", detail="sent")

ActionExecutor.register("notification", my_notification)
```

注册后即可在 Hook 的 `actions` 中使用：

```json
{
  "type": "notification",
  "target": "admin",
  "content": "高好感度触发提醒"
}
```
