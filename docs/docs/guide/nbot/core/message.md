# message - 消息管理

## 概述

`message.py` 定义了 NekoBot 的统一消息格式和消息管理器，提供 QQ 私聊、QQ 群聊和 Web 三种消息来源的 CRUD 操作。

## 核心数据类

### Message

统一的内部消息格式。

```python
@dataclass
class Message:
    id: str                          # UUID
    role: str                        # user / assistant / system
    content: str                     # 消息内容
    timestamp: str                   # ISO 格式时间戳
    sender: str                      # 发送者标识
    source: str                      # qq_private / qq_group / web
    session_id: str                  # 会话 ID
    attachments: List[Dict]          # 附件列表
    metadata: Dict                   # 扩展元数据
```

便捷构造方法：
- `Message.create_user_message(content, sender, source, session_id, attachments, metadata)`
- `Message.create_assistant_message(content, sender, source, session_id, metadata)`
- `Message.create_system_message(content)`
- `Message.from_dict(data)` / `to_dict()`

## 核心管理器

### MessageManager（单例）

三源消息管理：

```
MessageManager
├── qq_private/          # data/qq/private/{user_id}.json
│   ├── add_qq_private_message(user_id, message)
│   ├── get_qq_private_messages(user_id, limit)
│   └── clear_qq_private_messages(user_id)
├── qq_group/            # data/qq/group/{group_id}.json
│   ├── add_qq_group_message(group_id, message)
│   ├── get_qq_group_messages(group_id, limit)
│   └── clear_qq_group_messages(group_id)
└── web/                 # data/web/ (通过 sessions_db 持久化)
    ├── add_web_message(session_id, message)
    ├── get_web_messages(session_id, limit)
    └── clear_web_messages(session_id)
```

每个源存储独立的 JSON 文件。Web 消息复用现有的 `sessions_db` 机制，仅对 `is_web_visible_session()` 返回 True 的会话进行操作。

## 兼容接口

```python
add_message(source, target_id, role, content, **kwargs) → Dict
get_messages(source, target_id, limit) → List[Dict]
```

自动路由到对应的子管理器，用于逐步迁移的过渡期。

## 数据迁移

```python
message_manager.migrate_from_chat_service(user_messages, group_messages)
```

将旧版 `chat_service` 中的内存字典格式迁移到新的文件存储格式，跳过 system 角色消息。

## 全局实例与便捷函数

```python
from nbot.core.message import message_manager, add_message, get_messages
from nbot.core.message import create_message, migrate_messages

# 快捷方式
add_message("qq_group", "group_123", "user", "你好")
msgs = get_messages("qq_private", "user_456", limit=50)
```

## 设计原则

1. **三源统一** - QQ 私聊/群聊、Web 使用相同 Message 数据结构
2. **文件持久化** - 每条消息立即写入磁盘，避免内存丢失
3. **缓存加速** - 内存缓存 + 文件存储，读取时优先命中缓存
4. **向后兼容** - 旧接口在不破坏现有代码的前提下适配新架构
