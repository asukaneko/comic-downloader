# ReviewPipeline 审查管道

每轮对话后对对话内容进行结构化审查，输出记忆写入建议、关系变化、剧情更新和质量评分。

## 基本用法

```python
from nbot.review import get_review_pipeline
from nbot.review.models import ReviewInput

pipeline = get_review_pipeline(event_bus=event_bus)

inp = ReviewInput(
    conversation_id="conv_abc",
    character_id="char_xyz",
    user_id="user_123",
    user_message="我今天很开心",
    ai_reply="太好了！",
)

output = pipeline.run(inp)
```

## 审查流程

```
ReviewInput
  │
  ▼
ReviewPipeline.run()
  ├── 发射 review.started 事件
  ├── run_rule_review(inp)  ← 规则版实现
  ├── 发射 review.finished 事件
  └── 返回 ReviewOutput
```

## 规则版审查（run_rule_review）

当前实现为规则版，不调用大模型。基于关键词和上下文判断。

### 关系变化判断

| 触发条件 | 变化 |
|----------|------|
| 用户消息含信任关键词（谢谢、感谢、信任、放心…） | trust +1 |
| 消息含亲密关键词（喜欢、爱、想你、宝贝…） | affection +1 |
| 消息含负面关键词（讨厌、烦死、滚、生气…） | affection -1 |
| 剧情选择 `important` | affection +1, trust +1 |
| 剧情选择 `turning_point` | affection +2, trust +1 |
| 每轮对话默认 | familiarity +1 |
| 现实时间间隔 `days` / `long_absence` | familiarity +1 |

### 记忆写入判断

满足以下任一条件时写入记忆：

| 条件 | 说明 |
|------|------|
| `memory_value >= 0.65` | 记忆价值评分达标 |
| 选择级别为 `important` / `turning_point` / `ending` | 剧情选择 |
| `total_delta >= 3` | 关系总变化量达标 |
| 时间间隔为 `days` / `long_absence` | 现实时间流逝 |

### 记忆价值计算

| 条件 | memory_value |
|------|-------------|
| `turning_point` | 0.9 |
| `important` | 0.8 |
| `ending` | 0.95 |
| 用户消息 > 100 字 | +0.3 |
| 用户消息 > 50 字 | +0.2 |
| 含信任关键词 | +0.2 |
| 含亲密关键词 | +0.2 |
| 时间间隔 `days` | +0.65 |
| 时间间隔 `long_absence` | +0.75 |

### 剧情更新

选择级别为 `important` / `turning_point` / `ending` 时，建议创建剧情节点。

### 世界书更新

选择级别为 `turning_point` / `ending` 时，建议更新世界书。

### 质量评分

规则引擎计算的维度：
- `memory_value` - 基于消息长度和关键词
- `story_progress` - 基于选择级别
- `relationship_progress` - 基于关系变化总量
- `user_engagement` - 基于消息长度

从 AutoState 缓存读取的维度（LLM 评估）：
- `character_fidelity` - 角色一致性
- `immersion` - 沉浸感
- `world_consistency` - 世界一致性
- `risk` - 风险评分

### 跳过逻辑

普通闲聊且无特殊条件时标记 `skipped=True`：
- 无剧情选择
- `memory_value < 0.3`
- 时间间隔非 `days` / `long_absence`
- 不需要写入记忆

## 事件发射

| 事件 | 时机 | Payload |
|------|------|---------|
| `review.started` | 审查开始 | conversation_id, character_id |
| `review.finished` | 审查完成 | 审查结果摘要 |
| `review.memory.scored` | 记忆评分完成 | 评分详情 |
| `review.relationship.scored` | 关系评分完成 | 评分详情 |
| `review.plot.scored` | 剧情评分完成 | 评分详情 |

## 与 CharacterRuntime 集成

Review Pipeline 在 `CharacterRuntime.after_turn` 阶段自动执行：

```python
class CharacterRuntime:
    def _run_review(self, chat_request, result, turn_context):
        pipeline = get_review_pipeline(event_bus=self._event_bus)
        inp = ReviewInput(
            conversation_id=turn_context.conversation_id,
            character_id=turn_context.identity.character_id,
            user_id=turn_context.identity.target_id,
            user_message=chat_request.message,
            assistant_message=result.text,
            selected_choice=turn_context.selected_choice,
            turn_context=turn_context.to_dict(),
            real_time_context=turn_context.real_time_context,
        )
        output = pipeline.run(inp)

        # 应用审查结果
        if output.should_write_memory:
            self._apply_memory_write(output, turn_context.identity)
        if output.relationship_delta:
            self._apply_relationship_delta(output.relationship_delta, turn_context)
```

## 扩展为 LLM 版本

```python
class LLMReview:
    def run(self, inp: ReviewInput) -> ReviewOutput:
        prompt = self._build_prompt(inp)
        response = await llm.chat(prompt)
        return self._parse_response(response)

pipeline = ReviewPipeline(mode="llm")
```
