"""Gateway 统一异常类型"""


class GatewayError(Exception):
    """Gateway 基础异常"""

    def __init__(self, message: str, code: str = "gateway_error", status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class UnknownChannelError(GatewayError):
    """未注册的频道"""

    def __init__(self, channel_id: str):
        super().__init__(
            message=f"unknown channel: {channel_id}",
            code="unknown_channel",
            status_code=404,
        )
        self.channel_id = channel_id


class DisabledChannelError(GatewayError):
    """频道已禁用"""

    def __init__(self, channel_id: str):
        super().__init__(
            message=f"channel is disabled: {channel_id}",
            code="disabled_channel",
            status_code=403,
        )
        self.channel_id = channel_id


class SecurityVerificationError(GatewayError):
    """安全验证失败（签名/Token/时间戳等）"""

    def __init__(self, message: str, code: str = "security_error"):
        super().__init__(message=message, code=code, status_code=401)


class InvalidSignatureError(SecurityVerificationError):
    """HMAC 签名无效"""

    def __init__(self):
        super().__init__(message="invalid webhook signature", code="invalid_signature")


class InvalidTokenError(SecurityVerificationError):
    """Token 无效"""

    def __init__(self):
        super().__init__(message="invalid or missing token", code="invalid_token")


class TimestampExpiredError(SecurityVerificationError):
    """请求时间戳过期"""

    def __init__(self):
        super().__init__(message="request timestamp expired", code="timestamp_expired")


class ReplayDetectedError(SecurityVerificationError):
    """检测到重放攻击"""

    def __init__(self):
        super().__init__(message="replay request detected", code="replay_detected")


class RateLimitedError(GatewayError):
    """触发限流"""

    def __init__(self, message: str = "rate limit exceeded"):
        super().__init__(message=message, code="rate_limited", status_code=429)


class DuplicatedMessageError(GatewayError):
    """重复消息"""

    def __init__(self, message_id: str = ""):
        super().__init__(
            message=f"duplicated message: {message_id}" if message_id else "duplicated message",
            code="duplicated",
            status_code=200,
        )


class ParseFailedError(GatewayError):
    """平台事件解析失败"""

    def __init__(self, reason: str = "failed to parse event"):
        super().__init__(message=reason, code="parse_failed", status_code=400)


class DispatchFailedError(GatewayError):
    """AI Core 调度失败"""

    def __init__(self, reason: str = "dispatch to AI core failed"):
        super().__init__(message=reason, code="dispatch_failed", status_code=502)


class DeliveryFailedError(GatewayError):
    """回复投递失败"""

    def __init__(self, reason: str = "delivery failed"):
        super().__init__(message=reason, code="delivery_failed", status_code=502)
