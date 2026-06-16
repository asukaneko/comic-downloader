# 事件参考

Hook 系统在 AI Pipeline 的 27 个关键检查点插入事件。每个事件都是一个 `RuntimeEvent` 对象，携带当前对话上下文信息。

## 事件类型一览

### 会话入口

| 事件名 | 触发时机 | 典型 payload |
|--------|----------|-------------|
| `conversation.before_receive` | 消息进入 Pipeline 之前 | `channel`, 原始消息数据 |

### 附件处理

| 事件名 | 触发时机 | 典型 payload |
|--------|----------|-------------|
| `pipeline.before_attachments` | 解析附件（图片/文件）之前 | — |
| `pipeline.after_attachments` | 解析附件之后 | 解析结果 |

### 知识检索

| 事件名 | 触发时机 | 典型 payload |
|--------|----------|-------------|
| `pipeline.before_knowledge` | 知识库检索之前 | — |
| `pipeline.after_knowledge` | 知识库检索之后 | 检索到的知识片段 |

### 角色 before_turn（上下文准备阶段）

| 事件名 | 触发时机 | 典型 payload |
|--------|----------|-------------|
| `character.before_turn.started` | 角色回合开始 | — |
| `character.after_profile_load` | 加载角色档案之后 | 角色 profile 数据 |
| `character.after_memory_retrieve` | 记忆检索之后 | 检索到的记忆列表 |
| `character.after_world_book_match` | 世界书匹配之后 | 匹配到的条目 |
| `character.after_reaction_plan` | 反应规划之后 | 规划结果 |
| `character.before_turn.finished` | 上下文准备完毕，即将渲染 prompt | 完整上下文数据 |

### Prompt 渲染

| 事件名 | 触发时机 | 典型 payload |
|--------|----------|-------------|
| `prompt.before_render` | 渲染 prompt 模板之前 | — |
| `prompt.after_render` | 渲染 prompt 模板之后 | 渲染结果 |

### 模型调用

| 事件名 | 触发时机 | 典型 payload |
|--------|----------|-------------|
| `model.before_call` | 调用 LLM API 之前 | 模型名、token 预估 |
| `model.on_stream_chunk` | 流式响应首块到达 | 首块文本 |
| `model.after_call` | LLM 调用完成 | 响应文本、token 用量 |

### 回复发送

| 事件名 | 触发时机 | 典型 payload |
|--------|----------|-------------|
| `reply.before_send` | 回复发送给用户之前 | 回复内容 |
| `reply.after_send` | 回复发送给用户之后 | 发送结果 |

### 角色 after_turn（状态更新阶段）

| 事件名 | 触发时机 | 典型 payload |
|--------|----------|-------------|
| `character.after_turn.started` | after_turn 阶段开始 | — |
| `character.after_state_update` | 角色状态更新之后 | 状态变更详情 |
| `character.after_turn.finished` | after_turn 阶段结束 | — |

### 记忆

| 事件名 | 触发时机 | 典型 payload |
|--------|----------|-------------|
| `memory.after_extract` | 记忆抽取之后 | 抽取的记忆内容 |

### 状态变化

| 事件名 | 触发时机 | 典型 payload |
|--------|----------|-------------|
| `state.changed` | 角色状态字段发生变化 | 变更的字段和值 |
| `relationship.changed` | 关系字段发生变化 | 变更的字段和值 |

### 工具调用

| 事件名 | 触发时机 | 典型 payload |
|--------|----------|-------------|
| `tool.before_call` | 工具执行之前 | 工具名、参数 |
| `tool.after_call` | 工具执行之后 | 执行结果 |

## 事件别名映射

为兼容文档命名和代码实际 emit 的事件名，系统支持别名映射。两种写法均可在 Hook 的 `event` 字段中使用：

| 文档别名（也可用） | 代码实际事件名 |
|-------------------|--------------|
| `pipeline.before_model_call` | `model.before_call` |
| `pipeline.after_model_call` | `model.after_call` |
| `pipeline.before_reply_send` | `reply.before_send` |
| `pipeline.after_reply_send` | `reply.after_send` |
| `pipeline.before_prompt_render` | `prompt.before_render` |
| `pipeline.after_prompt_render` | `prompt.after_render` |
| `pipeline.stream_chunk` | `model.on_stream_chunk` |
| `character.before_turn.after_memory_retrieve` | `character.after_memory_retrieve` |
| `character.before_turn.after_world_book_match` | `character.after_world_book_match` |
| `character.before_turn.after_reaction_plan` | `character.after_reaction_plan` |
| `character.after_turn.after_state_update` | `character.after_state_update` |

