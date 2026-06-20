# world - WorldEngine 群聊环境判定器

## 概述

`world` 模块实现 WorldEngine 群聊环境判定器，为群聊场景提供智能发言策略。MVP 版本基于规则判断，无需调用大模型，后续可替换为 LLM 版本。

**核心特性：**
- **智能发言选择** - 综合考虑 @提及、剧情关联、关系权重、关键词匹配
- **旁白判定** - 自动判断是否需要旁白叙述
- **轮换降级** - 无明确匹配时按顺序轮换，避免连续独白
- **可扩展** - 支持后续替换为 LLM 版本

## 核心类

### WorldEngineDecision

判定结果数据模型。

```python
from nbot.world.engine import WorldEngineDecision

decision = WorldEngineDecision(
    speaker_id="char_xyz",
    reason="角色被用户直接提及（@char_xyz）",
    should_narrate_before=False,
    should_narrate_after=True,
    narrate_trigger="剧情转折点",
    confidence=0.95,
)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `speaker_id` | `str` | 选定的发言角色 ID |
| `reason` | `str` | 选择原因描述 |
| `should_narrate_before` | `bool` | 是否需要发言前旁白 |
| `should_narrate_after` | `bool` | 是否需要发言后旁白 |
| `narrate_trigger` | `str` | 旁白触发原因 |
| `confidence` | `float` | 判断置信度（0-1） |

### WorldEngine

群聊世界引擎判定器。

```python
from nbot.world import get_world_engine

# 获取全局单例
engine = get_world_engine()

# 判定下一个发言角色
decision = engine.decide(
    message="大家好，今天天气真不错",
    character_ids=["char_a", "char_b", "char_c"],
    recent_messages=recent_messages,
    characters=characters_info,
    relations=relations_data,
    scene=scene_info,
    active_plot_node=active_node,
    last_speaker="char_a",
)

print(f"发言角色: {decision.speaker_id}")
print(f"选择原因: {decision.reason}")
print(f"置信度: {decision.confidence}")
```

## 判定策略

WorldEngine 按优先级顺序尝试以下策略：

### 1. @提及优先（置信度 0.95）

检查消息中是否明确 @了某个角色。

```python
# 用户消息: "@char_b 你觉得呢？"
# 结果: speaker_id = "char_b"
```

**判定规则：**
- 检查 `@{角色名}` 或 `@{角色ID}` 模式
- 优先匹配角色名，其次匹配角色 ID
- 置信度最高（0.95）

### 2. 剧情关联（置信度 0.85）

检查消息是否与当前激活的剧情节点相关。

```python
# 当前剧情节点参与者: ["char_a", "char_c"]
# 用户消息: "我们继续刚才的话题"
# 结果: speaker_id = "char_a" 或 "char_c"
```

**判定规则：**
- 检查剧情节点的 `participants` 字段
- 检查剧情摘要中是否出现角色名
- 剧情转折点/结局时触发发言后旁白

### 3. 关系权重（置信度 0.7）

根据关系矩阵选择关系权重最高的角色。

```python
# 关系数据:
# char_a: affection=80, trust=70, familiarity=60
# char_b: affection=90, trust=80, familiarity=70
# 结果: speaker_id = "char_b"（权重最高）
```

**权重计算公式：**
```
weight = affection + trust * 0.8 + familiarity * 0.5
```

**排除规则：**
- 排除上一个发言者，避免连续独白
- 如果排除后无候选，则不排除

### 4. 关键词匹配（置信度 0.75）

检查消息中是否出现角色名关键词。

```python
# 用户消息: "小明你觉得怎么样？"
# 角色名: {"char_a": "小明", "char_b": "小红"}
# 结果: speaker_id = "char_a"
```

**判定规则：**
- 检查消息中是否包含角色名
- 优先匹配较长的角色名
- 置信度 0.75

### 5. 轮换降级（置信度 0.5）

无明确匹配时按顺序轮换。

```python
# 角色列表: ["char_a", "char_b", "char_c"]
# 上一个发言者: "char_a"
# 结果: speaker_id = "char_b"
```

**轮换规则：**
- 排除上一个发言者
- 按角色列表顺序选择
- 置信度最低（0.5）

## 旁白判定

### should_narrate()

判断当前是否需要旁白叙述。

```python
should_narrate = engine.should_narrate(
    message="我们换个地方吧",
    recent_messages=recent_messages,
    active_plot_node=active_node,
    turn_count=10,
    narrate_interval=5,
)
```

**触发条件：**

| 条件 | 说明 | 示例 |
|------|------|------|
| 剧情转折点 | 活跃剧情节点为转折点/结局 | `active_plot_node.level in ("turning_point", "ending")` |
| 周期触发 | 每隔 N 轮触发一次 | `turn_count % narrate_interval == 0` |
| 场景切换 | 消息包含场景切换关键词 | "换个地方"、"去...吧"、"离开"、"到达" |

**场景切换关键词：**
- 换个地方
- 去...吧
- 离开
- 到达
- 来到
- 我们走

### 旁白类型

| 类型 | 时机 | 说明 |
|------|------|------|
| `should_narrate_before` | 发言前 | 用于场景描述、氛围营造 |
| `should_narrate_after` | 发言后 | 用于总结、过渡、剧情推进 |

## 与 SpeakerScheduler 集成

WorldEngine 已集成到 `SpeakerScheduler`，作为 `world_engine` 发言策略：

```python
from nbot.group.scheduler import SpeakerScheduler

