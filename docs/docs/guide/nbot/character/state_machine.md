# 状态机 (StateMachine)

StateMachine 负责根据信号和反应计划更新角色状态和关系状态。

## 核心原则

1. **情绪惯性**: 情绪不会一句话突变
2. **数值边界**: 所有关系值在 0-100 范围内
3. **每轮变化限幅**: 避免暴涨暴跌

## 情绪惯性

```python
# 情绪惯性系数：旧情绪权重 0.75，新信号权重 0.25
_MOOD_INERTIA = 0.75

# 情绪强度更新
new_intensity = (
    old_state.mood_intensity * _MOOD_INERTIA
    + (old_state.mood_intensity + intensity_delta) * (1 - _MOOD_INERTIA)
)
```

情绪不要一句话突变，推荐状态变化路径：

```
开心 → 疑惑 → 委屈 → 生气 / 沉默
平静 → 被关心 → 放松 → 黏人
不安 → 被安慰 → 缓和 → 依赖
```

## 每轮变化限幅

```python
_MAX_DELTA_PER_TURN = {
    "affection": 3,    # 好感
    "trust": 3,        # 信任
    "familiarity": 2,  # 熟悉
    "dependency": 2,   # 依赖
    "security": 4,     # 安全感
    "jealousy": 2,     # 嫉妒
}
```

## 情绪转移表

```python
_MOOD_TRANSITIONS = {
    "开心": ["放松", "得意", "黏人"],
    "委屈": ["不安", "沉默", "伤心"],
    "害羞": ["开心", "放松"],
    "受伤": ["不安", "沉默", "委屈"],
    "感动": ["幸福", "依赖"],
    "幸福": ["黏人", "放松"],
    "不安": ["害怕", "试探"],
    "平静": ["放松", "期待"],
    "生气": ["沉默", "委屈"],
}
```

## apply 方法

```python
def apply(
    self,
    old_state: CharacterState,
    old_relationship: RelationshipState,
    signals: Optional[UserSignals],
    plan: ReactionPlan,
    user_message: str = "",
    assistant_message: str = "",
) -> Tuple[CharacterState, RelationshipState]:
    """
    应用状态变化

    Returns:
        (new_state, new_relationship) 元组
    """
```

## 更新角色状态

```python
def _apply_state(
    self,
    old_state: CharacterState,
    plan: ReactionPlan,
) -> CharacterState:
    new_state = CharacterState(
        character_id=old_state.character_id,
        scope_id=old_state.scope_id,
        mood=old_state.mood,
        mood_intensity=old_state.mood_intensity,
        energy=old_state.energy,
        scene=dict(old_state.scene),
        last_active_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )

    # 情绪更新
    deltas = plan.state_deltas
    if deltas:
        target_mood = deltas.get("mood_toward", old_state.mood)
        intensity_delta = deltas.get("mood_intensity_delta", 0.0)

        if target_mood != old_state.mood:
            # 情绪转移
            new_state.mood = target_mood

        # 情绪强度：惯性混合
        new_intensity = (
            old_state.mood_intensity * _MOOD_INERTIA
            + (old_state.mood_intensity + intensity_delta) * (1 - _MOOD_INERTIA)
        )
        new_state.mood_intensity = max(0.0, min(1.0, new_intensity))

    # 精力微减（每轮 -1）
    new_state.energy = max(0, old_state.energy - 1)

    return new_state
```

## 更新关系状态

```python
def _apply_relationship(
    self,
    old_rel: RelationshipState,
    plan: ReactionPlan,
) -> RelationshipState:
    new_rel = RelationshipState(
        character_id=old_rel.character_id,
        target_id=old_rel.target_id,
        affection=old_rel.affection,
        trust=old_rel.trust,
        familiarity=old_rel.familiarity,
        dependency=old_rel.dependency,
        security=old_rel.security,
        jealousy=old_rel.jealousy,
        updated_at=datetime.now().isoformat(),
    )

    # 应用关系变化量
    deltas = plan.relationship_deltas
    if not deltas:
        return new_rel

    for field_name, delta in deltas.items():
        if field_name not in _MAX_DELTA_PER_TURN:
            continue

        max_delta = _MAX_DELTA_PER_TURN[field_name]
        # 限幅
        clamped_delta = max(-max_delta, min(max_delta, delta))

        old_value = getattr(new_rel, field_name, 50)
        new_value = old_value + clamped_delta
        # 边界约束 0-100
        new_value = max(0, min(100, new_value))
        setattr(new_rel, field_name, new_value)

    return new_rel
```

## 使用示例

```python
from nbot.character.state_machine import StateMachine

state_machine = StateMachine()

# 应用状态变化
new_state, new_relationship = state_machine.apply(
    old_state=turn_context.state,
    old_relationship=turn_context.relationship,
    signals=turn_context.signals,
    plan=turn_context.plan,
    user_message="你真可爱",
    assistant_message="谢谢！",
)

print(new_state.mood)              # 更新后的心情
print(new_state.mood_intensity)    # 更新后的情绪强度
print(new_relationship.affection)  # 更新后的好感度
```

## 数值边界

所有关系数值限定在 0-100：

```python
# 边界约束
new_value = max(0, min(100, new_value))
```

## 每轮变化建议

```
普通消息：      -1 ~ +1
明显情绪消息：  -3 ~ +3
重大事件：      -8 ~ +8
```

避免一轮暴涨暴跌。

## 调试输出

```python
{
  "state_before": {"mood": "平静", "mood_intensity": 0.5},
  "state_after": {"mood": "开心", "mood_intensity": 0.55},
  "relationship_before": {"affection": 50, "trust": 50},
  "relationship_after": {"affection": 52, "trust": 50}
}
```
