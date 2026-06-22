# NarratorCharacter 旁白角色

第三人称场景叙述系统，为群聊提供场景描述、氛围营造和过渡衔接。

## 触发条件

| 触发类型 | 说明 | 优先级 |
|----------|------|--------|
| `scene_change` | 场景变化时立即触发 | 高 |
| `character_join` | 角色加入时立即触发 | 高 |
| `plot_node` | 剧情节点到达时立即触发 | 高 |
| `silence` | 超过 5 分钟无旁白时触发 | 中 |
| `interval` | 每 N 轮自动触发（`narrate_interval`） | 低 |
| `manual` | 手动触发 | - |

## 基本用法

```python
from nbot.group.narrator import NarratorCharacter

narrator = NarratorCharacter()

# 判断是否需要旁白
if narrator.should_narrate(
    trigger="scene_change",
    turn_count=5,
    narrate_interval=3,
    last_narrate_time=last_narrate_ts,
):
    # 生成旁白提示词
    prompt = narrator.build_narrate_prompt(
        trigger="scene_change",
        scene_context={"location": "咖啡馆", "time": "傍晚"},
        recent_summary="角色们在讨论天气",
    )
    
    # 格式化旁白输出
    narration = narrator.format_narration(raw_text)
```

## should_narrate()

判断当前是否需要旁白叙述。

```python
should = narrator.should_narrate(
    trigger="scene_change",
    turn_count=10,
    narrate_interval=5,
    last_narrate_time=1719000000.0,
)
```

判断逻辑：
- `scene_change` / `character_join` / `plot_node` / `manual` → 立即返回 `True`
- `interval` → 检查 `turn_count % narrate_interval == 0`
- `silence` → 检查距上次旁白是否超过 5 分钟

## build_narrate_prompt()

生成旁白提示词。

```python
prompt = narrator.build_narrate_prompt(
    trigger="scene_change",
    scene_context={
        "location": "咖啡馆",
        "time": "傍晚",
        "weather": "小雨",
    },
    recent_summary="角色们在讨论最近的考试",
    characters_present=["char_a", "char_b", "char_c"],
)
```

### 旁白规则

提示词中包含以下规则：
- 仅描述场景和氛围，**不替角色说话**
- 第三人称视角
- 2-4 句话
- 中性语调
- 不编造角色的心理活动或对话

## format_narration()

格式化旁白输出，添加视觉标记：

```python
formatted = narrator.format_narration("夕阳西下，咖啡馆里弥漫着淡淡的咖啡香。")
# 返回: "【旁白】夕阳西下，咖啡馆里弥漫着淡淡的咖啡香。"
```

## 与 WorldEngine 集成

当使用 `world_engine` 发言策略时，`WorldEngine.decide()` 的返回结果包含 `should_narrate_before` 和 `should_narrate_after` 字段，可直接驱动旁白：

```python
decision = engine.decide(message, character_ids, ...)
if decision.should_narrate_after:
    prompt = narrator.build_narrate_prompt(
        trigger=decision.narrate_trigger,
        scene_context=scene_context,
    )
```
