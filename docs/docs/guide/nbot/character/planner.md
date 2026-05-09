# 反应计划生成器 (ReactionPlanner)

ReactionPlanner 根据角色状态、关系、信号和记忆，生成本轮的 ReactionPlan，控制角色的回复策略。

## 概述

第一版使用规则引擎，后续可替换为 LLM 规划。

```python
class ReactionPlanner:
    def plan(
        self,
        profile: CharacterProfile,
        state: CharacterState,
        relationship: RelationshipState,
        memories: List[CharacterMemory],
        signals: Optional[UserSignals],
        user_message: str = "",
    ) -> ReactionPlan
```

## 情绪映射表

信号 → 表面情绪 → 内心情绪 → 语气

```python
_EMOTION_MAP = {
    "praise": {
        "visible": "开心",
        "hidden": "被认可的喜悦",
        "tone": "happy_clingy",
    },
    "rejection": {
        "visible": "委屈",
        "hidden": "害怕被讨厌",
        "tone": "hurt_but_soft",
    },
    "affection": {
        "visible": "害羞",
        "hidden": "心里很开心",
        "tone": "shy_happy",
    },
    "hostility": {
        "visible": "受伤",
        "hidden": "害怕被抛弃",
        "tone": "hurt_scared",
    },
    "care": {
        "visible": "感动",
        "hidden": "被关心的温暖",
        "tone": "touched",
    },
    "intimacy": {
        "visible": "幸福",
        "hidden": "想一直在一起",
        "tone": "blissful",
    },
}
```

## 计划流程

```
plan
├── 找到最强信号类别
├── 信号强度 < 0.3 → 保持自然
├── 根据最强信号设置反应
│   ├── 设置语气
│   ├── 设置表面情绪
│   └── 设置内心情绪
├── 关系状态修正
│   ├── 安全感低 → 负面情绪更强烈
│   └── 熟悉度高 → 反应更随意
├── 计算风格控制
├── 计算状态变化量
└── 计算关系变化量
```

## 关系状态修正

### 安全感低时

```python
if relationship.security < 30 and strongest in ("rejection", "hostility"):
    plan.visible_emotion = "不安"
    plan.hidden_emotion = "害怕被抛弃"
```

### 熟悉度高时

```python
if relationship.familiarity > 70:
    if strongest == "praise":
        plan.visible_emotion = "得意"
        plan.hidden_emotion = "嘿嘿被夸了"
```

## 风格控制

```python
def _compute_style_controls(
    self,
    signal_type: str,
    score: float,
    relationship: RelationshipState,
) -> Dict[str, Any]:
    controls = {
        "length": "medium",        # 回复长度
        "action_detail": "medium", # 动作描写
        "initiative": "medium",    # 主动性
    }

    if signal_type in ("rejection", "hostility"):
        controls["length"] = "short"
        controls["action_detail"] = "low"
        controls["initiative"] = "low"
    elif signal_type in ("praise", "affection", "intimacy"):
        controls["length"] = "medium"
        controls["action_detail"] = "high"
        controls["initiative"] = "medium"

    # 依赖度高时更主动
    if relationship.dependency > 70:
        controls["initiative"] = "high"

    return controls
```

## 状态变化量

```python
def _compute_state_deltas(self, signals: UserSignals) -> Dict[str, Any]:
    deltas = {}

    if signals.praise_score > 0.3:
        deltas["mood_toward"] = "开心"
        deltas["mood_intensity_delta"] = 0.1
    if signals.rejection_score > 0.3:
        deltas["mood_toward"] = "委屈"
        deltas["mood_intensity_delta"] = 0.15
    if signals.hostility_score > 0.3:
        deltas["mood_toward"] = "受伤"
        deltas["mood_intensity_delta"] = 0.2
    if signals.affection_score > 0.3:
        deltas["mood_toward"] = "幸福"
        deltas["mood_intensity_delta"] = 0.1
    if signals.care_score > 0.3:
        deltas["mood_toward"] = "感动"
        deltas["mood_intensity_delta"] = 0.1

    return deltas
```

## 关系变化量

```python
def _compute_relationship_deltas(self, signals: UserSignals) -> Dict[str, Any]:
    deltas = {}

    # 好感变化
    if signals.praise_score > 0.3:
        deltas["affection"] = 2
    if signals.affection_score > 0.3:
        deltas["affection"] = deltas.get("affection", 0) + 2
    if signals.rejection_score > 0.3:
        deltas["affection"] = deltas.get("affection", 0) - 2
    if signals.hostility_score > 0.3:
        deltas["affection"] = deltas.get("affection", 0) - 3

    # 安全感变化
    if signals.rejection_score > 0.3:
        deltas["security"] = -3
    if signals.hostility_score > 0.3:
        deltas["security"] = deltas.get("security", 0) - 4
    if signals.care_score > 0.3:
        deltas["security"] = deltas.get("security", 0) + 2

    # 信任变化
    if signals.care_score > 0.3:
        deltas["trust"] = 1
    if signals.hostility_score > 0.3:
        deltas["trust"] = deltas.get("trust", 0) - 2

    # 熟悉度（每次互动微增）
    deltas["familiarity"] = deltas.get("familiarity", 0) + 1

    # 依赖度
    if signals.care_score > 0.3:
        deltas["dependency"] = 1
    if signals.affection_score > 0.3:
        deltas["dependency"] = deltas.get("dependency", 0) + 1

    return deltas
```

## 使用示例

```python
from nbot.character.planner import ReactionPlanner
from nbot.character.policies import SignalAnalyzer

planner = ReactionPlanner()
analyzer = SignalAnalyzer()

# 分析信号
signals = analyzer.analyze("你真可爱", state, relationship)

# 生成反应计划
plan = planner.plan(
    profile=profile,
    state=state,
    relationship=relationship,
    memories=memories,
    signals=signals,
    user_message="你真可爱",
)

print(plan.visible_emotion)  # 开心
print(plan.hidden_emotion)   # 被认可的喜悦
print(plan.tone)             # happy_clingy
print(plan.style_controls)   # {'length': 'medium', 'action_detail': 'high', ...}
print(plan.state_deltas)     # {'mood_toward': '开心', 'mood_intensity_delta': 0.1}
print(plan.relationship_deltas)  # {'affection': 2, 'familiarity': 1, ...}
```

## Prompt 中的表达

ReactionPlan 注入给模型时不要写成机械 JSON，建议文本：

```
本轮回复策略：
- 角色表面情绪：委屈，但不要崩溃
- 内心倾向：害怕被讨厌，所以会小心试探
- 回复长度：偏短
- 可以有轻微动作描写
- 不要解释规则，不要说自己在扮演角色
```

## 后续改进

- [ ] LLM 驱动的 ReactionPlanner
- [ ] 更复杂的情绪转移路径
- [ ] 角色个性影响反应风格
- [ ] 长期关系历史影响
