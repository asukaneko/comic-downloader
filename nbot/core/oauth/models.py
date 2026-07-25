"""OAuth 数据模型定义。

从 Android 端 LocalOAuthModels.kt 1:1 移植：
- OAuthLoginMode: 4 种登录模式
- OAuthProviderSpec: provider 配置（id/title/protocol/base_url/models/...）
- LocalOAuthModelTarget: 模型运行时定位（protocol/base_url/max_context_length/max_tokens）
- OAuthLoginSession: 设备码/PKCE 登录会话
- OAuthPollResult: 轮询结果（Pending / Connected / Failed）
- OAuthRuntimeCredential: 运行时凭据（access_token + extra_headers + remove_headers）
- OAuthTokenState: 令牌状态（access_token / refresh_token / expires_at / ...）
- OAuthAccount: 已登录账号实体
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class OAuthLoginMode(str, Enum):
    """OAuth 登录模式"""

    DEVICE_CODE = "DEVICE_CODE"
    PKCE_CODE = "PKCE_CODE"
    QWEN_CREDENTIAL_IMPORT = "QWEN_CREDENTIAL_IMPORT"
    API_KEY = "API_KEY"


@dataclass
class OAuthProviderSpec:
    """OAuth 提供商配置"""

    id: str
    title: str
    subtitle: str
    login_mode: OAuthLoginMode
    protocol: str
    base_url: str
    models: list[str]
    default_context_length: int
    default_max_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "subtitle": self.subtitle,
            "login_mode": self.login_mode.value,
            "protocol": self.protocol,
            "base_url": self.base_url,
            "models": list(self.models),
            "default_context_length": self.default_context_length,
            "default_max_tokens": self.default_max_tokens,
        }


@dataclass
class LocalOAuthModelTarget:
    """单个模型在 OAuth provider 下的运行时定位（用于 OpenCode 模型族切换）"""

    protocol: str
    base_url: str
    max_context_length: int
    max_tokens: int


@dataclass
class OAuthLoginSession:
    """OAuth 登录会话（设备码 / PKCE 通用）"""

    id: str
    provider: str
    verification_url: str
    user_code: str = ""
    expires_at: int = 0  # 毫秒时间戳
    poll_interval_seconds: int = 3
    secret: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "verification_url": self.verification_url,
            "user_code": self.user_code,
            "expires_at": self.expires_at,
            "poll_interval_seconds": self.poll_interval_seconds,
            "secret": dict(self.secret),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OAuthLoginSession":
        return cls(
            id=data.get("id", ""),
            provider=data.get("provider", ""),
            verification_url=data.get("verification_url", ""),
            user_code=data.get("user_code", ""),
            expires_at=int(data.get("expires_at", 0) or 0),
            poll_interval_seconds=int(data.get("poll_interval_seconds", 3) or 3),
            secret=dict(data.get("secret") or {}),
        )


@dataclass
class OAuthRuntimeCredential:
    """运行时凭据：用于注入到 HTTP 请求"""

    access_token: str
    extra_headers: dict[str, str] = field(default_factory=dict)
    remove_headers: set[str] = field(default_factory=set)


@dataclass
class OAuthTokenState:
    """OAuth 令牌状态（持久化到 encrypted_credentials 字段）"""

    access_token: str = ""
    refresh_token: str = ""
    id_token: str = ""
    expires_at: Optional[int] = None  # 毫秒时间戳
    token_endpoint: str = ""
    client_id: str = ""
    portal_base_url: str = ""
    resource_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "id_token": self.id_token,
            "expires_at": self.expires_at,
            "token_endpoint": self.token_endpoint,
            "client_id": self.client_id,
            "portal_base_url": self.portal_base_url,
            "resource_url": self.resource_url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OAuthTokenState":
        if not isinstance(data, dict):
            return cls()
        return cls(
            access_token=data.get("access_token", "") or "",
            refresh_token=data.get("refresh_token", "") or "",
            id_token=data.get("id_token", "") or "",
            expires_at=data.get("expires_at"),
            token_endpoint=data.get("token_endpoint", "") or "",
            client_id=data.get("client_id", "") or "",
            portal_base_url=data.get("portal_base_url", "") or "",
            resource_url=data.get("resource_url", "") or "",
        )


@dataclass
class OAuthAccount:
    """已登录的 OAuth 账号"""

    id: str
    provider: str
    label: str
    encrypted_credentials: str  # OAuthTokenState 的 JSON 字符串（外层信封已加密）
    metadata_json: dict[str, Any] = field(default_factory=dict)
    status: str = "connected"
    expires_at: Optional[int] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "label": self.label,
            "encrypted_credentials": self.encrypted_credentials,
            "metadata_json": dict(self.metadata_json),
            "status": self.status,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OAuthAccount":
        return cls(
            id=data.get("id", ""),
            provider=data.get("provider", ""),
            label=data.get("label", ""),
            encrypted_credentials=data.get("encrypted_credentials", "") or "",
            metadata_json=dict(data.get("metadata_json") or {}),
            status=data.get("status", "connected") or "connected",
            expires_at=data.get("expires_at"),
            created_at=data.get("created_at", "") or "",
            updated_at=data.get("updated_at", "") or "",
        )


# ---------------------------------------------------------------------------
# OAuthPollResult: 用类层级模拟 sealed interface
# ---------------------------------------------------------------------------


class OAuthPollResult:
    """OAuth 轮询结果基类（模拟 Kotlin sealed interface）"""

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError


class OAuthPollPending(OAuthPollResult):
    """登录仍在等待用户授权"""

    def to_dict(self) -> dict[str, Any]:
        return {"status": "pending"}


@dataclass
class OAuthPollConnected(OAuthPollResult):
    """登录成功"""

    account: OAuthAccount
    models: list[str]

    def to_dict(self) -> dict[str, Any]:
        # 不返回 encrypted_credentials，避免敏感信息泄露
        safe_account = dict(self.account.to_dict())
        safe_account.pop("encrypted_credentials", None)
        return {
            "status": "connected",
            "account": safe_account,
            "models": list(self.models),
        }


@dataclass
class OAuthPollFailed(OAuthPollResult):
    """登录失败"""

    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": "failed", "message": self.message}
