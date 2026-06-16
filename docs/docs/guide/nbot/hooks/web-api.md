# Web API 参考

Hook 系统通过 Web 后台提供完整的 RESTful 管理接口。

## API 端点总览

| 方法 | 路由 | 说明 |
|------|------|------|
| `GET` | `/api/hooks` | 列出所有 Hook |
| `POST` | `/api/hooks` | 创建 Hook |
| `GET` | `/api/hooks/<hook_id>` | 获取单个 Hook |
| `PUT` | `/api/hooks/<hook_id>` | 更新 Hook |
| `DELETE` | `/api/hooks/<hook_id>` | 删除 Hook |
| `POST` | `/api/hooks/<hook_id>/toggle` | 启用/禁用 Hook |
| `POST` | `/api/hooks/test` | 发送模拟事件测试 |
| `GET` | `/api/hooks/logs` | 查询执行日志 |
| `GET` | `/api/hooks/events` | 查询事件历史 |
| `GET` | `/api/hooks/stats` | 查询统计信息 |

---

## 列出 Hook

```
GET /api/hooks
```

### 查询参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `scope` | `str` | — | 按作用域过滤：`global` / `character` / `conversation` / `user` |
| `event` | `str` | — | 按事件类型过滤（支持通配符） |
| `enabled` | `str` | — | 设为 `"true"` 仅返回已启用的 Hook |

### 响应

```json
{
  "hooks": [
    {
      "id": "hk_abc123def456",
      "name": "高好感度提醒",
      "description": "",
      "enabled": true,
      "scope": "global",
      "event": "character.before_turn.finished",
      "priority": 100,
      "conditions": {"affection_gte": 80},
      "actions": [
        {"type": "log", "level": "info", "message": "好感度达到80"}
      ],
      "permissions": {},
      "timeout_ms": 3000,
      "max_retries": 0,
      "trigger_mode": "always",
      "character_id": "",
      "conversation_id": "",
      "user_id": "",
      "created_at": "2026-06-15T10:00:00+00:00",
      "updated_at": "2026-06-15T10:00:00+00:00"
    }
  ],
  "total": 1
}
```

---

## 创建 Hook

```
POST /api/hooks
```

### 请求体

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | `str` | ✅ | — | Hook 名称 |
| `event` | `str` | ✅ | — | 监听的事件类型 |
| `description` | `str` | — | `""` | 描述 |
| `enabled` | `bool` | — | `true` | 是否启用 |
| `scope` | `str` | — | `"global"` | 作用域 |
| `priority` | `int` | — | `100` | 优先级（越小越先执行） |
| `conditions` | `dict` | — | `{}` | 触发条件 |
| `actions` | `list` | — | `[]` | 执行动作列表 |
| `permissions` | `dict` | — | `{}` | 权限限制 |
| `timeout_ms` | `int` | — | `3000` | 超时时间（毫秒） |
| `max_retries` | `int` | — | `0` | 失败重试次数 |
| `trigger_mode` | `str` | — | `"always"` | 触发模式 |
| `character_id` | `str` | — | `""` | 绑定角色 ID（scope=character 时） |
| `conversation_id` | `str` | — | `""` | 绑定会话 ID（scope=conversation 时） |
| `user_id` | `str` | — | `""` | 绑定用户 ID（scope=user 时） |

### 请求示例

```json
{
  "name": "高好感度日志",
  "event": "character.before_turn.finished",
  "conditions": {"affection_gte": 80},
  "actions": [
    {"type": "log", "level": "info", "message": "好感度达到80"}
  ],
  "trigger_mode": "once_per_conversation"
}
```

### 响应

```json
{
  "hook": {
    "id": "hk_abc123def456",
    "name": "高好感度日志",
    ...
  }
}
```

状态码：`201 Created`

---

## 获取单个 Hook

```
GET /api/hooks/<hook_id>
```

### 响应

```json
{
  "hook": { ... }
}
```

未找到时返回 `404`。

---

## 更新 Hook

