# events - 事件标准化系统

## 概述

`events` 模块提供标准化事件名常量，涵盖 character、plot、group、world、workflow、review 六大域。所有模块发射事件时应优先使用这里的常量，避免事件名散落在业务代码中。

**核心特性：**
- **统一命名规范** - 采用 `domain.phase.action` 三层命名结构
- **六大事件域** - 覆盖角色、剧情、群聊、世界、工作流、审查全部场景
- **向后兼容** - 与 Hook 系统的 `HookEventType` 完全兼容

## 核心模块

### 事件名常量 ([names.md](./names.md))

所有标准化事件名常量定义，按六大域组织：
- **character** (8 事件) - 角色对话生命周期
- **plot** (6 事件) - 剧情分支系统
- **group** (5 事件) - 群聊
- **world** (2 事件) - 世界状态与世界书
- **workflow** (3 事件) - 工作流
- **review** (5 事件) - Review Pipeline

## 命名规范

所有事件名遵循 `domain.phase.action` 格式：

```
character.turn.before      # 角色回合开始前
plot.node.created          # 剧情节点创建
group.message.received     # 群聊消息接收
world.event.triggered      # 世界事件触发
workflow.started           # 工作流开始
review.memory.scored       # 记忆审查评分
```

## 目录结构

```
nbot/events/
├── __init__.py    # 模块入口，导出所有常量
└── names.py       # 标准化事件名常量定义
```

## 与其他模块的关系

| 模块 | 关系 |
|------|------|
| **hooks** | 事件通过 `ConversationEventBus` 发射，Hook 系统消费事件 |
| **character** | `CharacterRuntime._emit_hook()` 发射角色生命周期事件 |
| **plot** | `PlotGraphManager._emit()` 发射剧情图事件 |
| **review** | `ReviewPipeline` 发射审查开始/完成事件 |
| **group** | 群聊流程发射消息接收、发言者选定等事件 |
| **world** | 世界引擎触发 `world.*` 事件 |
