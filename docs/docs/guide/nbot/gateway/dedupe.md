# 消息去重

## 概述

消息去重防止 Webhook 重试、平台重复推送等场景下 AI Core 对同一条消息重复回复。去重键格式为 `{channel_id}:{platform_message_id}`。

## 去重键生成

由 Gateway 在步骤 6 从适配器解析结果中提取：

```python
def _extract_message_id(self, channel_id: str, parsed: dict[str, Any]) -> str:
    metadata = parsed.get("metadata") or {}
    raw_id = (
        metadata.get("message_id")
        or metadata.get(f"{channel_id}_message_id")
        or parsed.get("message_id")
    )
    return f"{channel_id}:{raw_id}" if raw_id else ""
```

优先级：`metadata.message_id` → `metadata.{channel}_message_id` → `parsed.message_id`。

## 去重范围

去重作用在管道步骤 6：

```
Step 6 → dedupe_store.exists(key)
           ├── 存在且未过期 → status: duplicated → 直接返回（不处理）
           └── 不存在或已过期 → status: deduped → 继续处理
```

去重标记（`dedupe_store.mark()`）在同步模式下仅在 `delivered` 或 `built` 之后才写入，确保只有真正成功处理的消息被标记。

```
同步模式：
  dispatch + delivery 成功 → dedupe_store.mark(key)

异步模式：
  Worker dequeue + dispatch + delivery 成功 → dedupe_store.mark(key)
```

## 双后端架构

### MemoryDedupeStore（默认）

基于 `OrderedDict` 实现 LRU + TTL 过期。适合单实例部署。

```python
class MemoryDedupeStore:
    def __init__(self, *, ttl_seconds: int = 86400, max_size: int = 10000):
        self._store: OrderedDict[str, tuple] = OrderedDict()
```

关键参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ttl_seconds` | 86400（24 小时） | 去重记录的存活时间 |
| `max_size` | 10000 | 最大缓存条目数，超出后淘汰最旧的 |

过期清理机制：

- 每次 `exists()` 调用检查过期条目
- 每 1000 次访问触发一次全量清理
- 使用 `popitem(last=False)` 淘汰最旧条目

### SQLiteDedupeStore（持久化）

当 Gateway 配置了持久化存储时自动启用。进程重启后仍能识别近期重复消息。

```python
class SQLiteDedupeStore:
    def __init__(self, storage: "GatewayStorage", *, default_ttl: int = 86400):
        self._storage = storage
```

底层存储表 `gateway_dedupe`：

```sql
CREATE TABLE IF NOT EXISTS gateway_dedupe (
    dedupe_key TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT
);
```

- `dedupe_key` 为主键，支持 `INSERT ... ON CONFLICT DO UPDATE`
- `expires_at` 列用于过期检查和清理
- 自动创建索引 `idx_gateway_dedupe_expires`

### DedupeStore 统一接口

根据构造时是否传入 `storage` 自动选择后端：

```python
class DedupeStore:
    def __init__(
        self,
        store: MemoryDedupeStore | SQLiteDedupeStore | None = None,
        storage: "GatewayStorage | None" = None,
    ):
        if store:
            self._store = store
        elif storage:
            self._store = SQLiteDedupeStore(storage)
        else:
            self._store = MemoryDedupeStore()
```

方法：

| 方法 | 说明 |
|------|------|
| `exists(key)` | 检查消息是否已处理（含过期检查） |
| `mark(key, channel_id, message_id, ttl_seconds)` | 标记消息已处理 |
| `backend_name` | 返回当前后端类型名称 |

## TTL 配置

默认 TTL 为 24 小时（86400 秒），可通过以下方式修改：

```python
# 内存后端
store = MemoryDedupeStore(ttl_seconds=3600)  # 1 小时

# SQLite 后端
store = SQLiteDedupeStore(storage, default_ttl=3600)

# 单条消息覆盖 TTL
await dedupe_store.mark(key, channel_id="qq", message_id="123", ttl_seconds=300)
```

持久化后端支持定期清理过期记录：

```python
storage.dedupe_cleanup_expired()  # 返回清理条数
```

## 配置示例

```python
from nbot.gateway.dedupe import DedupeStore, MemoryDedupeStore

# 完全使用默认值
dedupe_store = DedupeStore()

# 自定义内存后端
dedupe_store = DedupeStore(
    store=MemoryDedupeStore(ttl_seconds=7200, max_size=5000)
)

# 启用持久化去重（通过 Gateway 构造自动切换）
gateway = create_gateway_with_storage(data_dir="data")
# gateway.dedupe_store 自动为 SQLiteDedupeStore
```

## 最佳实践

- **持久化去重**：生产环境建议使用 `create_gateway_with_storage()`，这样进程重启后不会重复回复重启前已处理的消息。
- **TTL 调整**：如果平台的 Webhook 重试窗口较短（如 5 分钟），可将 TTL 缩短至 1 小时以减少存储占用。
- **消息 ID 唯一性**：确保上游平台推送的 `message_id` 具有全局唯一性，否则去重键可能发生误碰撞。
