# Plot 桥接模块

剧情图系统通过三个桥接模块将剧情事件自动同步到记忆、世界书和多媒体子系统。桥接在 `select_choice` 时触发。

## PlotMemoryBridge - 记忆桥接

选择被标记后，根据级别自动写入角色记忆。

### 级别映射

| 选择级别 | 记忆类型 | 说明 |
|----------|----------|------|
| `normal` | 不写入 | 普通选择不产生记忆 |
| `important` | `relationship` | 关系相关记忆 |
| `turning_point` | `event` | 重要事件记忆 |
| `ending` | `long` | 长期记忆 |

### 使用方式

```python
from nbot.plot.memory_bridge import PlotMemoryBridge

bridge = PlotMemoryBridge.instance()
bridge.on_choice_selected(
    choice=choice,
    conversation_id="conv_abc",
    character_id="char_xyz",
    user_id="user_123",
    memory_service=memory_service,
)
```

内部调用 `memory_service.save()` 写入记忆，选择文本作为记忆内容。

## PlotWorldBookBridge - 世界书桥接

当剧情到达转折点时，自动将事件写入世界书。

### 触发条件

仅 `turning_point` 级别的选择触发。

### 写入参数

| 参数 | 值 |
|------|-----|
| 优先级 | 80 |
| 条目类型 | `event` |
| 标签 | `["plot", "turning_point"]` |
| 关键词 | 从中文文本自动提取（2-4 字，最多 5 个） |

### 关键词提取

使用正则 `[一-鿿]{2,4}` 从选择文本和意图中提取中文关键词。

### 使用方式

```python
from nbot.plot.world_book_bridge import PlotWorldBookBridge

bridge = PlotWorldBookBridge.instance()
bridge.on_turning_point(
    choice=choice,
    conversation_id="conv_abc",
    character_id="char_xyz",
    book_id="wb_001",
    world_book_store=world_book_store,
)
```

## MultimediaBridge - 多媒体桥接

根据选择级别触发不同的多媒体动作。

### 触发规则

| 选择级别 | 表情包强度 | TTS | 场景描述 | 剧情回顾 |
|----------|-----------|-----|----------|----------|
| `normal` | 0.3 | - | - | - |
| `important` | 0.6 | - | - | - |
| `turning_point` | 0.9 | ✅ | ✅ | - |
| `ending` | 1.0 | ✅ | - | ✅ |

### 使用方式

```python
from nbot.plot.multimedia_bridge import MultimediaBridge

bridge = MultimediaBridge.instance()
actions = bridge.generate_actions(choice_level="turning_point", plot_nodes=nodes)
# 返回: [{"type": "sticker", ...}, {"type": "tts", ...}, {"type": "scene_description", ...}]
```

### 辅助方法

```python
# 角色状态卡（姓名、心情、精力、场景、关系）
card = bridge.build_status_card(character_state, relationship_state, scene)

# 群聊布局（含发言指示器）
layout = bridge.build_group_layout(group_conversation, active_speaker)
```

## 桥接触发流程

```
select_choice("pc_001")
  │
  ├── PlotMemoryBridge.on_choice_selected()
  │     └── memory_service.save(...)  (important+)
  │
  ├── PlotWorldBookBridge.on_turning_point()
  │     └── world_book_store.add_entry(...)  (turning_point only)
  │
  └── MultimediaBridge.generate_actions()
        ├── sticker (all levels)
        ├── tts (turning_point, ending)
        ├── scene_description (turning_point)
        └── story_recap (ending)
```

桥接操作均为非阻塞，失败不影响主流程（异常仅 `_log.debug`）。
