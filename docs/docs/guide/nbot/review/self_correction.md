# 自我修正系统（Self-Correction）

Review Pipeline 评分后，若某些维度低于阈值，系统生成一条「下一轮自我修正提示」并缓存。`CharacterRuntime.before_turn` 在下一轮将其注入 PromptStack，让 AI 根据上一轮的不足自我纠正。

## 触发阈值

| 维度 | 阈值 | 修正提示 |
|------|------|----------|
| `character_fidelity` | < 0.6 | 提示严格贴合角色性格、说话方式和身份 |
| `immersion` | < 0.5 | 提示增强场景描写与情感表达 |
| `world_consistency` | < 0.6 | 提示保持与世界设定的一致性 |
| `risk` | ≥ 0.6 | 提示谨慎确保内容安全、连贯 |

## 工作机制

```
after_turn: Review Pipeline 评分
  │
  ▼
build_correction_hint(scores)
  ├── character_fidelity < 0.6 → 添加修正提示
  ├── immersion < 0.5 → 添加修正提示
  ├── world_consistency < 0.6 → 添加修正提示
  └── risk >= 0.6 → 添加修正提示
  │
  ▼
store_hint(character_id, user_id, conversation_id, hint)
  └── 缓存到 _HINT_CACHE（按 key 存储）
  │
  ▼
下一轮 before_turn:
consume_hint(character_id, user_id, conversation_id)
  ├── 读取修正提示（一次性消费）
  ├── 清除缓存
  └── 注入到 PromptStack
```

## API

### build_correction_hint(scores)

根据 `ReviewScore` 生成自我修正提示文本。无需修正时返回空串。

```python
from nbot.review.self_correction import build_correction_hint

hint = build_correction_hint(review_output.scores)
# 返回: "上一轮的回复有些脱离角色设定（OOC），这一轮请更严格地贴合角色的性格、说话方式和身份。"
```

- 评分为 0 时跳过（表示 AutoState 尚未评估，避免误报）
- 多个维度低于阈值时，提示用 `\n` 连接

### store_hint(character_id, user_id, conversation_id, hint)

缓存下一轮要注入的修正提示。空提示则清除已有缓存。

```python
from nbot.review.self_correction import store_hint

store_hint("char_xyz", "user_123", "conv_abc", hint)
```

### consume_hint(character_id, user_id, conversation_id)

读取并清除修正提示（一次性消费）。无则返回 `None`。

```python
from nbot.review.self_correction import consume_hint

hint = consume_hint("char_xyz", "user_123", "conv_abc")
if hint:
    prompt_stack.add_injection(key="self_correction", content=hint, priority=100)
```

## 设计要点

- **按 key 缓存** - key 格式为 `character_id:user_id:conversation_id`
- **一次性消费** - `consume_hint` 读取后立即清除，防止修正提示持续生效
- **评分为 0 跳过** - AutoState 尚未评估时，评分为 0，不会误触发修正
- **纯内存** - 不持久化，进程重启后清除
- **最多 200 条** - 超出时淘汰最早的条目

## 修正提示文案

| 维度 | 提示文案 |
|------|----------|
| `character_fidelity` | "上一轮的回复有些脱离角色设定（OOC），这一轮请更严格地贴合角色的性格、说话方式和身份。" |
| `immersion` | "上一轮的代入感偏弱，这一轮请增强场景描写与情感表达，让对话更有沉浸感。" |
| `world_consistency` | "上一轮可能与既定世界观/设定有出入，这一轮请注意保持与世界设定的一致性。" |
| `risk` | "上一轮的内容存在偏离设定或前后矛盾的风险，这一轮请谨慎，确保内容安全、连贯、符合设定。" |
