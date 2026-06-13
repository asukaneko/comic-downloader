# 消息过滤系统

> 自 v2.7.7 起可用

## 概述

消息过滤系统是 NekoBot 内置的内容安全管控组件，支持按频道、会话、全局维度配置关键词或正则表达式，对用户消息和 AI 回复进行过滤。

过滤系统支持两种处理动作：

- **strip（删除）**：仅删除匹配文字，不撤回整条消息
- **recall（撤回）**：整条消息被拦截，不会进入 AI 处理或发送

## 架构

```text
用户消息
    │
    ▼
MessageFilter.match_all()
    │
    ├── 1. 频道级规则（当前频道的通用规则）
    ├── 2. 会话级规则（指定会话的精确规则）
    └── 3. 全局规则（所有频道生效）
    │
    ▼
filter_content() / filter_message()
    │
    ├── recall → 消息被拦截
    └── strip  → 删除匹配文字后继续处理
```

过滤在以下环节触发：

1. **QQ 频道**：消息进入时，对用户输入进行过滤
2. **Web 频道**：用户发送消息时，对输入内容进行过滤
3. **AI 回复**：AI 生成回复后，对输出内容进行过滤
4. **会话存储**：保存历史消息时，对消息内容进行过滤

## 配置方式

### 配置文件位置

过滤规则存储在 `resources/config/message_filter.json`：

```json
{
  "enabled": true,
  "global": [
    {
      "id": "rule_abc12345",
      "pattern": "敏感词",
      "type": "keyword",
      "action": "strip",
      "filter_target": "both",
      "session_scope": "all",
      "session_id": "",
      "enabled": true,
      "created_at": "2026-06-10T10:00:00"
    }
  ],
  "channels": {
    "qq": [
      {
        "id": "rule_def67890",
        "pattern": "群聊违规词",
        "type": "keyword",
        "action": "recall",
        "filter_target": "user",
        "session_scope": "specific",
        "session_id": "qq:group:123456",
        "enabled": true,
        "created_at": "2026-06-10T10:01:00"
      }
    ],
    "web": []
  }
}
```

### 规则字段说明

| 字段 | 类型 | 可选值 | 说明 |
|------|------|--------|------|
| `id` | string | 自动生成 | 规则唯一标识 |
| `pattern` | string | - | 匹配关键词或正则表达式 |
| `type` | string | `keyword` / `regex` | 匹配类型 |
| `action` | string | `strip` / `recall` | 过滤动作 |
| `filter_target` | string | `user` / `ai` / `both` | 过滤目标（见下文） |
| `session_scope` | string | `all` / `specific` | 作用域范围 |
| `session_id` | string | - | 指定会话 ID（`specific` 时必填） |
| `enabled` | bool | `true` / `false` | 是否启用 |

---

## filter_target 字段

`filter_target` 是 v2.7.7 新增的重要字段，决定规则对谁生效：

| 值 | 含义 | 适用场景 |
|----|------|----------|
| `user` | 仅过滤用户发送的消息 | 防止用户发送违规内容 |
| `ai` | 仅过滤 AI 生成的回复 | 防止 AI 输出敏感内容 |
| `both` | 同时过滤用户和 AI 的消息 | 双向管控 |

### 过滤目标工作流程

**对用户消息的过滤（`filter_target: user`）：**

```
用户发送消息
    → 过滤匹配？→ 是 → strip/recall
    → 否 → 进入 AI 处理
```

**对 AI 回复的过滤（`filter_target: ai`）：**

```
AI 生成回复
    → 过滤匹配？→ 是 → strip/recall
    → 否 → 投递到频道
```

**双向过滤（`filter_target: both`）：**

```
用户消息 → 过滤 → AI 处理 → AI 回复 → 过滤 → 投递
```

---

## 匹配类型

### 关键词匹配（keyword）

大小写不敏感的简单子串匹配，性能优秀：

```json
{
  "pattern": "违规词",
  "type": "keyword",
  "action": "strip"
}
```

