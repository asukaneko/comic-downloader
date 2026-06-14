# group - 群聊会话系统

## 概述

`group` 是 NekoBot 3.0 的群聊会话模块，支持多个 AI 角色在同一个会话中进行群聊对话。系统提供发言调度、角色间关系管理、旁白叙述等能力，让多角色互动自然流畅。

**核心特性：**
- **多角色群聊** - 多个角色在同一会话中轮流发言
- **发言调度** - 5 种发言策略：轮询、@提及、相关性、随机、旁白驱动
- **角色间关系** - 四维关系模型（熟悉、信任、好感、竞争），带变更历史
- **旁白系统** - 第三人称场景叙述，支持定时/场景变化/沉默触发
- **会话集成** - 与 Session 系统深度集成，通过 `session_mode: "group"` 创建群聊

## 架构总览

```
用户消息
  │
  ▼
Session (mode="group")
  │
  ├── SpeakerScheduler.decide_next_speaker()
  │   ├── round_robin  轮询
  │   ├── mention      @提及
  │   ├── relevance    相关性
  │   ├── random       随机
  │   └── narrator_driven 旁白驱动
  │
  ├── build_group_system_prompt()
  │   ├── 群聊名称与描述
  │   ├── 参与角色资料
  │   └── 角色间关系矩阵
  │
  ├── 角色依次回复
  │
  ├── NarratorCharacter.should_narrate()
  │   └── build_narrate_prompt()  生成旁白
  │
  └── advance_turn()  推进回合
```

## 核心类

### GroupConfig

群聊配置，控制群聊的行为参数。

```python
from nbot.group import GroupConfig

config = GroupConfig(
    speaker_strategy="mention",
    max_chars_per_turn=800,
    allow_character_cross_talk=True,
    shared_memory=True,
    token_budget=4000,
    auto_narrate=True,
    narrate_interval=3,
)
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `speaker_strategy` | `str` | `"mention"` | 发言策略 |
| `max_chars_per_turn` | `int` | `800` | 每轮最大字符数 |
| `allow_character_cross_talk` | `bool` | `True` | 允许角色间交叉对话 |
| `shared_memory` | `bool` | `True` | 共享记忆 |
| `token_budget` | `int` | `4000` | Token 预算 |
| `auto_narrate` | `bool` | `True` | 自动旁白 |
| `narrate_interval` | `int` | `3` | 每 N 轮触发一次旁白 |

### GroupConversation

群聊会话实体，包含角色列表、发言队列、关系矩阵等。

```python
from nbot.group import GroupManager

gm = GroupManager.instance()
group = gm.create_group(
    name="咖啡馆闲聊",
    character_ids=["char_a", "char_b", "char_c"],
    narrator_id="char_a",
    config=config,
)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `group_id` | `str` | 群聊 ID（自动 `gc_` 前缀） |
| `name` | `str` | 群聊名称 |
| `character_ids` | `list[str]` | 参与角色 ID 列表 |
| `narrator_id` | `str` | 旁白角色 ID（可选） |
| `active_speaker` | `str` | 当前发言者 |
| `speaker_queue` | `list` | 发言队列 |
| `config` | `GroupConfig` | 群聊配置 |
| `turn_count` | `int` | 回合计数 |
| `bound_channel` | `str` | 绑定的频道 ID |
| `relations` | `dict` | 角色间关系矩阵 |

### InterCharacterRelation

角色间关系，四维模型。

```python
# 获取两个角色的关系
relation = group.get_relation("char_a", "char_b")
print(relation.familiarity)  # 熟悉度
print(relation.trust)        # 信任度
print(relation.affection)    # 好感度
print(relation.rivalry)      # 竞争度

# 更新关系
group.set_relation("char_a", "char_b", "affection", 10, "一起经历了冒险")
```

| 字段 | 范围 | 说明 |
|------|------|------|
| `familiarity` | 0-100 | 熟悉程度 |
| `trust` | 0-100 | 信任程度 |
| `affection` | 0-100 | 好感程度 |
| `rivalry` | 0-100 | 竞争/对抗程度 |

每次变更自动记录到 `history`（最多保留 50 条），包含变更维度、数值和原因。

### GroupManager

群聊管理器，负责群聊的 CRUD 和频道绑定。通过 `instance()` 获取全局单例。

```python
from nbot.group import GroupManager

gm = GroupManager.instance()

# 创建群聊
group = gm.create_group("咖啡馆闲聊", ["char_a", "char_b"])

# 查询
group = gm.get_group("gc_abc")
groups = gm.list_groups()

# 更新
gm.update_group("gc_abc", name="新名字")

# 频道绑定
gm.bind_channel("qq_group_123", "gc_abc")
```