## 通配符匹配

Hook 的 `event` 字段支持通配符模式：

| 模式 | 匹配范围 | 示例 |
|------|---------|------|
| `*` | 所有事件 | 监听全部事件 |
| `character.*` | 所有 character. 开头的事件 | 监听角色生命周期 |
| `pipeline.*` | 所有 pipeline. 开头的事件 | 监听 Pipeline 阶段 |
| `model.*` | 所有 model. 开头的事件 | 监听模型调用 |
| 精确匹配 | 完全匹配单个事件 | `character.before_turn.finished` |

## RuntimeEvent 字段定义

```python
@dataclass
class RuntimeEvent:
    type: str               # 事件类型（必填）
    source: str = ""        # 产生事件的模块标识
    conversation_id: str = ""  # 会话 ID
    character_id: str = ""  # 角色 ID
    user_id: str = ""       # 用户 ID
    group_id: str = ""      # 群聊 ID
    payload: dict = {}      # 事件负载数据
    metadata: dict = {}     # 附加元数据
    id: str = ""            # 自动生成（evt_{uuid}）
    created_at: str = ""    # 自动生成（ISO 时间戳）
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `str` | ✅ | 事件类型，使用点分隔的层级命名 |
| `source` | `str` | — | 模块标识，如 `ai_pipeline`、`character_runtime` |
| `conversation_id` | `str` | — | 当前会话 ID，用于 `once_per_conversation` 触发模式 |
| `character_id` | `str` | — | 当前角色 ID，用于作用域过滤和条件匹配 |
| `user_id` | `str` | — | 当前用户 ID，用于作用域过滤和条件匹配 |
| `group_id` | `str` | — | 群聊 ID（群聊场景） |
| `payload` | `dict` | — | 事件数据，不同事件类型携带不同内容 |
| `metadata` | `dict` | — | 附加元数据，如 `channel` 信息 |
| `id` | `str` | — | 自动生成，格式 `evt_{12位uuid}` |
| `created_at` | `str` | — | 自动生成，UTC ISO 时间戳 |

## Pipeline 事件发射点

事件在 Pipeline 中的实际发射位置：

```
用户消息进入
  │
  ├─ conversation.before_receive        ← ai_pipeline.py
  │
  ├─ pipeline.before_attachments        ← ai_pipeline.py
  ├─ pipeline.after_attachments         ← ai_pipeline.py
  │
  ├─ pipeline.before_knowledge          ← ai_pipeline.py
  ├─ pipeline.after_knowledge           ← ai_pipeline.py
  │
  ├─ CharacterRuntime.before_turn       ← character/runtime.py
  │   ├─ character.before_turn.started
  │   ├─ character.after_profile_load
  │   ├─ character.after_memory_retrieve
  │   ├─ character.after_world_book_match
  │   ├─ character.after_reaction_plan
  │   └─ character.before_turn.finished
  │
  ├─ prompt.before_render               ← ai_pipeline.py
  ├─ prompt.after_render                ← ai_pipeline.py
  │
  ├─ model.before_call                  ← ai_pipeline.py
  ├─ model.on_stream_chunk (首块)        ← ai_pipeline.py
  ├─ model.after_call                   ← ai_pipeline.py
  │
  ├─ reply.before_send                  ← ai_pipeline.py
  ├─ reply.after_send                   ← ai_pipeline.py
  │
  ├─ CharacterRuntime.after_turn        ← character/runtime.py
  │   ├─ character.after_turn.started
  │   ├─ character.after_state_update
  │   └─ character.after_turn.finished
  │
  ├─ memory.after_extract               ← character/runtime.py
  ├─ state.changed                      ← character/runtime.py
  ├─ relationship.changed               ← character/runtime.py
  │
  ├─ tool.before_call                   ← ai_pipeline.py
  └─ tool.after_call                    ← ai_pipeline.py
```