匹配逻辑：`pattern.lower() in text.lower()`

### 正则匹配（regex）

支持完整 Python 正则语法，更灵活但注意性能：

```json
{
  "pattern": "\\d{17}[\\dXx]",
  "type": "regex",
  "action": "recall"
}
```

安全特性：

- **ReDoS 防护**：正则匹配超时 0.1 秒，超时自动跳过
- **编译缓存**：同一模式只编译一次
- **忽略大小写**：默认 `re.IGNORECASE | re.DOTALL`

---

## 频道支持

### QQ 频道

在 `commands.py` 中，QQ 消息的处理链路：

```
用户 QQ 消息
    → 文本提取 → MessageFilter.match_all(channel="qq")
    → 匹配 recall → 撤回消息，不处理
    → 匹配 strip  → 删除关键词，继续处理
    → 进入 AI 管道
    → AI 回复 → MessageFilter.filter_message() 二次过滤
    → 发送到 QQ
```

支持群聊和私聊，群聊 ID 格式：`qq:group:{group_id}`

### Web 频道

在 `session_store.py` 中，Web 消息的处理链路：

```
Web 用户消息
    → MessageFilter.filter_message() 过滤
    → 匹配 recall → 返回过滤提示
    → 匹配 strip  → 删除关键词后存储
    → 进入 AI 管道
    → AI 回复 → MessageFilter.filter_message() 二次过滤
    → 存储到会话历史
```

在 Web 前端发送消息时，如果消息被拦截，会收到 `message_filtered` 事件通知。

---

## 规则作用域

### 全局规则（global）

对所有频道、所有会话生效：

```json
{
  "session_scope": "all",
  "session_id": ""
}
```

### 频道级规则（channel scope）

对指定频道的所有会话生效（如所有 QQ 群）：

```json
{
  "session_scope": "all",
  "session_id": ""
}
```

此规则配置在 `channels.qq` 列表中。

### 会话级规则（specific scope）

仅对指定的具体会话生效：

```json
{
  "session_scope": "specific",
  "session_id": "qq:group:123456"
}
```

### 匹配优先级

```
会话级规则 > 频道级规则 > 全局规则
```

一条消息可能匹配多条规则，所有匹配规则都会被执行。

---

## 通过 QQ 命令管理

NekoBot 提供了完整的 QQ 命令用于管理过滤规则（需要管理员权限）：

### 添加规则

```
/msg_filter add <关键词> [类型] [动作] [目标]
```

参数：

| 参数 | 可选值 | 默认值 | 说明 |
|------|--------|--------|------|
| 关键词 | - | - | 必填，过滤关键词或正则 |
| 类型 | `keyword` / `regex` | `keyword` | 匹配类型 |
| 动作 | `strip` / `recall` | `strip` | 过滤动作 |
| 目标 | `user` / `ai` / `both` | `user` | 过滤目标 |

示例：

```
/msg_filter add 广告 recall       # 撤回包含"广告"的消息
/msg_filter add \\d{11} regex recall  # 用正则撤回11位数字
/msg_filter add 违规词 strip both   # 双向删除"违规词"
```

群聊中添加规则会自动绑定到当前群：

```
/msg_filter add 群聊禁词 recall
```

### 删除规则

```
/msg_filter del <规则ID>
/msg_filter del <规则ID> -g <群号>
```

示例：

```
/msg_filter del rule_abc12345
```

### 查看规则

```
/msg_filter list
/msg_filter list -g <群号>
```

### 开关过滤器

```
/msg_filter on     # 启用过滤
/msg_filter off    # 禁用过滤
```

---

## 通过 Web API 管理

### 获取全部规则

```
GET /api/message-filter
```

返回：

```json
{
  "enabled": true,
  "rules": {
    "global": [...],
    "channels": { "qq": [...], "web": [...] }
  }
}
```

### 添加规则

```
POST /api/message-filter
Content-Type: application/json

{
  "pattern": "广告",
  "type": "keyword",
  "action": "recall",
  "filter_target": "user",
  "channel": "qq",
  "session_scope": "all",
  "session_id": ""
}
```

