# world - WorldEngine 群聊环境判定器

## 概述

`world` 模块实现 WorldEngine 群聊环境判定器，为群聊场景提供智能发言策略和旁白判定。基于规则判断，无需调用大模型，后续可替换为 LLM 版本。

**核心特性：**
- **智能发言选择** - 五级优先系统：@提及 → 剧情关联 → 关系权重 → 关键词 → 轮换
- **旁白判定** - 自动判断是否需要旁白叙述（剧情转折/周期/场景切换）
- **置信度系统** - 每个判定结果带置信度（0.5-0.95）
- **可扩展** - 支持后续替换为 LLM 版本

## 核心模块

### 判定引擎 ([engine.md](./engine.md))

WorldEngine 提供两个核心方法：
- **decide()** - 五级优先发言选择
- **should_narrate()** - 旁白触发判定

## 与 SpeakerScheduler 集成

WorldEngine 已集成到 `SpeakerScheduler`，作为第 6 种发言策略 `world_engine`：

```python
config = GroupConfig(speaker_strategy="world_engine")
```

当使用此策略时，`SpeakerScheduler.decide_next_speaker()` 内部调用 `WorldEngine.decide()`。

## 目录结构

```
nbot/world/
├── __init__.py    # 模块入口
└── engine.py      # WorldEngine 实现
```

## 与其他模块的关系

| 模块 | 关系 |
|------|------|
| **group** | `SpeakerScheduler` 的 `world_engine` 策略委托 `WorldEngine.decide()` |
| **plot** | 判定时参考 `active_plot_node` 的参与者和级别 |
| **character** | 判定时使用角色间关系数据（affection、trust、familiarity） |
| **events** | 群聊流程发射 `group.speaker.selected` 事件 |
