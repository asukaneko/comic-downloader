# group - 群聊会话系统

## 概述

`group` 是 NekoBot 的群聊会话模块，支持多个 AI 角色在同一个会话中进行群聊对话。系统提供发言调度、角色间关系管理、旁白叙述和跨角色对话等能力，让多角色互动自然流畅。

**核心特性：**
- **多角色群聊** - 多个角色在同一会话中轮流发言
- **发言调度** - 6 种发言策略：轮询、@提及、相关性、随机、旁白驱动、智能判定
- **角色间关系** - 四维关系模型（熟悉、信任、好感、竞争），带变更历史
- **旁白系统** - 第三人称场景叙述，支持定时/场景变化/沉默触发
- **跨角色对话** - @mention 触发被 @ 角色的额外对话

## 架构总览

```
用户消息
  │
  ▼
Session (mode="group")
  │
  ├── SpeakerScheduler.decide_next_speaker()
  │   ├── round_robin      轮询
  │   ├── mention          @提及
  │   ├── relevance        相关性
  │   ├── random           随机
  │   ├── narrator_driven  旁白驱动
  │   └── world_engine     智能判定
  │
  ├── build_group_system_prompt()
  │   ├── 群聊名称与描述
  │   ├── 参与角色资料
  │   └── 角色间关系矩阵
  │
  ├── 角色依次回复
  │
  ├── CrossTalk 处理 @mention
  │   └── 被 @ 角色额外回复
  │
  ├── NarratorCharacter.should_narrate()
  │   └── build_narrate_prompt()  生成旁白
  │
  └── advance_turn()  推进回合
```

## 核心模块

### 1. 数据模型 ([models.md](./models.md))

- **GroupConfig** - 群聊配置（发言策略、Token 预算、旁白间隔等）
- **GroupConversation** - 群聊会话实体（角色列表、发言队列、关系矩阵）
- **InterCharacterRelation** - 角色间关系（四维模型 + 变更历史）

### 2. 发言调度器 ([scheduler.md](./scheduler.md))

SpeakerScheduler 决定下一个发言的角色，支持 6 种策略。提供 `build_group_system_prompt()` 构建群聊专用提示词。

### 3. 旁白角色 ([narrator.md](./narrator.md))

NarratorCharacter 提供第三人称场景叙述，支持 6 种触发条件。

### 4. 跨角色对话 ([cross_talk.md](./cross_talk.md))

CrossTalk 处理 @mention 跨角色对话，解析回复中的 `@角色名` 触发额外对话。

## Web API

### 群聊管理

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/groups` | 列出所有群聊 |
| POST | `/api/groups` | 创建群聊 |
| GET | `/api/groups/<group_id>` | 获取群聊详情 |
| PUT | `/api/groups/<group_id>` | 更新群聊 |
| DELETE | `/api/groups/<group_id>` | 删除群聊 |
| POST | `/api/groups/<group_id>/characters` | 添加角色 |
| DELETE | `/api/groups/<group_id>/characters/<char_id>` | 移除角色 |
| PUT | `/api/groups/<group_id>/strategy` | 设置发言策略 |
| POST | `/api/groups/<group_id>/bind` | 绑定频道 |

### 关系管理

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/groups/<group_id>/relations` | 获取角色间关系矩阵 |
| PUT | `/api/groups/<group_id>/relations` | 更新关系 |

## 目录结构

```
nbot/group/
├── __init__.py        # 模块入口
├── models.py          # 数据模型（GroupConfig / GroupConversation / InterCharacterRelation）
├── manager.py         # GroupManager 群聊管理器
├── scheduler.py       # SpeakerScheduler 发言调度器
├── narrator.py        # NarratorCharacter 旁白角色
└── cross_talk.py      # @mention 跨角色对话处理器
```

## 数据存储

```
data/web/
└── groups.json        # 群聊数据（群聊定义 + 频道绑定 + 角色间关系）
```

## 与其他模块的关系

| 模块 | 关系 |
|------|------|
| **character** | 每个发言角色通过 `CharacterRuntime` 独立运行 |
| **world** | `world_engine` 策略委托 `WorldEngine.decide()` |
| **plot** | `plot_node` 触发条件可驱动旁白生成 |
| **events** | 发射 `group.*` 系列标准化事件 |
