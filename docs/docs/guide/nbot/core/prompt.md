# prompt - 提示词管理

## 概述

`prompt.py` 提供统一的提示词加载和管理功能，支持用户/群组专属提示词、记忆管理、工具列表组装等。

## 核心类

### PromptManager（单例）

```python
class PromptManager:
    def load_base_prompt(self, user_id=None, group_id=None) -> str
    def load_memories(self, user_id=None, group_id=None, character_name=None) -> str
    def load_tools_prompt(self) -> str
    def load_prompt(self, ...) -> str
    def save_prompt(self, content, user_id=None, group_id=None) -> bool
    def add_memory(self, title, content, target_id, ...) -> bool
    def delete_memory(self, memory_id) -> bool
    def update_memory(self, memory_id, updates) -> bool
    def clear_memories(self, target_id=None) -> bool
    def get_memories(self, target_id=None, mem_type=None, character_name=None) -> List[Dict]
```

## 提示词加载

### load_base_prompt(user_id, group_id)

加载优先级：
1. `resources/prompts/user/user_{user_id}.txt` — 用户专属
2. `resources/prompts/group/group_{group_id}.txt` — 群组专属
3. `resources/prompts/neko.txt` — 默认提示词
4. `resources/prompts/personality.json` 中的 `systemPrompt` — 角色卡提示词
5. 空字符串

### load_prompt(user_id, group_id, include_memories, include_tools)

组装完整提示词：基础提示词 + 记忆 + 工具列表。

```python
prompt = prompt_manager.load_prompt(user_id="123", group_id=None)
# → "基础提示词\n\n【重要记忆】\n...\n\n## 可用工具\n..."
```

## 记忆管理

记忆存储在 `data/memories.json`，支持自动过期清理。

### 添加记忆

```python
prompt_manager.add_memory(
    title="用户喜好",
    content="用户喜欢喝美式咖啡，每周去星巴克3次",
    target_id="user_123",
    summary="喜欢美式咖啡",
    mem_type="long",        # long / short
    expire_days=7,          # 短期记忆过期天数
    character_name="neko"   # 角色名，支持多角色记忆隔离
)
```

### 记忆格式

每条记忆包含：`id`, `title`, `summary`, `content`, `target_id`, `type`, `expire_days`, `created_at`, `character_name`（可选）。

### 过期清理

短期记忆（`type == "short"`）会自动检查 `created_at` 是否超过 `expire_days`，过期记忆在 `_cleanup_expired()` 中移除并持久化。

### 筛选查询

```python
# 按目标/类型/角色名筛选
memories = prompt_manager.get_memories(
    target_id="user_123",
    mem_type="long",
    character_name="neko"
)
```

## 工具提示词

`load_tools_prompt()` 通过 `get_enabled_tools()` 获取启用的工具列表，组装为 markdown 格式的提示词，包含工作区工具和命令执行工具的描述。工具列表通常由角色卡配置决定。

## 全局实例与便捷函数

```python
from nbot.core.prompt import prompt_manager
from nbot.core.prompt import load_prompt, load_memories, add_memory
from nbot.core.prompt import delete_memory, clear_memories, save_prompt

# 便捷用法
load_prompt(user_id="123")               # 等同 prompt_manager.load_prompt()
add_memory("标题", "内容", "user_123")    # 等同 prompt_manager.add_memory()
```

## 设计原则

1. **分层加载** - 用户 > 群组 > 默认 > 角色卡，逐级回退
2. **自动过期** - 短期记忆自动过期，无需手动清理
3. **格式迁移** - 自动检测旧格式（key/value）并迁移到新格式（title/summary/content）
4. **多角色隔离** - 通过 `character_name` 字段支持同一用户的多个角色记忆
