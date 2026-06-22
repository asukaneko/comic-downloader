# memory - MemoryFS 记忆逻辑文件系统

## 概述

`memory` 模块实现 MemoryFS 记忆逻辑文件系统，作为现有 PromptManager 记忆系统的上层组织层。通过 `path` 字段把记忆条目组织成角色可读的逻辑视图，支持用户关系摘要、日记、剧情摘要三层必读注入到 Prompt。

**核心特性：**
- **逻辑文件系统** - 使用路径组织记忆，支持层次化结构
- **三层必读注入** - 用户关系摘要 + 当前剧情摘要 + 最近日记摘要
- **智能截断** - 按条目数截断，避免切断单条记忆
- **持久化存储** - 独立持久化到 `memory_fs.json`

## 核心模块

### 1. 数据模型 ([models.md](./models.md))

**MemoryFile** - 逻辑记忆文件，含路径、内容、摘要、重要性、版本号等字段。

### 2. 文件系统 ([fs.md](./fs.md))

**MemoryFS** - 记忆逻辑文件系统管理器，提供 read/write/delete 操作、路径辅助方法、三层必读注入和智能截断。

## 路径规范

```
characters/{char_id}/general.md           # 角色通用信息
characters/{char_id}/users/{user_id}.md   # 对特定用户的关系摘要
characters/{char_id}/diary/daily.md       # 最近日常日记
characters/{char_id}/diary/weekly.md      # 本周摘要
characters/{char_id}/plot/{conv_id}.md    # 剧情摘要
characters/{char_id}/world/events.md      # 世界事件记录
```

## Web API

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/review/memory-fs` | 获取 MemoryFS 文件列表 |
| GET | `/api/review/memory-fs?path=<path>` | 获取指定路径的文件内容 |

## 目录结构

```
nbot/memory/
├── __init__.py    # 模块入口
├── fs.py          # MemoryFS 实现
└── models.py      # MemoryFile 数据模型
```

## 数据存储

```
data/web/
└── memory_fs.json    # MemoryFS 索引文件（path → MemoryFile）
```

## 与其他模块的关系

| 模块 | 关系 |
|------|------|
| **character** | `CharacterRuntime._inject_memory_fs()` 在 before_turn 注入三层必读上下文 |
| **review** | `ReviewPipeline` 输出驱动 MemoryFS 同步（用户摘要、日记、剧情摘要） |
| **plot** | `PlotMemoryBridge` 将重要选择写入 MemoryFS |
| **events** | 记忆写入发射 `character.memory.written` 事件 |