### SpeakerScheduler

发言调度器，决定下一个发言的角色。通过 `SpeakerScheduler` 类直接使用。

#### 发言策略

| 策略 | 说明 |
|------|------|
| `round_robin` | 轮流发言，按角色列表顺序循环 |
| `mention` | 仅在被 @提及时发言（默认策略） |
| `random` | 随机选择发言者 |
| `relevance` | 根据消息与角色的相关性选择 |
| `narrator_driven` | 由旁白角色决定发言者 |

```python
from nbot.group.scheduler import SpeakerScheduler

scheduler = SpeakerScheduler()
next_speaker = scheduler.decide_next_speaker(
    conversation=group,
    message=user_message,
    character_ids=["char_a", "char_b", "char_c"],
    last_speaker="char_a",
)
```

#### 群聊系统提示词

`scheduler.build_group_system_prompt()` 构建群聊专用的系统提示词，包含：
- 群聊名称
- 参与角色资料（名称、描述、性格）
- 角色间关系矩阵

### NarratorCharacter

旁白角色，负责第三人称场景叙述。

#### 触发条件

| 触发类型 | 说明 |
|----------|------|
| `scene_change` | 场景变化时立即触发 |
| `character_join` | 角色加入时立即触发 |
| `plot_node` | 剧情节点到达时立即触发 |
| `manual` | 手动触发 |
| 定时触发 | 每 N 轮自动触发（`narrate_interval`） |
| 沉默触发 | 超过 5 分钟无旁白时触发 |

#### 旁白规则

`build_narrate_prompt()` 生成旁白提示词，遵循以下规则：
- 仅描述场景和氛围，不替角色说话
- 第三人称视角
- 2-4 句话
- 中性语调

```python
from nbot.group.narrator import NarratorCharacter

narrator = NarratorCharacter()
if narrator.should_narrate("scene_change", turn_count=5, narrate_interval=3):
    prompt = narrator.build_narrate_prompt(
        trigger="scene_change",
        scene_context={"location": "咖啡馆", "time": "傍晚"},
        recent_summary="角色们在讨论天气",
    )
```

## Web API

### 群聊管理

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/groups` | 列出所有群聊 |
| POST | `/api/groups` | 创建群聊（需 `name` + `character_ids`） |
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
| PUT | `/api/groups/<group_id>/relations` | 更新关系（需 `char_a`、`char_b`、`dimension`、`delta`、`reason`） |

### 会话集成

创建群聊模式的会话：

```bash
curl -X POST /api/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "session_mode": "group",
    "name": "咖啡馆闲聊",
    "character_ids": ["char_a", "char_b", "char_c"],
    "group_config": {
      "speaker_strategy": "mention",
      "auto_narrate": true,
      "narrate_interval": 3
    }
  }'
```

三种会话模式：

| 模式 | 说明 |
|------|------|
| `character` | 传统单角色对话（默认） |
| `group` | 多角色群聊 |
| `agent` | 纯 Agent 模式，无角色卡 |

## 目录结构

```
nbot/group/
├── __init__.py        # 模块入口
├── models.py          # 数据模型（GroupConfig / GroupConversation / InterCharacterRelation）
├── manager.py         # GroupManager 群聊管理器
├── scheduler.py       # SpeakerScheduler 发言调度器
└── narrator.py        # NarratorCharacter 旁白角色
```

## 数据存储

```
data/web/
└── groups.json        # 群聊数据（群聊定义 + 频道绑定 + 角色间关系）
```

## 使用示例

### 创建群聊并开始对话

```python
from nbot.group import GroupManager, GroupConfig

gm = GroupManager.instance()

# 创建群聊
config = GroupConfig(
    speaker_strategy="mention",
    auto_narrate=True,
    narrate_interval=3,
)
group = gm.create_group(
    name="校园日常",
    character_ids=["char_sakura", "char_ren", "char_yuki"],
    config=config,
)

# 绑定到 QQ 群
gm.bind_channel("qq_group_456", group.group_id)

# 查看角色间关系
matrix = group.get_relation_matrix()
```

### 更新角色关系

```python
# 通过 Web API 更新
# PUT /api/groups/gc_abc/relations
# {
#   "char_a": "char_sakura",
#   "char_b": "char_ren",
#   "dimension": "affection",
#   "delta": 10,
#   "reason": "一起完成了社团活动"
# }

# 或直接代码调用
group.set_relation("char_sakura", "char_ren", "affection", 10, "一起完成了社团活动")
```

### 配置发言策略

```python
# 切换为轮询模式
# PUT /api/groups/gc_abc/strategy
# {"strategy": "round_robin"}

# 或代码调用
group.config.speaker_strategy = "round_robin"
```
