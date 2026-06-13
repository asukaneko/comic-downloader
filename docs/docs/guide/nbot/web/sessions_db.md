# sessions_db - SQLite 会话存储

## 概述

`sessions_db.py` 提供基于 SQLite 的持久化会话存储层。所有 Web 会话的结构化数据（消息列表、元数据、角色配置等）均通过此模块写入 `sessions.db` 文件。相比 JSON 文件存储，SQLite 支持单条记录的原子更新，避免大规模重写。

## 数据库结构

```python
def _connect(data_dir: str) -> sqlite3.Connection:
    conn = sqlite3.connect(os.path.join(data_dir, "sessions.db"))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            data_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    return conn
```

`data_dir` 参数由 `WebServer` 实例初始化时传入，默认为 `data/web/`。

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | TEXT PRIMARY KEY | 会话唯一标识 |
| `data_json` | TEXT NOT NULL | 完整会话数据的 JSON 序列化 |
| `updated_at` | TEXT NOT NULL | 最后更新时间（ISO 8601） |

## CRUD 操作

### 读取全部会话

```python
from nbot.web.sessions_db import load_sessions

sessions = load_sessions(data_dir)
# 返回: { "session_id": { "name": "...", "messages": [...], ... }, ... }
```

全量加载会遍历 `sessions` 表所有行，将每行的 `data_json` 反序列化为字典。反序列化失败的记录被静默跳过。

### 读取单条会话

```python
from nbot.web.sessions_db import get_session

session = get_session(data_dir, "session_abc123")
if session:
    print(session["name"])
```

按 `session_id` 精确查找，不存在时返回 `None`。此函数在 Socket.IO 的 `join_session` 事件中被调用，用于在内存中未命中时从磁盘加载。

### 全量写入

```python
from nbot.web.sessions_db import save_sessions

save_sessions(data_dir, server.sessions)
# 先 DELETE 全表，再 INSERT 所有会话
```

```python
def save_sessions(data_dir: str, sessions: Dict[str, Dict[str, Any]]) -> None:
    now = datetime.now().isoformat()
    with _connect(data_dir) as conn:
        conn.execute("DELETE FROM sessions")
        payload = [
            (session_id, json.dumps(session, ensure_ascii=False), now)
            for session_id, session in sessions.items()
        ]
        if payload:
            conn.executemany(
                "INSERT INTO sessions (session_id, data_json, updated_at) VALUES (?, ?, ?)",
                payload,
            )
```

采用 **全量替换** 策略：先删除旧数据，再批量插入当前所有会话。这种方式确保了数据库与内存状态的一致性，适合会话数量适中的场景（通常数百个以内）。

### 单条更新

```python
from nbot.web.sessions_db import upsert_session

upsert_session(data_dir, "session_abc123", updated_session)
```

```python
def upsert_session(data_dir: str, session_id: str, session: Dict[str, Any]) -> None:
    now = datetime.now().isoformat()
    with _connect(data_dir) as conn:
        conn.execute(
            """
            INSERT INTO sessions (session_id, data_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                data_json = excluded.data_json,
                updated_at = excluded.updated_at
            """,
            (session_id, json.dumps(session, ensure_ascii=False), now),
        )
```

使用 SQLite 的 `ON CONFLICT ... DO UPDATE` 语法实现 upsert 语义。适用于单条会话变更后快速持久化，无需触发全量写操作。

## 调用链路

```
persistence.py (save_data)
    │
    ├─ data_type == "sessions"
    │   → 过滤 visible 会话
    │   → save_sessions(to_db)
    │
    ├─ data_type == "ai_config"
    │   → write_secure_json()  # 加密写入
    │
    └─ data_type == "ai_models"
        → write_secure_json()  # 加密写入

persistence.py (load_all_data)
    │
    └─ load_sessions() ← SQLite (主数据源)
       └─ _merge_session_sources()
           └─ _load_json_sessions() ← sessions.json (旧版兼容)
```

## 数据迁移

### JSON → SQLite

`load_all_data()` 中的合并逻辑：

```python
loaded_sessions = _merge_session_sources(
    load_sessions_from_db(server.data_dir),   # SQLite
    _load_json_sessions(server.data_dir),      # 旧版 sessions.json
)
```

- 如果 SQLite 已有数据，以 SQLite 为主，从 JSON 回填缺失的元数据字段（name、type、created_at 等）
- 如果 SQLite 为空（首次运行），从旧版 `sessions.json` 全量导入

### 清理重复

```python
normalized_sessions = _dedup_qq_sessions(normalized_sessions)
```

启动时自动合并重复的 QQ 会话（`qq_private_xxx` / `qq_group_xxx`），保留 canonical ID，合并消息列表并去重。

## 注意事项

- **全量保存性能**：每次 `save_sessions` 都会 DELETE + INSERT 全表，适合会话数 < 1000 的场景。大规模部署应考虑增量同步。
- **JSON 序列化**：`data_json` 使用 `ensure_ascii=False` 确保中文等 Unicode 字符正确保存。
- **数据一致性**：`persistence.py` 的 `save_data("sessions")` 在保存前会通过 `is_web_visible_session()` 过滤 CLI 专有会话，避免非 Web 数据写入 SQLite。
- **文件位置**：数据库文件位于 `{data_dir}/sessions.db`，与 `sessions.json`（旧版）同目录。