scheduler = SpeakerScheduler()

# 使用 world_engine 策略
speaker_id = scheduler.select_speaker(
    message="大家好",
    character_ids=["char_a", "char_b", "char_c"],
    strategy="world_engine",
    recent_messages=recent_messages,
    characters=characters_info,
    relations=relations_data,
    scene=scene_info,
    active_plot_node=active_node,
    last_speaker="char_a",
)
```

## 与 AIPipeline 集成

WorldEngine 已集成到 `AIPipeline`，在群聊场景自动发射标准化事件：

```python
# AIPipeline 中发射的事件
GROUP_MESSAGE_RECEIVED      # 群聊消息接收
GROUP_SPEAKER_SELECTED      # 发言者选定
GROUP_NARRATION_REQUESTED   # 旁白请求
```

## Web API

WorldEngine 的判定结果可通过以下 API 获取：

| 方法 | 路由 | 说明 |
|------|------|------|
| POST | `/api/group/decide` | 判定下一个发言角色 |
| POST | `/api/group/narrate` | 判断是否需要旁白 |

### 判定发言角色

```bash
curl -X POST /api/group/decide \
  -H "Content-Type: application/json" \
  -d '{
    "message": "大家好",
    "character_ids": ["char_a", "char_b", "char_c"],
    "last_speaker": "char_a"
  }'
```

**响应示例：**
```json
{
  "speaker_id": "char_b",
  "reason": "无明确匹配，按顺序轮换",
  "confidence": 0.5,
  "should_narrate_before": false,
  "should_narrate_after": false
}
```

## 目录结构

```
nbot/world/
├── __init__.py    # 模块入口
└── engine.py      # WorldEngine 实现
```

## 使用示例

### 基本使用

```python
from nbot.world import get_world_engine

# 获取全局单例
engine = get_world_engine()

# 准备数据
character_ids = ["char_a", "char_b", "char_c"]
characters = {
    "char_a": {"name": "小明"},
    "char_b": {"name": "小红"},
    "char_c": {"name": "小刚"},
}
relations = [
    {"character_id": "char_a", "affection": 80, "trust": 70, "familiarity": 60},
    {"character_id": "char_b", "affection": 90, "trust": 80, "familiarity": 70},
    {"character_id": "char_c", "affection": 70, "trust": 60, "familiarity": 50},
]

