# SpeakerScheduler 发言调度器

决定群聊中下一个发言的角色。通过 `SpeakerScheduler.instance()` 获取全局单例。

## 基本用法

```python
from nbot.group.scheduler import SpeakerScheduler

scheduler = SpeakerScheduler.instance()
next_speaker = scheduler.decide_next_speaker(
    conversation=group,
    message=user_message,
    character_ids=["char_a", "char_b", "char_c"],
    last_speaker="char_a",
    group_context=group_context,
)
```

## 六种发言策略

### round_robin - 轮询

按角色列表顺序循环发言。

```python
config = GroupConfig(speaker_strategy="round_robin", round_robin_mode="async")
```

- 排除上一个发言者，选择列表中的下一个
- `round_robin_mode="async"` 时异步并行回复
- `round_robin_mode="sequential"` 时顺序回复

### mention - @提及（默认）

仅在被 @提及时发言。

```python
config = GroupConfig(speaker_strategy="mention")
```

- 检测 `@角色ID` 或 `@角色名` 模式
- 大小写不敏感
- 无明确 @ 时返回第一个角色

### random - 随机

随机选择发言者。

```python
config = GroupConfig(speaker_strategy="random")
```

### relevance - 相关性

根据消息与角色的相关性选择。

```python
config = GroupConfig(speaker_strategy="relevance")
```

评分规则：
- 关键词匹配：消息中出现角色 ID/名称，每次 +10 分
- 关系加成：affection × 0.05 + familiarity × 0.03
- 选择得分最高的角色

### narrator_driven - 旁白驱动

由旁白角色优先发言。

```python
config = GroupConfig(speaker_strategy="narrator_driven")
```

- 优先返回 `narrator_id`
- 旁白不在角色列表中时，返回第一个非旁白角色

### world_engine - 智能判定

委托 `WorldEngine.decide()` 综合语境判断。

```python
config = GroupConfig(speaker_strategy="world_engine")
```

调用 WorldEngine 的五级优先判定系统（详见 [world/engine.md](../world/engine.md)）：
1. @提及（置信度 0.95）
2. 剧情关联（置信度 0.85）
3. 关系权重（置信度 0.7）
4. 关键词匹配（置信度 0.75）
5. 轮换降级（置信度 0.5）

## should_respond()

判断指定角色是否应该回复：

```python
should = scheduler.should_respond(conversation, message, "char_a")
```

- `mention` 策略：只在被 @ 时返回 `True`
- 其他策略：始终返回 `True`（由 `decide_next_speaker` 决定具体发言者）

## parse_mentions()

从文本中解析 @角色名，返回有序去重的角色 ID 列表：

```python
mentions = SpeakerScheduler.parse_mentions(
    text="@char_b 你觉得呢？ @char_c",
    character_ids=["char_a", "char_b", "char_c"],
    character_profiles=profiles,
)
# 返回: ["char_b", "char_c"]
```

- 同时匹配 `@character_id` 和 `@character_name`（中文名）
- 使用正则 `(?<![一-鿿\w])@([\w一-鿿]+)` 匹配
- 返回首次出现顺序、去重后的列表

## build_group_system_prompt()

构建群聊专用的系统提示词：

```python
prompt = scheduler.build_group_system_prompt(
    conversation=group,
    character_profiles=character_profiles,
    speaker_id="char_a",
    full_profile=char_a_profile,
)
```

提示词包含：
- 群聊名称和当前发言角色
- 参与角色资料（名称、描述、性格）
- 当前发言角色的完整角色卡（system_prompt 或各字段拼接）
- 角色间关系矩阵（仅显示 > 0 的维度）
- 群聊规则（禁止代替其他角色发言、使用 @ 引导对话等）
