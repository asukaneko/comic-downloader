# 现实时间连续性（Time Context）

计算现实世界中两次对话之间的时间间隔，生成角色扮演提示，让角色能自然地体现时间流逝。

## 连续性等级

| 等级 | 时间范围 | 角色扮演提示 |
|------|----------|-------------|
| `first_contact` | 首次记录 | "这是第一次可用的现实时间记录；不要假装已经知道之前离线时发生的事。" |
| `continuous` | < 30 分钟 | "现实中几乎没有间隔；把这轮当作连续对话自然承接。" |
| `short_gap` | < 6 小时 | "现实中已经过去X小时；可轻微承认时间流逝，但不要夸大成久别。" |
| `same_day_gap` | < 24 小时 | "现实中已经过去X小时；角色可以像在同一天稍后再次见面一样回应。" |
| `days` | < 7 天 | "现实中已经过去X天；角色应意识到隔了几天，可体现等待、生活延续或重新见面的感觉。" |
| `long_absence` | ≥ 7 天 | "现实中已经过去X天；角色应把这当作较长分别后的再次互动，但不要编造未经确认的具体经历。" |

## API

### build_real_time_context()

从时间戳构建时间上下文。

```python
from nbot.review.time_context import build_real_time_context

ctx = build_real_time_context(
    previous_turn_time="2026-06-20T10:00:00+08:00",
    current_time="2026-06-22T14:30:00+08:00",
)
```

返回字典：

```python
{
    "current_time": "2026-06-22T14:30:00+08:00",
    "previous_turn_time": "2026-06-20T10:00:00+08:00",
    "elapsed_seconds": 188600,
    "elapsed_label": "2天4小时",
    "continuity_level": "days",
    "roleplay_hint": "现实中已经过去2天4小时；角色应意识到隔了几天...",
}
```

### build_current_real_time_context()

使用当前时间构建时间上下文。

```python
from nbot.review.time_context import build_current_real_time_context

ctx = build_current_real_time_context(previous_turn_time="2026-06-20T10:00:00+08:00")
```

### format_real_time_prompt_context()

将时间上下文格式化为可注入 Prompt 的文本。

```python
from nbot.review.time_context import format_real_time_prompt_context

text = format_real_time_prompt_context(ctx)
```

输出格式：

```
## real_time.continuity
当前现实时间: 2026-06-22T14:30:00+08:00
上次互动时间: 2026-06-20T10:00:00+08:00
现实时间间隔: 2天4小时
连续性等级: days
角色扮演提示: 现实中已经过去2天4小时；角色应意识到隔了几天，可体现等待、生活延续或重新见面的感觉。
把现实时间流逝当作角色生活连续性的一部分；可以体现等待、日常延续、重新见面的感觉。
不要编造未经用户确认的具体离线经历、事件或承诺。
```

## 时间间隔标签

`_elapsed_label(seconds)` 生成人类可读的时间间隔：

| 秒数 | 标签 |
|------|------|
| ≤ 0 | "刚刚" |
| < 60 | "刚刚" |
| < 3600 | "X分钟" |
| < 86400 | "X小时" |
| ≥ 86400 | "X天" 或 "X天Y小时" |

## 与 CharacterRuntime 集成

`CharacterRuntime.before_turn` 在每轮开始时调用 `build_current_real_time_context()`，将结果存入 `turn_context.real_time_context`。Review Pipeline 和 Self-Correction 系统都会读取这个上下文。

## 与 Review Pipeline 集成

Review Pipeline 使用时间上下文：
- `days` / `long_absence` 时额外增加 `familiarity_delta +1`
- `days` / `long_absence` 时 `memory_value` 额外 +0.65 / +0.75
- 时间间隔信息写入记忆内容
