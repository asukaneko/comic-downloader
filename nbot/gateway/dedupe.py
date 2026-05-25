"""消息去重存储

防止 Webhook 重试导致重复回复。

去重 Key 格式：{channel_id}:{platform_message_id}

支持两种后端：
- MemoryDedupeStore: 内存实现（LRU + TTL），适合单实例
- SQLiteDedupeStore: SQLite 持久化，适合需要重启后仍能去重的场景
"""

import logging
import time
from collections import OrderedDict
from typing import TYPE_CHECKING

_log = logging.getLogger(__name__)

# 默认去重记录 TTL（秒），24 小时
_DEFAULT_TTL_SECONDS = 86400

# 内存中最大缓存条目数
_MAX_CACHE_SIZE = 10000

if TYPE_CHECKING:
    from nbot.gateway.storage import GatewayStorage


class MemoryDedupeStore:
    """基于内存的消息去重存储

    使用 OrderedDict 实现 LRU + TTL 过期机制。
    适合单实例部署场景。
    """

    def __init__(self, *, ttl_seconds: int = _DEFAULT_TTL_SECONDS, max_size: int = _MAX_CACHE_SIZE):
        self._ttl_seconds = ttl_seconds
        self._max_size = max_size
        # OrderedDict: key → (timestamp, ttl)
        self._store: OrderedDict[str, tuple] = OrderedDict()
        # 清理计数器，避免每次都全量扫描
        self._access_count = 0
        self._cleanup_threshold = 1000

    async def exists(self, key: str) -> bool:
        """检查消息是否已存在（即是否为重复消息）"""
        self._access_count += 1
        if self._access_count >= self._cleanup_threshold:
            self._cleanup_expired()

        entry = self._store.get(key)
        if entry is None:
            return False

        timestamp = entry[0]
        if time.time() - timestamp > entry[1]:
            del self._store[key]
            return False

        self._store.move_to_end(key)
        _log.debug("[Dedupe] 检测到重复消息 key=%s", key)
        return True

    async def mark(self, key: str, channel_id: str = "", message_id: str = "", ttl_seconds: int | None = None) -> None:
        """标记消息已处理"""
        ttl = ttl_seconds or self._ttl_seconds
        if key in self._store:
            self._store.move_to_end(key)
            self._store[key] = (time.time(), ttl)
            return
        while len(self._store) >= self._max_size:
            self._store.popitem(last=False)
        self._store[key] = (time.time(), ttl)
        _log.debug("[Dedupe] 标记消息 key=%s ttl=%ds", key, ttl)

    def _cleanup_expired(self) -> int:
        """清理已过期的条目"""
        now = time.time()
        expired_keys = [
            k for k, v in self._store.items() if now - v[0] > v[1]
        ]
        for k in expired_keys:
            del self._store[k]
        self._access_count = 0
        if expired_keys:
            _log.debug("[Dedupe] 清理过期条目 count=%d", len(expired_keys))
        return len(expired_keys)

    def size(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()


class SQLiteDedupeStore:
    """基于 SQLite 的持久化去重存储

    重启后仍能识别近期重复消息。
    通过 GatewayStorage 实现底层操作。
    """

    def __init__(self, storage: "GatewayStorage", *, default_ttl: int = _DEFAULT_TTL_SECONDS):
        self._storage = storage
        self._default_ttl = default_ttl

    async def exists(self, key: str) -> bool:
        """检查去重键是否存在（含过期检查）"""
        return self._storage.dedupe_exists(key)

    async def mark(
        self,
        key: str,
        channel_id: str = "",
        message_id: str = "",
        ttl_seconds: int | None = None,
    ) -> None:
        """标记消息已处理，写入 SQLite"""
        ttl = ttl_seconds or self._default_ttl
        self._storage.dedupe_mark(
            key=key,
            channel_id=channel_id,
            message_id=message_id,
            ttl_seconds=ttl,
        )

    def cleanup_expired(self) -> int:
        """清理过期记录"""
        return self._storage.dedupe_cleanup_expired()

    def count(self) -> int:
        return self._storage.dedupe_count()


class DedupeStore:
    """去重存储统一接口

    自动根据是否传入 storage 选择后端：
    - 有 storage → SQLiteDedupeStore（持久化）
    - 无 storage → MemoryDedupeStore（内存，默认）
    """

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
        self._backend_type = type(self._store).__name__

    async def exists(self, key: str) -> bool:
        return await self._store.exists(key)

    async def mark(self, key: str, channel_id: str = "", message_id: str = "", ttl_seconds: int | None = None) -> None:
        await self._store.mark(key, channel_id=channel_id, message_id=message_id, ttl_seconds=ttl_seconds)

    @property
    def backend_name(self) -> str:
        return self._backend_type

    @property
    def store(self) -> MemoryDedupeStore | SQLiteDedupeStore:
        return self._store
