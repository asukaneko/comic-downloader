# WorldEngine 群聊环境判定器

规则版上下文判定器，为群聊场景提供智能发言选择和旁白判定。无需调用大模型。

## 获取单例

```python
from nbot.world import get_world_engine

engine = get_world_engine()
```

## decide() - 发言选择

五级优先系统，按优先级顺序尝试，返回第一个匹配结果。

```python
decision = engine.decide(
    message="大家好，今天天气真不错",
    character_ids=["char_a", "char_b", "char_c"],
    recent_messages=recent_messages,
    characters=characters_info,
    relations=relations_data,
    active_plot_node=active_node,
    last_speaker="char_a",
)
```

### 返回值

```python
@dataclass
class WorldEngineDecision:
    speaker_id: str           # 选定的发言角色 ID
    reason: str               # 选择原因描述
    should_narrate_before: bool  # 是否需要发言前旁白
    should_narrate_after: bool   # 是否需要发言后旁白
    narrate_trigger: str      # 旁白触发原因
    confidence: float         # 判断置信度（0-1）
```

### 五级优先判定

#### 1. @提及优先（置信度 0.95）

检查消息中是否明确 @了某个角色。

```python
# "@char_b 你觉得呢？" → speaker_id = "char_b"
```

- 检查 `@{角色名}` 或 `@{角色ID}` 模式
- 优先匹配角色名，其次匹配角色 ID
- 触发 `should_narrate_after`：当活跃剧情节点为 `turning_point` / `ending` 时

#### 2. 剧情关联（置信度 0.85）

检查消息是否与当前激活的剧情节点相关。

```python
# 当前剧情节点参与者: ["char_a", "char_c"]
# "我们继续刚才的话题" → speaker_id = "char_a" 或 "char_c"
```

- 检查剧情节点的 `participants` 字段
- 检查剧情摘要中是否出现角色名
- 剧情转折点/结局时触发发言后旁白

#### 3. 关系权重（置信度 0.7）

根据关系矩阵选择关系权重最高的角色。

```python
# 权重公式: affection + trust * 0.8 + familiarity * 0.5
```

- 排除上一个发言者，避免连续独白
- 排除后无候选时不排除

#### 4. 关键词匹配（置信度 0.75）

检查消息中是否出现角色名关键词。

```python
# "小明你觉得怎么样？" → speaker_id = "char_a"（如果 char_a.name == "小明"）
```

- 优先匹配较长的角色名
- 置信度 0.75

#### 5. 轮换降级（置信度 0.5）

无明确匹配时按顺序轮换。

```python
# 角色列表: ["char_a", "char_b", "char_c"]
# 上一个发言者: "char_a" → speaker_id = "char_b"
```

- 排除上一个发言者
- 按角色列表顺序选择
- 置信度最低（0.5）

## should_narrate() - 旁白判定

判断当前是否需要旁白叙述。

```python
should = engine.should_narrate(
    message="我们换个地方吧",
    recent_messages=recent_messages,
    active_plot_node=active_node,
    turn_count=10,
    narrate_interval=5,
)
```

### 触发条件

| 条件 | 说明 | 示例 |
|------|------|------|
| 剧情转折点 | 活跃剧情节点为转折点/结局 | `active_plot_node.level in ("turning_point", "ending")` |
| 周期触发 | 每隔 N 轮触发一次 | `turn_count % narrate_interval == 0` |
| 场景切换 | 消息包含场景切换关键词 | "换个地方"、"去...吧"、"离开"、"到达" |

### 场景切换关键词

- 换个地方
- 去...吧
- 离开
- 到达
- 来到
- 我们走

### 旁白类型

| 类型 | 时机 | 说明 |
|------|------|------|
| `should_narrate_before` | 发言前 | 场景描述、氛围营造 |
| `should_narrate_after` | 发言后 | 总结、过渡、剧情推进 |

## 与 SpeakerScheduler 集成

WorldEngine 已集成到 `SpeakerScheduler`，作为 `world_engine` 发言策略：

```python
from nbot.group.scheduler import SpeakerScheduler

scheduler = SpeakerScheduler()
speaker_id = scheduler.decide_next_speaker(
    conversation=group,
    message="大家好",
    character_ids=["char_a", "char_b", "char_c"],
    last_speaker="char_a",
    group_context={
        "character_profiles": profiles,
        "active_plot_node": active_node,
        "recent_messages": recent_messages,
    },
)
# 当 speaker_strategy="world_engine" 时，内部调用 WorldEngine.decide()
```

## 扩展为 LLM 版本

```python
class LLMWorldEngine:
    def decide(self, message, character_ids, **kwargs) -> WorldEngineDecision:
        prompt = self._build_prompt(message, character_ids, **kwargs)
        response = await llm.chat(prompt)
        return self._parse_decision(response)

    def should_narrate(self, message, **kwargs) -> bool:
        prompt = self._build_narrate_prompt(message, **kwargs)
        response = await llm.chat(prompt)
        return self._parse_narrate_decision(response)

engine = WorldEngine(llm_engine=LLMWorldEngine())
```
