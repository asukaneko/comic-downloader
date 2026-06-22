# review - Review Pipeline 审查层

## 概述

`review` 模块实现 Review Pipeline 审查层，每轮对话后对对话内容进行结构化审查。当前实现为规则版（不调用大模型），后续可替换为 LLM Review。

**核心特性：**
- **规则审查** - 基于关键词规则判断记忆写入、关系变化及剧情节点更新
- **结构化输出** - 返回标准化的审查结果，包含记忆写入建议、关系变化、8 维评分等
- **自我修正** - 评分低于阈值时生成下一轮修正提示
- **时间感知** - 计算现实时间间隔，生成角色扮演连续性提示
- **事件驱动** - 支持通过 event_bus 发射审查事件

## 架构总览

```
CharacterRuntime.after_turn()
  │
  ▼
ReviewPipeline.run(inp)
  ├── run_rule_review(inp)
  │   ├── 关系变化判断（关键词 + 剧情选择 + 时间间隔）
  │   ├── 记忆写入判断（记忆价值 + 选择级别 + 关系变化）
  │   ├── 剧情更新（important/turning_point/ending）
  │   ├── 世界书更新（turning_point/ending）
  │   └── 质量评分（规则计算 + AutoState LLM 缓存）
  │
  ├── 输出 ReviewOutput
  │   ├── memory_items → MemoryFS 同步
  │   ├── relationship_delta → 关系状态更新
  │   └── plot_update → 剧情节点创建
  │
  ├── build_correction_hint(scores)
  │   └── 低分维度 → 下一轮自我修正提示
  │
  └── 发射 review.* 事件
```

## 核心模块

### 1. 数据模型 ([models.md](./models.md))

- **ReviewScore** - 8 维角色体验评分
- **MemoryItem** - 待写入的记忆条目
- **RelationshipDelta** - 六维关系变化增量
- **PlotUpdate** - 剧情更新建议
- **WorldBookUpdate** - 世界书更新建议
- **ReviewInput** / **ReviewOutput** - 审查管道输入/输出

### 2. 审查管道 ([pipeline.md](./pipeline.md))

ReviewPipeline 编排器 + 规则版审查实现（run_rule_review）。基于关键词和上下文判断关系变化、记忆写入、剧情更新。

### 3. 自我修正 ([self_correction.md](./self_correction.md))

评分低于阈值时生成下一轮修正提示，一次性消费后清除。

### 4. 时间连续性 ([time_context.md](./time_context.md))

计算现实时间间隔，生成 6 级连续性等级和角色扮演提示。

## Web API

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/review/logs` | 获取审查日志 |
| GET | `/api/review/memory-fs` | 获取 MemoryFS 文件列表 |
| GET | `/api/review/event-stream` | SSE 事件流 |
| POST | `/api/review/run` | 手动触发审查 |

## 目录结构

```
nbot/review/
├── __init__.py          # 模块入口
├── models.py            # ReviewInput / ReviewOutput 数据模型
├── pipeline.py          # ReviewPipeline 编排器
├── rule_review.py       # 规则版审查实现
├── self_correction.py   # 自我修正提示系统
└── time_context.py      # 现实时间连续性上下文
```

## 与其他模块的关系

| 模块 | 关系 |
|------|------|
| **character** | `CharacterRuntime._run_review()` 在 after_turn 执行审查 |
| **memory** | 审查输出写入 MemoryFS（用户摘要、日记、剧情摘要） |
| **plot** | `PlotUpdate` 决定是否创建剧情节点和节点级别 |
| **events** | 发射 `review.*` 系列标准化事件 |
| **hooks** | 通过 `ConversationEventBus` 发射审查生命周期事件 |