# 判定发言角色
decision = engine.decide(
    message="大家好，今天天气真不错",
    character_ids=character_ids,
    characters=characters,
    relations=relations,
    last_speaker="char_a",
)

print(f"发言角色: {decision.speaker_id}")
print(f"选择原因: {decision.reason}")
print(f"置信度: {decision.confidence}")
```

### 带剧情节点的判定

```python
# 当前剧情节点
active_plot_node = {
    "node_id": "pn_001",
    "title": "关键时刻",
    "level": "turning_point",
    "participants": ["char_a", "char_c"],
    "summary": "面对重大抉择",
}

# 判定发言角色
decision = engine.decide(
    message="我们该怎么办？",
    character_ids=character_ids,
    characters=characters,
    active_plot_node=active_plot_node,
    last_speaker="char_b",
)

# 剧情相关角色会优先被选择
print(f"发言角色: {decision.speaker_id}")
print(f"选择原因: {decision.reason}")

# 剧情转折点会触发发言后旁白
print(f"需要发言后旁白: {decision.should_narrate_after}")
```

### 旁白判定

```python
# 判断是否需要旁白
should_narrate = engine.should_narrate(
    message="我们换个地方吧",
    active_plot_node=active_plot_node,
    turn_count=10,
    narrate_interval=5,
)

print(f"需要旁白: {should_narrate}")

# 场景切换关键词会触发旁白
should_narrate = engine.should_narrate(
    message="我们去公园吧",
    turn_count=5,
    narrate_interval=5,
)
print(f"需要旁白: {should_narrate}")  # True
```

### 完整群聊流程

```python
from nbot.world import get_world_engine
from nbot.group.scheduler import SpeakerScheduler

# 初始化
engine = get_world_engine()
scheduler = SpeakerScheduler()

# 群聊消息处理
def handle_group_message(message, character_ids, last_speaker):
    # 1. 判定发言角色
    decision = engine.decide(
        message=message,
        character_ids=character_ids,
        characters=characters,
        relations=relations,
        active_plot_node=active_node,
        last_speaker=last_speaker,
    )
    
    # 2. 判断是否需要旁白
    should_narrate = engine.should_narrate(
        message=message,
        active_plot_node=active_node,
        turn_count=turn_count,
        narrate_interval=5,
    )
    
    # 3. 生成旁白（如果需要）
    if should_narrate:
        narration = generate_narration(message, decision)
    
    # 4. 生成角色回复
    reply = generate_character_reply(decision.speaker_id, message)
    
    return {
        "speaker_id": decision.speaker_id,
        "reply": reply,
        "narration": narration if should_narrate else None,
        "reason": decision.reason,
    }
```

## 扩展为 LLM 版本

当前实现为规则版，后续可扩展为 LLM 版本：

```python
class LLMWorldEngine:
    """LLM 版世界引擎（示例）"""
    
    def decide(self, message, character_ids, **kwargs) -> WorldEngineDecision:
        # 构建 Prompt
        prompt = self._build_prompt(message, character_ids, **kwargs)
        
        # 调用 LLM
        response = await llm.chat(prompt)
        
        # 解析 LLM 输出
        return self._parse_decision(response)
    
    def should_narrate(self, message, **kwargs) -> bool:
        # 调用 LLM 判断
        prompt = self._build_narrate_prompt(message, **kwargs)
        response = await llm.chat(prompt)
        return self._parse_narrate_decision(response)

# 在 WorldEngine 中使用
engine = WorldEngine(llm_engine=LLMWorldEngine())
```

## 最佳实践

1. **策略优先级** - 严格按优先级顺序尝试判定策略
2. **置信度使用** - 根据置信度决定是否需要人工确认
3. **旁白时机** - 合理使用旁白，避免过度打断对话
4. **性能优化** - 规则版判定应保持低延迟
5. **日志记录** - 记录判定过程，便于调试和优化