```
PUT /api/hooks/<hook_id>
```

### 请求体

仅传入需要更新的字段，未传入的字段保持不变：

```json
{
  "enabled": false,
  "conditions": {"affection_gte": 90}
}
```

### 可更新字段

`name`、`description`、`enabled`、`scope`、`event`、`priority`、`conditions`、`actions`、`permissions`、`timeout_ms`、`max_retries`、`trigger_mode`、`character_id`、`conversation_id`、`user_id`

### 响应

```json
{
  "hook": { ... }
}
```

---

## 删除 Hook

```
DELETE /api/hooks/<hook_id>
```

### 响应

```json
{
  "success": true
}
```

未找到时返回 `404`。

---

## 启用/禁用 Hook

```
POST /api/hooks/<hook_id>/toggle
```

### 请求体（可选）

```json
{
  "enabled": true
}
```

不传 `enabled` 字段时，自动切换为当前状态的反面。

### 响应

```json
{
  "hook": { ... }
}
```

---

## 测试 Hook 触发

发送一个模拟事件，测试哪些 Hook 会被触发。

```
POST /api/hooks/test
```

### 请求体

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `event_type` | `str` | — | 事件类型（默认 `"test.ping"`） |
| `payload` | `dict` | — | 事件 payload |
| `context` | `dict` | — | 额外上下文（如 mood、affection 等） |
| `conversation_id` | `str` | — | 模拟的会话 ID |
| `character_id` | `str` | — | 模拟的角色 ID |
| `user_id` | `str` | — | 模拟的用户 ID |

### 请求示例

```json
{
  "event_type": "character.before_turn.finished",
  "character_id": "char_xyz",
  "context": {
    "mood": "happy",
    "affection": 85,
    "energy": 90
  }
}
```

### 响应

```json
{
  "event": {
    "id": "evt_test123",
    "type": "character.before_turn.finished",
    ...
  },
  "hooks_triggered": 2,
  "logs": [
    {
      "id": "log_abc123",
      "hook_id": "hk_xyz",
      "event_id": "evt_test123",
      "status": "success",
      "actions_executed": 1,
      "error": "",
      "duration_ms": 5,
      ...
    }
  ]
}
```

---

## 查询执行日志

```
GET /api/hooks/logs
```

### 查询参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `hook_id` | `str` | — | 按 Hook ID 过滤 |
| `limit` | `int` | — | 返回条数（默认 50） |

### 响应

```json
{
  "logs": [
    {
      "id": "log_abc123",
      "hook_id": "hk_xyz",
      "event_id": "evt_test123",
      "status": "success",
      "actions_executed": 2,
      "error": "",
      "duration_ms": 12,
      "conversation_id": "conv_001",
      "event_type": "character.before_turn.finished",
      "created_at": "2026-06-15T10:30:00+00:00"
    }
  ],
  "total": 1
}
```

---

## 查询事件历史

```
GET /api/hooks/events
```

### 查询参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `event_type` | `str` | — | 按事件类型过滤 |
| `limit` | `int` | — | 返回条数（默认 50） |

### 响应

```json
{
  "events": [
    {
      "id": "evt_abc123",
      "type": "character.before_turn.finished",
      "source": "character_runtime",
      "conversation_id": "conv_001",
      "character_id": "char_xyz",
      "user_id": "user_001",
      "payload": { ... },
      "metadata": { ... },
      "created_at": "2026-06-15T10:30:00+00:00"
    }
  ],
  "total": 1
}
```

---

## 查询统计信息

```
GET /api/hooks/stats
```

### 响应

```json
{
  "total_hooks": 5,
  "enabled_hooks": 3,
  "total_executions": 127,
  "turn_hooks_executed": 0,
  "event_bus": {
    "patterns_registered": 3,
    "total_subscribers": 5,
    "total_published": 1200,
    "total_delivered": 1150,
    "history_size": 200,
    "history_max": 200,
    "patterns": ["character.*", "model.*", "state.changed"]
  }
}
```
