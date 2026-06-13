# switches - 开关管理

## 概述

`switches.py` 提供按群组、用户和会话粒度的开关管理，用于控制功能启用/禁用，如 AI 回复开关、图转文开关等。

## 核心类

### SwitchManager

三级作用域的开关管理。

```
SwitchManager
├── group_switches: Dict[str, Dict]         # group_id → {switch_name: bool}
├── user_switches: Dict[str, Dict]          # user_id → {switch_name: bool}
├── conversation_switches: Dict[str, Dict]  # conversation_id → {switch_name: bool}
└── switch_configs: Dict[str, Dict]         # 开关定义 → {default, description}
```

## 方法说明

### add_switch(switch_name, default_value, description)

注册一个新开关，指定默认值和说明。

```python
switch_manager.add_switch("ai_reply", default_value=True, description="AI 自动回复")
switch_manager.add_switch("image_to_text", default_value=False, description="图转文功能")
```

### get_switch_state(switch_name, group_id, user_id, conversation_id)

获取开关状态，优先级：会话 > 用户 > 群组 > 默认值。

```python
state = switch_manager.get_switch_state("ai_reply", conversation_id="qq:group:123")
```

### set_switch_state(switch_name, state, group_id, user_id, conversation_id)

设置开关状态。必须提供 `conversation_id`、`group_id` 或 `user_id` 中的一个。

```python
switch_manager.set_switch_state("ai_reply", False, group_id="group_123")
switch_manager.set_switch_state("image_to_text", True, conversation_id="qq:private:user_456")
```

### toggle_switch(switch_name, group_id, user_id, conversation_id)

翻转开关，返回新状态。

### get_switch_info(switch_name)

获取开关的配置信息（默认值、说明）。

### list_all_switches()

列出所有已注册的开关名称。

## 作用域解析

`_scope_from_conversation_id()` 从 `conversation_id` 解析出群组或用户 ID。格式：`qq:group:{group_id}` 或 `qq:private:{user_id}`。

```python
# "qq:group:123" → ("123", None)
# "qq:private:456" → (None, "456")
# "web:session_abc" → (None, None)  # 非 QQ 会话无作用域
```

路由逻辑：如果直接提供了 `conversation_id` 且有记录，优先使用；否则从 `conversation_id` 解析出群组/用户 ID 作为 fallback。

## 持久化

状态持久化到 `switches.json`：

```json
{
    "group_switches": {"group_123": {"ai_reply": false}},
    "user_switches": {"user_456": {"image_to_text": true}},
    "conversation_switches": {}
}
```

- `save_switches(file_path)` — 写入 JSON
- `load_switches(file_path)` — 读取 JSON，文件不存在时静默跳过

## 使用示例

```python
from nbot.core.switches import SwitchManager

sm = SwitchManager()
sm.load_switches()

sm.add_switch("ai_reply", True, "是否允许 AI 自动回复")

# 群组粒度
sm.set_switch_state("ai_reply", False, group_id="group_123")

# 会话粒度（覆盖群组设置）
sm.set_switch_state("ai_reply", True, conversation_id="qq:group:123:user:456")

# 查询
state = sm.get_switch_state("ai_reply", group_id="group_123")
```

## 设计原则

1. **三级粒度** - 会话 > 用户 > 群组，精细控制功能开关
2. **默认回退** - 未设置的开关使用注册时的默认值
3. **即时持久化** - 每次设置/切换后立即写入磁盘
4. **conversation_id 自解析** - 无需显式传入 group/user ID，从会话 ID 自动推导
