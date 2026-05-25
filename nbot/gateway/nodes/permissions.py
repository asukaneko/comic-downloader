"""权限与 Scope 系统

定义 Gateway 控制面的权限模型：

Scope（权限范围）：
- 定义一个 Node 或连接可以执行的操作集合
- 采用最小权限原则
- 支持细粒度控制

权限层级：
  admin      → 完全管理权限（所有操作）
  gateway:write → 写入/修改 Gateway 配置
  gateway:read  → 读取 Gateway 状态
  channel:*     → 频道相关操作
  event:*       → 事件查询
  node:manage   → 节点管理
"""

import logging
from dataclasses import dataclass, field
from enum import StrEnum

_log = logging.getLogger(__name__)


class PermissionScope(StrEnum):
    """预定义的权限范围"""

    # 管理员
    ADMIN = "admin"

    # Gateway 操作
    GATEWAY_READ = "gateway:read"
    GATEWAY_WRITE = "gateway:write"
    GATEWAY_CONFIG = "gateway:config"

    # 事件操作
    EVENT_READ = "event:read"
    EVENT_QUERY = "event:query"
    EVENT_MANAGE = "event:manage"

    # 频道操作
    CHANNEL_READ = "channel:read"
    CHANNEL_WRITE = "channel:write"
    CHANNEL_MANAGE = "channel:manage"

    # 队列操作
    QUEUE_READ = "queue:read"
    QUEUE_MANAGE = "queue:manage"

    # Worker 操作
    WORKER_CONTROL = "worker:control"
    WORKER_STATUS = "worker:status"

    # 节点操作
    NODE_REGISTER = "node:register"
    NODE_MANAGE = "node:manage"
    NODE_VIEW = "node:view"


# 权限层级关系：高权限自动包含低权限
SCOPE_HIERARCHY: dict[str, list[str]] = {
    PermissionScope.ADMIN.value: [
        PermissionScope.GATEWAY_WRITE.value,
        PermissionScope.GATEWAY_CONFIG.value,
        PermissionScope.EVENT_MANAGE.value,
        PermissionScope.CHANNEL_MANAGE.value,
        PermissionScope.QUEUE_MANAGE.value,
        PermissionScope.WORKER_CONTROL.value,
        PermissionScope.NODE_MANAGE.value,
    ],
    PermissionScope.GATEWAY_WRITE.value: [
        PermissionScope.GATEWAY_READ.value,
    ],
    PermissionScope.GATEWAY_CONFIG.value: [
        PermissionScope.GATEWAY_READ.value,
    ],
    PermissionScope.EVENT_MANAGE.value: [
        PermissionScope.EVENT_READ.value,
        PermissionScope.EVENT_QUERY.value,
    ],
    PermissionScope.CHANNEL_MANAGE.value: [
        PermissionScope.CHANNEL_READ.value,
        PermissionScope.CHANNEL_WRITE.value,
    ],
    PermissionScope.QUEUE_MANAGE.value: [
        PermissionScope.QUEUE_READ.value,
    ],
    PermissionScope.WORKER_CONTROL.value: [
        PermissionScope.WORKER_STATUS.value,
    ],
    PermissionScope.NODE_MANAGE.value: [
        PermissionScope.NODE_VIEW.value,
        PermissionScope.NODE_REGISTER.value,
    ],
}


@dataclass
class TokenInfo:
    """访问令牌信息"""

    token_id: str = ""
    token_type: str = ""  # "node", "admin", "api_key"
    scopes: list[str] = field(default_factory=list)
    node_id: str = ""
    issued_at: float = 0.0
    expires_at: float | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        import time

        return time.time() > self.expires_at

    def has_scope(self, scope: str) -> bool:
        """检查是否拥有指定权限（含层级继承）"""
        if self.is_expired:
            return False
        if PermissionScope.ADMIN.value in self.scopes:
            return True
        if scope in self.scopes:
            return True
        # 检查是否有更高层级的权限包含此 scope
        for s in self.scopes:
            if scope in SCOPE_HIERARCHY.get(s, []):
                return True
        return False


class PermissionChecker:
    """权限检查器"""

    def __init__(self):
        self._tokens: dict[str, TokenInfo] = {}

    def issue_token(
        self,
        *,
        token_id: str,
        token_type: str = "api_key",
        scopes: list[str] | None = None,
        node_id: str = "",
        ttl_seconds: float | None = None,
    ) -> TokenInfo:
        """签发新令牌"""
        import time

        now = time.time()
        expires_at = (now + ttl_seconds) if ttl_seconds else None

        token_info = TokenInfo(
            token_id=token_id,
            token_type=token_type,
            scopes=scopes or [PermissionScope.GATEWAY_READ.value],
            node_id=node_id,
            issued_at=now,
            expires_at=expires_at,
        )
        self._tokens[token_id] = token_info
        _log.debug("[Permission] 签发令牌 type=%s scopes=%s", token_type, token_info.scopes)
        return token_info

    def revoke_token(self, token_id: str) -> bool:
        """撤销令牌"""
        if token_id in self._tokens:
            del self._tokens[token_id]
            return True
        return False

    def get_token(self, token_id: str) -> TokenInfo | None:
        return self._tokens.get(token_id)

    def check_permission(self, token_id: str, required_scope: str) -> bool:
        """检查令牌是否拥有所需权限"""
        token = self._tokens.get(token_id)
        if not token:
            return False
        return token.has_scope(required_scope)

    def validate_token(self, token_id: str) -> tuple[bool, TokenInfo | None]:
        """验证令牌有效性"""
        token = self._tokens.get(token_id)
        if not token:
            return False, None
        if token.is_expired:
            del self._tokens[token_id]
            return False, None
        return True, token

    def cleanup_expired(self) -> int:
        """清理过期令牌"""
        import time

        now = time.now()
        expired = [tid for tid, t in self._items.items() if t.expires_at and now > t.expires_at]
        for tid in expired:
            del self._tokens[tid]
        return len(expired)
