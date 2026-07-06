# 条件参考

条件系统决定 Hook 是否在事件匹配后实际执行。多个条件之间的逻辑关系由 `condition_logic` 字段控制，默认为 **AND**（全部满足才触发），可切换为 **OR**（任一满足即触发）。

## 条件逻辑字段

在 Hook 顶层可设置 `condition_logic` 字段（`"and"` / `"or"`），控制 `conditions` 中各条件项的组合方式：

```json
{
  "condition_logic": "or",
  "conditions": {
    "mood_is": "happy",
    "affection_gte": 80
  }
}
```

| 值 | 说明 |
|----|------|
| `"and"`（默认） | 所有条件同时满足才触发 |
| `"or"` | 任一条件满足即触发 |

非法值会在 `ConversationHook` 初始化时回退为 `"and"`。

## 条件字段总览

在 Hook 定义的 `conditions` 字段中配置：

```json
{
  "conditions": {
    "mood_is": "happy",
    "affection_gte": 60,
    "channel": "qq",
    "time_range": ["08:00", "22:00"]
  }
}
```

## 身份匹配条件

精确匹配事件中的身份字段。

| 条件键 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `character_id` | `str` | 匹配 `event.character_id` | `"char_xyz"` |
| `user_id` | `str` | 匹配 `event.user_id` | `"user_001"` |
| `channel` | `str` | 匹配频道，从 `event.payload.channel` 或 `event.metadata.channel` 取值 | `"qq"` / `"web"` / `"telegram"` |
| `event_source` | `str` | 匹配 `event.source` | `"ai_pipeline"` |

### 示例

```json
{
  "character_id": "char_my_waifu",
  "channel": "qq"
}
```

此条件表示：仅当角色 ID 为 `char_my_waifu` 且消息来自 QQ 频道时才触发。

## 心情条件

基于角色当前心情状态进行匹配。心情值从上下文的 `mood` 字段获取。

| 条件键 | 类型 | 说明 |
|--------|------|------|
| `mood_is` | `str` | 心情**等于**指定值 |
| `mood_is_not` | `str` | 心情**不等于**指定值 |

### 常见心情值

| 值 | 含义 |
|----|------|
| `happy` | 开心 |
| `sad` | 伤心 |
| `angry` | 生气 |
| `calm` | 平静 |
| `excited` | 兴奋 |
| `anxious` | 焦虑 |
| `neutral` | 中性 |

### 示例

```json
{
  "mood_is": "happy"
}
```

```json
{
  "mood_is_not": "angry"
}
```

## 关系阈值条件

基于角色关系属性进行数值阈值判断。使用 `_gte`（大于等于）和 `_lte`（小于等于）后缀。

### 支持的关系字段

| 字段前缀 | 含义 | 值域 |
|---------|------|------|
| `affection` | 好感度 | 0-100 |
| `trust` | 信任度 | 0-100 |
| `familiarity` | 熟悉度 | 0-100 |
| `dependency` | 依赖度 | 0-100 |
| `security` | 安全感 | 0-100 |
| `jealousy` | 嫉妒度 | 0-100 |

### 条件键格式

| 条件键 | 说明 |
|--------|------|
| `affection_gte` | 好感度 ≥ 指定值 |
| `affection_lte` | 好感度 ≤ 指定值 |
| `trust_gte` | 信任度 ≥ 指定值 |
| `trust_lte` | 信任度 ≤ 指定值 |
| `familiarity_gte` | 熟悉度 ≥ 指定值 |
| `familiarity_lte` | 熟悉度 ≤ 指定值 |
| `dependency_gte` | 依赖度 ≥ 指定值 |
| `dependency_lte` | 依赖度 ≤ 指定值 |
| `security_gte` | 安全感 ≥ 指定值 |
| `security_lte` | 安全感 ≤ 指定值 |
| `jealousy_gte` | 嫉妒度 ≥ 指定值 |
| `jealousy_lte` | 嫉妒度 ≤ 指定值 |

### 示例

```json
{
  "affection_gte": 80,
  "trust_gte": 50
}
```

此条件表示：好感度 ≥ 80 **且** 信任度 ≥ 50 时才触发。

## 精力阈值条件

基于角色精力值进行阈值判断。

| 条件键 | 类型 | 说明 |
|--------|------|------|
| `energy_gte` | `float` | 精力 ≥ 指定值 |
| `energy_lte` | `float` | 精力 ≤ 指定值 |

精力值范围为 0-100。

### 示例

```json
{
  "energy_lte": 30
}
```

此条件表示：精力低于 30% 时触发（适用于疲劳提醒）。

## 时间范围条件

基于当前时间进行匹配，格式为 `["HH:MM", "HH:MM"]`。支持跨午夜。

| 条件键 | 类型 | 说明 |
|--------|------|------|
| `time_range` | `[str, str]` | 时间窗口，24 小时制 |

### 时间匹配规则

- **正常范围**：`["08:00", "22:00"]` → 08:00 到 22:00 之间触发
- **跨午夜**：`["22:00", "06:00"]` → 22:00 到次日 06:00 之间触发
- 使用服务器本地时间

### 示例

```json
{
  "time_range": ["22:00", "06:00"]
}
```

此条件表示：仅在深夜时段（22:00-次日06:00）触发。

## 条件组合示例

> 所有示例默认使用 AND 逻辑（`condition_logic: "and"` 或省略）。如需 OR 逻辑请显式设置 `condition_logic: "or"`。

### 高好感度 + 开心时注入提示词

```json
{
  "conditions": {
    "mood_is": "happy",
    "affection_gte": 70,
    "energy_gte": 50
  }
}
```

### 低精力 + 深夜 + 特定频道

```json
{
  "conditions": {
    "energy_lte": 30,
    "time_range": ["23:00", "07:00"],
    "channel": "qq"
  }
}
```

### 特定角色 + 好感度区间

```json
{
  "conditions": {
    "character_id": "char_xyz",
    "affection_gte": 60,
    "affection_lte": 90
  }
}
```

### OR 逻辑示例

`condition_logic: "or"` 模式下，`conditions` 中任一项满足即触发：

```json
{
  "condition_logic": "or",
  "conditions": {
    "mood_is": "happy",
    "affection_gte": 90
  }
}
```

上述 Hook 表示：角色心情为 `happy` **或** 好感度 ≥ 90 时触发。适合「任意一个强信号就介入」的场景，例如紧急提醒或情绪切换。

## 安全机制

- **未知条件键**：如果条件字典中包含系统不认识的键，默认返回 `False`（拒绝匹配），防止因拼写错误意外触发
- **类型转换**：阈值条件会自动将值转换为 `float` 进行比较，无法转换的值视为 `0.0`
- **空条件**：`conditions` 为空字典 `{}` 或不设置时，视为无条件限制，始终满足
