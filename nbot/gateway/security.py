"""Gateway 安全验证模块

支持多种鉴权策略：
- none:     不验证（本地调试用）
- static:   固定 Token 验证
- hmac:     HMAC-SHA256 签名验证
- ip:       IP 白名单验证

可组合使用，如 hmac + ip 白名单双重验证。
"""

import hashlib
import hmac
import logging
import time
from typing import Any

from nbot.gateway.errors import (
    InvalidSignatureError,
    InvalidTokenError,
    ReplayDetectedError,
    SecurityVerificationError,
    TimestampExpiredError,
)

_log = logging.getLogger(__name__)

# 默认时间戳有效期：5 分钟
DEFAULT_TIMESTAMP_TOLERANCE_SECONDS = 300


class SecurityProvider:
    """安全验证提供者

    统一处理 Token、HMAC 签名、时间戳、Nonce、IP 白名单等安全检查。
    """

    def __init__(
        self,
        *,
        mode: str = "none",
        token: str = "",
        secret: str = "",
        allowed_ips: list[str] | None = None,
        timestamp_tolerance: int = DEFAULT_TIMESTAMP_TOLERANCE_SECONDS,
    ):
        self.mode = mode
        self.token = token
        self.secret = secret
        self.allowed_ips = allowed_ips or []
        self.timestamp_tolerance = timestamp_tolerance
        # 已使用的 nonce 集合（防重放）
        self._used_nonces: set = set()

    async def verify(
        self,
        *,
        channel_id: str,
        raw_event: dict[str, Any],
        headers: dict[str, str],
        remote_addr: str = "",
    ) -> None:
        """执行完整的安全验证链

        按顺序执行：IP 白名单 → 时间戳 → Nonce → Token/HMAC 签名

        Raises:
            SecurityVerificationError: 验证失败时抛出对应子类异常
        """
        # IP 白名单检查
        self._check_ip_whitelist(remote_addr)

        # 根据模式选择验证方式
        if self.mode == "none":
            _log.debug("[Security] 跳过验证 mode=none channel_id=%s", channel_id)
            return

        if self.mode == "static":
            await self._verify_token(headers, channel_id)
            return

        if self.mode == "hmac":
            await self._verify_hmac(raw_event, headers, channel_id)
            return

        if self.mode == "ip":
            # 仅 IP 验证，上面已经检查过
            return

        raise SecurityVerificationError(f"unsupported security mode: {self.mode}")

    def _check_ip_whitelist(self, remote_addr: str) -> None:
        """IP 白名单检查"""
        if not self.allowed_ips:
            return
        if not remote_addr:
            raise SecurityVerificationError(
                "remote address required for IP whitelist",
                code="ip_required",
            )
        if remote_addr not in self.allowed_ips:
            _log.warning(
                "[Security] IP 不在白名单 addr=%s allowed=%s",
                remote_addr,
                self.allowed_ips,
            )
            raise SecurityVerificationError(
                f"IP not in whitelist: {remote_addr}",
                code="ip_forbidden",
                status_code=403,
            )

    async def _verify_token(self, headers: dict[str, str], channel_id: str) -> None:
        """静态 Token 验证

        从请求头 X-NekoBot-Token 中获取 Token 并比对。
        """
        if not self.token:
            _log.warning("[Security] Token 模式但未配置 token channel_id=%s", channel_id)
            return

        provided = headers.get("X-NekoBot-Token", "")
        if not provided:
            _log.warning("[Security] 缺少 Token header channel_id=%s", channel_id)
            raise InvalidTokenError()

        # 常量时间比较，防止时序攻击
        if not hmac.compare_digest(provided, self.token):
            _log.warning("[Security] Token 不匹配 channel_id=%s", channel_id)
            raise InvalidTokenError()

        _log.debug("[Security] Token 验证通过 channel_id=%s", channel_id)

    async def _verify_hmac(
        self,
        raw_event: dict[str, Any],
        headers: dict[str, str],
        channel_id: str,
    ) -> None:
        """HMAC-SHA256 签名验证

        验证流程：
        1. 检查时间戳是否在有效期内（默认 5 分钟）
        2. 检查 nonce 是否已被使用（防重放）
        3. 计算并比对 HMAC 签名

        签名计算方式：
            signing_payload = timestamp + "\\n" + nonce + "\\n" + raw_body
            signature = hex(hmac_sha256(secret, signing_payload))
        """
        if not self.secret:
            _log.warning("[Security] HMAC 模式但未配置 secret channel_id=%s", channel_id)
            return

        # 提取请求头字段
        timestamp_str = headers.get("X-NekoBot-Timestamp", "")
        nonce = headers.get("X-NekoBot-Nonce", "")
        signature = headers.get("X-NekoBot-Signature", "")

        # 时间戳校验
        if timestamp_str:
            try:
                ts = int(timestamp_str)
                now = int(time.time())
                if abs(now - ts) > self.timestamp_tolerance:
                    _log.warning(
                        "[Security] 时间戳过期 channel_id=%s diff=%ds",
                        channel_id,
                        abs(now - ts),
                    )
                    raise TimestampExpiredError()
            except (ValueError, TypeError) as err:
                _log.warning("[Security] 无效的时间戳格式 channel_id=%s", channel_id)
                raise TimestampExpiredError() from err

        # Nonce 防重放
        if nonce:
            if nonce in self._used_nonces:
                _log.warning("[Security] 重放检测 channel_id=%s nonce=%s", channel_id, nonce)
                raise ReplayDetectedError()
            self._used_nonces.add(nonce)

        # 签名校验
        if not signature:
            _log.warning("[Security] 缺少签名 header channel_id=%s", channel_id)
            raise InvalidSignatureError()

        # 构造签名字符串
        signing_payload = f"{timestamp_str}\n{nonce}\n"
        expected = hmac.new(
            self.secret.encode("utf-8"),
            signing_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            _log.warning("[Security] 签名不匹配 channel_id=%s", channel_id)
            raise InvalidSignatureError()

        _log.debug("[Security] HMAC 验证通过 channel_id=%s", channel_id)


def build_security_provider(channel_config: dict[str, Any] | None = None) -> SecurityProvider:
    """从频道配置构建 SecurityProvider

    Args:
        channel_config: 频道配置字典，包含 gateway.auth 配置

    Returns:
        配置好的 SecurityProvider 实例
    """
    config = dict(channel_config or {})
    gateway_config = config.get("gateway", {}) or {}
    auth_config = gateway_config.get("auth", {}) or {}

    mode = auth_config.get("type", "none")
    secret_ref = auth_config.get("secret_ref", "")

    # 从配置中获取 secret/token
    token = ""
    secret = ""
    if secret_ref:
        try:
            from nbot.web.secure_store import read_secure_json

            secure_data = read_secure_json() or {}
            secret = secure_data.get(secret_ref, "")
        except Exception:
            pass

    # 兼容直接配置的方式
    if not secret and auth_config.get("secret"):
        secret = auth_config["secret"]
    if auth_config.get("token"):
        token = auth_config["token"]

    allowed_ips = config.get("config", {}).get("allowed_ips") or []

    return SecurityProvider(
        mode=mode,
        token=token or secret,
        secret=secret,
        allowed_ips=allowed_ips,
    )
