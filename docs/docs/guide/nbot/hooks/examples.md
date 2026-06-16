# 使用示例

## 基础示例

### 自动情绪联动

当角色心情变为伤心时，自动注入安慰提示词并降低精力：

```json
{
  "name": "伤心时注入安慰提示",
  "event": "character.before_turn.finished",
  "conditions": {"mood_is": "sad"},
  "actions": [
    {"type": "prompt_inject", "key": "comfort", "content": "角色正在伤心，回复应温柔安慰", "priority": 30},
    {"type": "state_delta", "field": "energy", "delta": -5}
  ]
}
```

### 好感度里程碑

当好感度超过 80 时，写入长期记忆并触发世界书更新：

```json
{
  "name": "好感度突破80",
  "event": "relationship.changed",
  "conditions": {"affection_gte": 80},
  "actions": [
    {"type": "memory_write", "content": "好感度达到了80，关系进入亲密阶段", "memory_type": "long"},
    {"type": "world_book_add", "book_id": "wb_lore", "content": "用户与角色关系亲密", "keywords": "亲密,好感"}
  ]
}
```

### 定时晚安

在晚间时段自动注入睡前提示：

```json
{
  "name": "晚间睡前模式",
  "event": "character.before_turn.finished",
  "conditions": {"time_range": ["22:00", "06:00"]},
  "actions": [
    {"type": "prompt_inject", "key": "night_mode", "content": "现在是深夜，角色可能困倦，语气温柔", "priority": 20}
  ]
}
```

## 进阶示例

### 好感度变化自动记录

每当好感度发生变化且达到阈值时，写入短期记忆：

```json
{
  "name": "好感度变化记录",
  "event": "relationship.changed",
  "conditions": {"affection_gte": 50},
  "trigger_mode": "once_per_conversation",
  "actions": [
    {"type": "memory_write", "title": "好感度变化", "content": "用户与角色的好感度达到了较高水平", "mem_type": "short"},
    {"type": "log", "level": "info", "message": "好感度变化已记录"}
  ]
}
```

### 低精力自动休息提醒

精力低于 20 时注入休息提示，并写入记忆：

```json
{
  "name": "低精力休息提醒",
  "event": "character.before_turn.finished",
  "conditions": {"energy_lte": 20},
  "actions": [
    {"type": "prompt_inject", "key": "tired_hint", "content": "角色很疲惫，说话简短，可能想休息", "priority": 10},
    {"type": "memory_write", "title": "疲劳状态", "content": "角色精力很低，需要休息", "mem_type": "short"}
  ]
}
```

### 特定角色专属 Hook

仅对特定角色生效的 Hook：

```json
{
  "name": "角色A专属互动",
  "event": "character.before_turn.finished",
  "scope": "character",
  "character_id": "char_my_waifu",
  "conditions": {"mood_is": "happy", "affection_gte": 70},
  "actions": [
    {"type": "prompt_inject", "key": "special_hint", "content": "角色心情好且好感度高，可以撒娇", "priority": 20}
  ]
}
```

### QQ 频道专属 Hook

仅在 QQ 频道触发的 Hook：

```json
{
  "name": "QQ专属问候",
  "event": "conversation.before_receive",
  "conditions": {"channel": "qq"},
  "actions": [
    {"type": "log", "level": "info", "message": "收到来自QQ的消息"}
  ]
}
```

### 模型调用监控

记录每次模型调用的详细信息：

```json
{
  "name": "模型调用日志",
  "event": "model.after_call",
  "actions": [
    {"type": "log", "level": "info", "message": "模型调用完成"}
  ]
}
```

### 多动作组合

一个 Hook 执行多个动作：

```json
{
  "name": "关系升温综合处理",
  "event": "character.before_turn.finished",
  "conditions": {"affection_gte": 60, "trust_gte": 50, "mood_is": "happy"},
  "actions": [
    {"type": "prompt_inject", "key": "warm_hint", "content": "角色对用户有好感，语气亲密", "priority": 25},
    {"type": "state_delta", "field": "energy", "delta": 3},
    {"type": "relationship_delta", "field": "familiarity", "delta": 1},
    {"type": "memory_write", "title": "愉快互动", "content": "与用户进行了一次愉快的互动", "mem_type": "short"},
    {"type": "log", "level": "info", "message": "关系升温 Hook 已触发"}
  ]
}
```

### 权限限制示例

仅允许特定频道触发：

```json
{
  "name": "Web频道专属",
  "event": "character.before_turn.finished",
  "permissions": {"channels": ["web"]},
  "actions": [
    {"type": "log", "level": "info", "message": "Web频道触发"}
  ]
}
```

禁止特定频道：

```json
{
  "name": "非Telegram专属",
  "event": "character.before_turn.finished",
  "permissions": {"deny_channels": ["telegram"]},
  "actions": [
    {"type": "log", "level": "info", "message": "非Telegram频道触发"}
  ]
}
```

### 通配符监听

监听所有角色相关事件：

```json
{
  "name": "角色事件全监听",
  "event": "character.*",
  "actions": [
    {"type": "log", "level": "debug", "message": "角色事件触发"}
  ]
}
```

监听所有事件（调试用）：

```json
{
  "name": "全事件调试日志",
  "event": "*",
  "priority": 999,
  "actions": [
    {"type": "log", "level": "debug", "message": "事件触发"}
  ]
}
```

## 最佳实践

1. **优先级规划**：数值越小越先执行。建议：
   - 0-20：核心逻辑（状态联动、安全检查）
   - 21-50：业务逻辑（提示词注入、记忆写入）
   - 51-100：通用逻辑（日志记录、统计）
   - 100+：调试用途

2. **触发模式选择**：
   - `always`：适用于需要每次触发的场景（日志、状态联动）
   - `once_per_conversation`：适用于里程碑事件（首次好感度达标、首次互动记录）

3. **超时设置**：
   - 默认 3000ms 足够大多数场景
   - 如果动作包含工作流触发等耗时操作，适当增大

4. **条件精简**：
   - 只在 `conditions` 中设置必要条件，避免过度限制
   - 利用 `scope` 过滤比在 `conditions` 中用 `character_id` 更高效

5. **安全限制**：
   - 系统每轮最多触发 20 个 Hook
   - 事件链最大深度 5 层（防止 Hook 触发事件再触发 Hook 的无限循环）
   - 每个 Hook 每轮最多触发一次（去重）
