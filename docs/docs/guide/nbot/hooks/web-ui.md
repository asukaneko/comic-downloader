# Web 管理界面

Hook 系统提供完整的 Web 管理界面，支持可视化创建、编辑、测试和监控 Hook。

## 访问方式

在 Web 后台左侧导航栏点击 **⚓ Hook 管理** 即可进入 Hook 管理页面。

## 页面布局

### Hook 列表页

- **创建 Hook** 按钮：打开创建模态框
- **刷新** 按钮：重新加载 Hook 列表
- **Hook 卡片网格**：每个 Hook 显示为一张卡片

每张卡片展示：
- Hook 名称
- 监听的事件类型
- 作用域（global / character / conversation / user）
- 触发模式（always / once_per_conversation）
- 启用/禁用状态
- 暂停/启用按钮
- 删除按钮

点击卡片可打开编辑模态框。

## 创建/编辑模态框

模态框包含 5 个区域：

### 1. 模板预设

提供 5 个快速模板，点击即可填充表单：

| 模板名 | 说明 | 事件 | 条件 | 动作 |
|--------|------|------|------|------|
| 高好感度日志（always） | 好感度 ≥ 80 时记录日志 | `character.before_turn.finished` | `affection_gte: 80` | `log` |
| 高好感度日志（once） | 同上，每个会话仅触发一次 | `character.before_turn.finished` | `affection_gte: 80` | `log` |
| 低精力提醒 | 精力 ≤ 30 时记录日志 | `character.before_turn.finished` | `energy_lte: 30` | `log` |
| 关系升温记忆 | 好感度 ≥ 60 且信任 ≥ 50 时写入记忆 | `character.before_turn.finished` | `affection_gte: 60, trust_gte: 50` | `memory_write` |
| 模型调用日志 | 记录每次模型调用 | `model.after_call` | — | `log` |

### 2. 基本信息

| 字段 | 类型 | 说明 |
|------|------|------|
| 名称 | 文本输入 | Hook 名称（必填） |
| 优先级 | 数字输入 | 0-999，数值越小越先执行 |
| 事件 | 下拉选择 | 按分类分组的 27+ 个事件类型 + 通配符 |
| 作用域 | 下拉选择 | `global` / `character` / `conversation` / `user` |
| 角色/会话/用户 ID | 文本输入 | 作用域非 global 时显示对应的 ID 输入框 |
| 触发模式 | 下拉选择 | `always`（每次触发）/ `once_per_conversation`（每会话一次） |
| 描述 | 文本输入 | 可选描述 |
| 启用 | 开关 | 是否启用 |

### 3. 触发条件

JSON 文本编辑区，提供快捷条件标签按钮：

| 标签 | 插入模板 |
|------|---------|
| `channel` | `"channel": ""` |
| `character_id` | `"character_id": ""` |
| `user_id` | `"user_id": ""` |
| `event_source` | `"event_source": ""` |
| `mood_is` | `"mood_is": ""` |
| `mood_is_not` | `"mood_is_not": ""` |
| `affection_gte` | `"affection_gte": 80` |
| `affection_lte` | `"affection_lte": 50` |
| `trust_gte` | `"trust_gte": 60` |
| `trust_lte` | `"trust_lte": 30` |
| `familiarity_gte` | `"familiarity_gte": 50` |
| `energy_gte` | `"energy_gte": 50` |
| `energy_lte` | `"energy_lte": 30` |
| `time_range` | `"time_range": ["HH:MM", "HH:MM"]` |

点击标签会将模板插入到 JSON 编辑区中。

### 4. 执行动作

动态动作列表，支持添加、删除、排序。提供快捷预设按钮：

| 预设 | 插入内容 |
|------|---------|
| 注入提示词 | `{"type": "prompt_inject", "key": "hint", "content": "本轮更主动一点", "priority": 50, "scope": "turn"}` |
| 状态变化 | `{"type": "state_delta", "field": "energy", "delta": -5}` |
| 关系变化 | `{"type": "relationship_delta", "field": "affection", "delta": 1}` |
| 日志 | `{"type": "log", "level": "info", "message": "Hook 触发"}` |
| 消息 | `{"type": "message", "content": ""}` |
| 写入记忆 | `{"type": "memory_write", "title": "", "content": "", "mem_type": "short"}` |
| 自定义 | `{"type": ""}` |

每个动作是一个独立的 JSON 文本框，可以手动编辑完整 JSON。

### 5. 权限设置

JSON 文本编辑区，配置频道白名单/黑名单：

```json
{
  "channels": ["web", "qq"]
}
```

或

```json
{
  "deny_channels": ["telegram"]
}
```

## 实时通知

当 Hook 成功触发时，页面右上角会弹出 Toast 通知，显示：

- 🔗 Hook 名称
- 触发的事件类型
- `display_message`（从 Hook 的第一个 `log` 或 `message` 动作中提取）

通知自动 5 秒后消失，也可手动关闭。

通知通过 Socket.IO 的 `hook_notification` 事件推送。

## Hook 字段完整参考

### ConversationHook 模型

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `id` | `str` | 自动生成 | 唯一标识，格式 `hk_{12位uuid}` |
| `name` | `str` | — | 显示名称（必填） |
| `description` | `str` | `""` | 描述文本 |
| `enabled` | `bool` | `true` | 是否启用 |
| `scope` | `str` | `"global"` | 作用域 |
| `event` | `str` | — | 监听事件（必填，支持通配符） |
| `priority` | `int` | `100` | 执行优先级（越小越先） |
| `conditions` | `dict` | `{}` | 触发条件（AND 逻辑） |
| `actions` | `list[dict]` | `[]` | 执行动作列表 |
| `permissions` | `dict` | `{}` | 频道权限限制 |
| `timeout_ms` | `int` | `3000` | 执行超时（毫秒） |
| `max_retries` | `int` | `0` | 失败重试次数 |
| `trigger_mode` | `str` | `"always"` | 触发模式 |
| `character_id` | `str` | `""` | 绑定角色 ID |
| `conversation_id` | `str` | `""` | 绑定会话 ID |
| `user_id` | `str` | `""` | 绑定用户 ID |
| `created_at` | `str` | 自动生成 | 创建时间（ISO） |
| `updated_at` | `str` | 自动生成 | 更新时间（ISO） |

### 作用域说明

| 作用域 | 说明 | 需要填写 |
|--------|------|---------|
| `global` | 全局生效，所有角色/会话/用户 | — |
| `character` | 仅对指定角色生效 | `character_id` |
| `conversation` | 仅对指定会话生效 | `conversation_id` |
| `user` | 仅对指定用户生效 | `user_id` |

### 触发模式说明

| 模式 | 说明 |
|------|------|
| `always` | 每次条件满足都会触发 |
| `once_per_conversation` | 每个会话最多触发一次，状态持久化到磁盘，重启后仍有效 |