### 更新规则

```
PUT /api/message-filter/<rule_id>
Content-Type: application/json

{
  "pattern": "新关键词",
  "action": "strip",
  "enabled": true
}
```

### 删除规则

```
DELETE /api/message-filter/<rule_id>?channel=qq&session_id=
```

### 开关过滤器

```
POST /api/message-filter/toggle
Content-Type: application/json

{ "enabled": false }
```

---

## 技术实现

### 核心类

`nbot/message_filter.py` 中的 `MessageFilter` 类：

| 方法 | 功能 |
|------|------|
| `match(content, channel, session_id)` | 匹配第一条规则 |
| `match_all(content, channel, session_id)` | 匹配所有规则 |
| `filter_content(content, channel, session_id)` | 过滤文本内容 |
| `filter_message(message, channel, session_id)` | 过滤消息对象 |
| `strip_content(content, rules)` | 删除匹配文字 |
| `add_rule(...)` | 添加规则 |
| `remove_rule(...)` | 删除规则 |
| `list_rules(...)` | 列出规则 |
| `set_enabled(enabled)` | 开关过滤器 |

### 存储结构

规则存储路径：`resources/config/message_filter.json`

存储结构：

```json
{
  "enabled": true,
  "global": [{ ...规则... }],
  "channels": {
    "qq": [
      { "session_scope": "all", "session_id": "", ... },
      { "session_scope": "specific", "session_id": "qq:group:123", ... }
    ],
    "web": [...]
  }
}
```

### 自动重载

`MessageFilter` 支持检测配置文件变化后自动重载：

```python
filter.reload_if_needed()
```

每次调用 `match_all()` 时都会检查文件修改时间，无需重启 Bot 即可生效。

### ID 规范化

频道和会话 ID 会自动规范化：

| 原始值 | 规范化后 |
|--------|----------|
| `qq` / `qq_group` / `qq_private` | `qq` |
| `qq_group_123456_user` | `qq:group:123456` |
| `qq_private_789012` | `qq:private:789012` |
| `web:session-uuid` | `web:session-uuid` |

### 正则安全

所有正则匹配在独立线程中执行，超时时间 0.1 秒，防止恶意正则导致服务阻塞（ReDoS 防护）：

```python
future = _regex_pool.submit(compiled.search, text)
result = future.result(timeout=0.1)
```

---

## 最佳实践

### 敏感词过滤

使用关键词类型（keyword）配置需要拦截的敏感词：

```json
{
  "pattern": "敏感词A",
  "type": "keyword",
  "action": "recall",
  "filter_target": "both"
}
```

### AI 回复内容审核

使用 `filter_target: ai` 仅过滤 AI 输出：

```json
{
  "pattern": "违规信息",
  "type": "keyword",
  "action": "strip",
  "filter_target": "ai"
}
```

### 群聊专门规则

为特定群聊设置独立规则：

```json
{
  "pattern": "群禁词",
  "type": "keyword",
  "action": "recall",
  "session_scope": "specific",
  "session_id": "qq:group:123456"
}
```

### 使用正则过滤手机号

```json
{
  "pattern": "1[3-9]\\d{9}",
  "type": "regex",
  "action": "strip",
  "filter_target": "both"
}
```

### 使用正则过滤 URL

```json
{
  "pattern": "https?://[\\w./?=&-]+",
  "type": "regex",
  "action": "strip",
  "filter_target": "ai"
}
```

---

## 性能说明

- **关键词匹配**：O(n) 时间复杂度，n 为规则数量，性能影响可忽略
- **正则匹配**：在独立线程中执行，超时 0.1 秒，建议控制正则规则数量
- **规则缓存**：正则编译结果缓存，同一模式只编译一次
- **文件重载**：只在匹配时检测文件 mtime，无额外开销

建议：日常使用以关键词匹配为主，正则匹配仅在需要时使用。
