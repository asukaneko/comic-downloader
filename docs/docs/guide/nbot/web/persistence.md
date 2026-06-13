# persistence - 数据持久化层

## 概述

`persistence.py` 是 NekoBot Web 后台的数据持久化管理模块，负责加载、合并、规范化和保存所有业务数据。它统一管理 SQLite 会话、JSON 配置文件、加密存储和通道配置的完整生命周期。

## 数据目录结构

```
data/web/
├── sessions.db             # SQLite 会话存储（主数据源）
├── sessions.json           # 旧版 JSON 会话（迁移后不再写入）
├── settings.json           # Web 面板设置
├── ai_config.json          # AI 配置（加密存储）
├── ai_models.json          # 多模型配置（加密存储）
├── login_tokens.json       # 登录令牌（加密存储）
├── workflows.json          # 定时工作流配置
├── memories.json           # 记忆数据
├── system_logs.json        # 系统日志
├── heartbeat.json          # Heartbeat 配置
├── scheduled_tasks.json    # 定时任务
├── skills.json             # Skills 配置
├── tools.json              # Tools 配置
├── channels.json           # 频道配置
├── custom_personality_presets.json  # 自定义人格预设
└── secrets/                # 加密密钥目录
    └── secure_store.key    # Fernet 加密密钥
```

## 数据加载流程

```python
def load_all_data(server):
```

启动时依次执行以下步骤：

1. **会话加载与合并**
2. **会话规范化**
3. **QQ 会话去重**
4. **工作流加载**
5. **记忆数据加载**
6. **AI 配置加载（加密）**
7. **登录令牌加载（加密 + 自动迁移）**
8. **设置加载**
9. **多模型配置加载**
10. **Skills / Tools / Channels 配置加载**
11. **系统日志加载**
12. **Heartbeat 调度器初始化**

### 会话可见性过滤

```python
def is_web_visible_session(session_id, session):
    return not is_cli_session(session_id, session)
```

```python
def is_cli_session(session_id, session):
    if str(session_id or "").startswith("cli_"):
        return True
    session_type = str(session.get("type") or "").strip().lower()
    if session_type == "cli":
        return True
    for message in session.get("messages") or []:
        if str(message.get("source") or "").strip().lower() == "cli":
            return True
    return False
```

CLI 频道创建的会话（`cli_` 前缀、`type: cli` 或消息 `source: cli`）被自动过滤，不会暴露给 Web API 前端。

### 会话规范化

```python
def _normalize_session_record(session_id, session):
```

每条会话在加载后统一规范化，确保以下字段始终存在：

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `id` | session_id | 会话 ID |
| `name` | 首条用户消息前 24 字 | 会话名称 |
| `type` | `"web"` | 会话类型 |
| `created_at` | 首条消息时间戳 | 创建时间 |
| `archived` | `False` | 归档标记 |
| `system_prompt` | 首条 system 消息 | 系统提示词 |
| `favorite` / `pinned` / `is_public` | `False` | 状态标记 |

## 数据保存

```python
def save_data(server, data_type: str):
```

通过 `data_type` 参数路由到不同的存储后端：

| data_type | 存储方式 | 目标文件 |
|-----------|----------|----------|
| `sessions` | SQLite | `sessions.db` |
| `ai_config` | 加密 JSON | `ai_config.json` |
| `ai_models` | 加密 JSON | `ai_models.json` |
| `settings` | 普通 JSON | `settings.json` |
| `workflows` | 普通 JSON | `workflows.json` |
| `memories` | 普通 JSON | `memories.json` |
| `heartbeat` | 普通 JSON | `heartbeat.json` |
| `scheduled_tasks` | 普通 JSON | `scheduled_tasks.json` |
| `skills` | 普通 JSON | `skills.json` |
| `tools` | 普通 JSON | `tools.json` |
| `channels` | 普通 JSON | `channels.json` |
| `logs` | 普通 JSON | `system_logs.json` |
| `custom_personality_presets` | 普通 JSON | `custom_personality_presets.json` |
| `token_stats` | 委托 | TokenStatsManager 自行管理 |

### 会话保存

`save_data("sessions")` 在执行 SQLite 写入前，通过 `is_web_visible_session()` 过滤掉 CLI 会话，确保非 Web 数据不会污染 Web 存储。

## 默认数据初始化

```python
def init_default_data(server):
```

首次启动时无数据文件存在，通过此函数初始化默认配置，包括：

- 3 个示例工作流（早安问候、天气提醒、新闻推送）
- 默认 AI 配置（OpenAI 兼容，空 API Key）
- 默认系统设置（端口 5000、WS URI 等）
- 默认频道配置（Web + QQ 两个内置频道）

```python
def init_default_skills(server):
def init_default_tools(server):
```

Skills 和 Tools 的默认配置在首次运行时写入文件。Tools 默认包含 search_news、get_weather、search_web、get_date_time、http_get、exec_command 六个内置工具。

## 加密存储集成

AI 配置 (`ai_config.json`)、AI 模型 (`ai_models.json`) 和登录令牌 (`login_tokens.json`) 使用 `secure_store.py` 的 Fernet 加密：

```python
from nbot.web.secure_store import read_secure_json, write_secure_json

saved_config, was_plaintext = read_secure_json(ai_config_file, server.data_dir, {})
if was_plaintext:
    write_secure_json(ai_config_file, server.data_dir, saved_config)
```

自动检测旧版明文文件并升级为加密格式。

## 令牌迁移

```python
# 旧格式 key 长度 43（token_urlsafe(32)），新格式为 64（hex sha256）
if len(key) != 64:
    migrated[server._hash_token(key)] = value
```

启动时自动将旧版明文 Token 转换为 SHA-256 哈希 key，同时清理已过期的 Token。
