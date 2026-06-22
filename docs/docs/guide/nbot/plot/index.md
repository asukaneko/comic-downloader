# plot - 剧情图与分支故事系统

## 概述

`plot` 是 NekoBot 的剧情模式模块，实现分支故事图（Branching Plot Graph）系统。每轮对话后 AI 自动生成 3 个不同级别的选择项，玩家选择后形成剧情分支，构建出树状剧情图。系统通过三个桥接模块将剧情事件自动同步到记忆、世界书和多媒体子系统。

**核心特性：**
- **AI 选择生成** - 每轮自动生成 3 个选择（普通/重要/转折），输出为可直接发送的第一人称消息
- **剧情图管理** - 节点 → 选择 → 边的有向图结构，支持回溯和 Mermaid 可视化
- **三级桥接** - 选择自动写入记忆（重要+）、世界书（转折点）、触发多媒体动作
- **回溯支持** - 可回退到任意历史节点重新选择
- **分支管理** - 支持多分支并行、分支切换和路径物化

## 架构总览

```
AI 回复
  │
  ▼
PlotChoiceGenerator.generate()
  │  调用 AI 生成 3 个选择项
  │  ┌─────────────────────────────────┐
  │  │ 普通 (normal)    - 保守回应     │
  │  │ 重要 (important) - 推进关系     │
  │  │ 转折 (turning)   - 剧情转折     │
  │  └─────────────────────────────────┘
  ▼
PlotGraphManager
  ├── add_node()        创建剧情节点
  ├── add_choice()      记录选择项
  │
  │  玩家选择后：
  ├── select_choice()   标记选择
  │   ├── PlotMemoryBridge      → 写入角色记忆
  │   ├── PlotWorldBookBridge   → 写入世界书（转折点）
  │   └── MultimediaBridge      → 触发表情包/TTS/场景描述
  │
  ├── add_edge()        建立节点连接
  └── generate_mermaid() 输出剧情图可视化
```

## 核心模块

### 1. 数据模型 ([models.md](./models.md))

定义剧情图的三种核心数据结构：

- **PlotNode** - 剧情节点，代表故事中的关键时刻，含状态快照和 v3.1 活动图扩展
- **PlotChoice** - 分支选择，含级别、意图、风险等级和隐藏条件
- **PlotEdge** - 连接两个节点的边

### 2. 剧情图管理器 ([graph_manager.md](./graph_manager.md))

PlotGraphManager 负责节点/选择/边的 CRUD、分支管理、回溯、Mermaid 可视化和 JSON 持久化。

### 3. 选择生成器 ([choice_generator.md](./choice_generator.md))

PlotChoiceGenerator 调用 LLM 生成 3 个不同级别的选择项，自动规范化文本为第一人称消息。

### 4. 桥接模块 ([bridges.md](./bridges.md))

选择被标记后自动同步到三个子系统：
- **PlotMemoryBridge** - 写入角色记忆
- **PlotWorldBookBridge** - 写入世界书
- **MultimediaBridge** - 触发多媒体动作

## Web API

| 方法 | 路由 | 说明 |
|------|------|------|
| POST | `/api/plot/toggle` | 开启/关闭会话的剧情模式 |
| GET | `/api/plot/<conversation_id>/graph` | 获取完整剧情图 |
| GET | `/api/plot/<conversation_id>/latest-choices` | 获取最新未选择的选择项 |
| GET | `/api/plot/<conversation_id>/mermaid` | 获取 Mermaid 图表代码 |
| POST | `/api/plot/<conversation_id>/select` | 选择一个选项 |
| POST | `/api/plot/<conversation_id>/rollback` | 回溯到指定节点 |
| POST | `/api/plot/<conversation_id>/regenerate-choices` | 重新生成当前节点的选择项 |
| GET | `/api/plot/<conversation_id>/branch-preview` | 预览到指定节点的消息路径 |
| POST | `/api/plot/<conversation_id>/switch` | 切换到不同分支 |
| POST | `/api/plot/<conversation_id>/branch` | 从指定节点+选择创建新分支 |

## 目录结构

```
nbot/plot/
├── __init__.py            # 模块入口
├── models.py              # 数据模型（PlotNode / PlotChoice / PlotEdge）
├── graph_manager.py       # 剧情图管理器
├── choice_generator.py    # AI 选择生成器
├── memory_bridge.py       # 记忆桥接
├── world_book_bridge.py   # 世界书桥接
└── multimedia_bridge.py   # 多媒体桥接
```

## 数据存储

```
data/web/
└── plot_graphs.json       # 剧情图数据（节点、选择、边、激活节点）
```

## 与其他模块的关系

| 模块 | 关系 |
|------|------|
| **character** | 剧情节点捕获角色状态和关系快照；分支物化时恢复角色上下文 |
| **memory** | `PlotMemoryBridge` 将重要选择写入角色记忆 |
| **review** | Review Pipeline 的 `PlotUpdate` 决定是否创建剧情节点 |
| **world** | `PlotWorldBookBridge` 将转折点写入世界书 |
| **events** | 发射 `plot.*` 系列标准化事件 |
| **hooks** | 通过 `ConversationEventBus` 发射生命周期事件 |
