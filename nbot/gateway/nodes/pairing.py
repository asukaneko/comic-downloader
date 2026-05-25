"""节点配对流程

管理 Node 与 Gateway 之间的配对（Pairing）流程：

配对步骤：
1. Node 发起配对请求 → Gateway 返回 pairing_code
2. 管理员在控制台确认/拒绝
3. 确认后 Gateway 签发 token
4. Node 使用 token 完成注册

安全机制：
- 配对码一次性使用
- 配对请求有有效期
- 支持预授权白名单
"""

import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

_log = logging.getLogger(__name__)

# 配对码长度
_PAIRING_CODE_LENGTH = 8
# 默认有效期（秒）
_DEFAULT_TTL_SECONDS = 300


class PairingStatus(StrEnum):
    """配对状态"""

    PENDING = "pending"       # 等待管理员确认
    APPROVED = "approved"     # 已批准，等待 Node 完成
    REJECTED = "rejected"     # 已拒绝
    COMPLETED = "completed"   # 配对完成
    EXPIRED = "expired"       # 已过期


@dataclass
class PairingRequest:
    """配对请求"""

    request_id: str = ""
    node_id: str = ""
    node_type: str = ""
    pairing_code: str = ""
    status: str = PairingStatus.PENDING.value
    capabilities: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    created_at: float = 0.0
    approved_at: float | None = None
    expires_at: float | None = None
    approved_by: str = ""

    def __post_init__(self):
        if not self.request_id:
            import uuid

            self.request_id = f"pair_{uuid.uuid4().hex[:12]}"
        if not self.pairing_code:
            self.pairing_code = self._generate_code()
        if not self.created_at:
            self.created_at = time.time()
        if not self.expires_at:
            self.expires_at = time.time() + _DEFAULT_TTL_SECONDS

    @staticmethod
    def _generate_code() -> str:
        return secrets.token_urlsafe(_PAIRING_CODE_LENGTH)[:_PAIRING_CODE_LENGTH].upper()

    @property
    def is_expired(self) -> bool:
        if self.status == PairingStatus.EXPIRED.value:
            return True
        if self.expires_at and time.time() > self.expires_at:
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        caps_dict = None
        if self.capabilities and hasattr(self.capabilities, "to_dict"):
            caps_dict = self.capabilities.to_dict()

        return {
            "request_id": self.request_id,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "status": self.status,
            "capabilities": caps_dict,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "expires_at": self.expires_at or 0,
            "approved_by": self.approved_by or "",
        }


class PairingManager:
    """配对管理器"""

    def __init__(self, *, ttl_seconds: int = _DEFAULT_TTL_SECONDS):
        self._requests: dict[str, PairingRequest] = {}  # request_id → request
        self._code_index: dict[str, str] = {}  # pairing_code → request_id
        self._ttl_seconds = ttl_seconds
        self._total_requests = 0
        self._approved_callbacks: list[Callable[[PairingRequest], None]] = []
        self._rejected_callbacks: list[Callable[[PairingRequest], None]] = []

    def create_pairing_request(
        self,
        *,
        node_id: str,
        node_type: str = "worker",
        capabilities: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PairingRequest:
        """创建新的配对请求"""
        req = PairingRequest(
            node_id=node_id,
            node_type=node_type,
            capabilities=capabilities,
            metadata=metadata or {},
        )
        self._requests[req.request_id] = req
        self._code_index[req.pairing_code] = req.request_id
        self._total_requests += 1

        _log.info(
            "[Pairing] 创建配对请求 id=%s node=%s code=%s",
            req.request_id,
            node_id,
            req.pairing_code,
        )
        return req

    def get_request(self, request_id: str) -> PairingRequest | None:
        return self._requests.get(request_id)

    def find_by_code(self, code: str) -> PairingRequest | None:
        rid = self._code_index.get(code.upper())
        if rid:
            return self._requests.get(rid)
        return None

    def approve(self, request_id: str, approved_by: str = "") -> bool:
        """批准配对请求"""
        req = self._requests.get(request_id)
        if not req:
            return False
        if req.is_expired:
            req.status = PairingStatus.EXPIRED.value
            return False

        req.status = PairingStatus.APPROVED.value
        req.approved_at = time.time()
        req.approved_by = approved_by

        _log.info(
            "[Pairing] 批准配对 id=%s node=%s by=%s",
            request_id,
            req.node_id,
            approved_by or "system",
        )

        for cb in self._approved_callbacks:
            try:
                cb(req)
            except Exception as e:
                _log.error("[Pairing] 批准回调异常 error=%s", str(e))

        return True

    def reject(self, request_id: str, reason: str = "") -> bool:
        """拒绝配对请求"""
        req = self._requests.get(request_id)
        if not req:
            return False

        req.status = PairingStatus.REJECTED.value
        req.metadata["rejection_reason"] = reason

        _log.info(
            "[Pairing] 拒绝配对 id=%s node=%s reason=%s",
            request_id,
            req.node_id,
            reason,
        )

        for cb in self._rejected_callbacks:
            try:
                cb(req)
            except Exception as e:
                _log.error("[Pairing] 拒绝回调异常 error=%s", str(e))

        return True

    def complete(self, request_id: str) -> bool:
        """标记配对完成（Node 注册成功后调用）"""
        req = self._requests.get(request_id)
        if not req:
            return False
        req.status = PairingStatus.COMPLETED.value
        return True

    def list_pending(self) -> list[dict[str, Any]]:
        """列出待处理的配对请求"""
        now = time.time()
        pending = []
        for req in self._requests.values():
            if req.status == PairingStatus.PENDING.value:
                if req.expires_at and now > req.expires_at:
                    req.status = PairingStatus.EXPIRED.value
                else:
                    pending.append(req.to_dict())
        return pending

    def list_all(
        self,
        *,
        status: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """列出所有配对请求"""
        results = list(self._requests.values())
        if status:
            results = [r for r in results if r.status == status]
        results.sort(key=lambda r: r.created_at, reverse=True)
        return [r.to_dict() for r in results[:limit]]

    def cleanup_expired(self) -> int:
        """清理过期的配对请求"""
        now = time.time()
        expired = [
            (rid, req)
            for rid, req in self._requests.items()
            if req.expires_at and now > req.expires_at
            and req.status in (
                PairingStatus.PENDING.value,
                PairingStatus.APPROVED.value,
            )
        ]
        for _rid, req in expired:
            req.status = PairingStatus.EXPIRED.value
            code = req.pairing_code
            if code in self._code_index:
                del self._code_index[code]

        if expired:
            _log.debug("[Pairing] 清理过期请求 count=%d", len(expired))
        return len(expired)

    def on_approved(self, callback: Callable[[PairingRequest], None]) -> None:
        self._approved_callbacks.append(callback)

    def on_rejected(self, callback: Callable[[PairingRequest], None]) -> None:
        self._rejected_callbacks.append(callback)

    def get_stats(self) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        for req in self._requests.values():
            status_counts[req.status] = status_counts.get(req.status, 0) + 1

        return {
            "total_requests": self._total_requests,
            "active_requests": len(self._requests),
            "status_breakdown": status_counts,
            "pending_count": status_counts.get(PairingStatus.PENDING.value, 0),
            "ttl_seconds": self._ttl_seconds,
        }
