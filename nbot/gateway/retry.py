"""Gateway 失败重试策略

处理 AI Core 调度和回复投递失败后的重试逻辑：

- 指数退避：每次重试等待时间逐渐增加（避免雪崩）
- 最大重试次数：超过后进入死信队列
- 可区分错误类型：可恢复错误重试，不可恢复错误直接死信
"""

import logging
import time
from dataclasses import dataclass
from enum import StrEnum

from nbot.gateway.queue import QueueItem

_log = logging.getLogger(__name__)


class ErrorCategory(StrEnum):
    """错误分类，决定是否值得重试"""

    RECOVERABLE = "recoverable"       # 可恢复：网络超时、AI 限流等
    NON_RECOVERABLE = "non_recoverable"  # 不可恢复：鉴权失败、频道不存在等
    UNKNOWN = "unknown"                  # 未知：按可恢复处理


@dataclass
class RetryPolicy:
    """重试策略配置"""

    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    jitter: bool = True  # 添加随机抖动，防止惊群效应


# 默认策略实例
DEFAULT_RETRY_POLICY = RetryPolicy()


def classify_error(error: Exception | str) -> ErrorCategory:
    """对错误进行分类

    Args:
        error: 异常实例或错误消息字符串

    Returns:
        错误分类
    """
    error_str = str(error).lower()

    # 明确不可恢复的错误
    non_recoverable_patterns = [
        "unknown_channel",
        "disabled_channel",
        "invalid_signature",
        "invalid_token",
        "timestamp_expired",
        "replay_detected",
        "missing_parser",
        "rate_limited",
        "duplicated",
        "permission_denied",
        "channel is disabled",
        "no parse_event",
    ]

    for pattern in non_recoverable_patterns:
        if pattern in error_str:
            return ErrorCategory.NON_RECOVERABLE

    # 可能可恢复的错误
    recoverable_patterns = [
        "timeout",
        "connection",
        "network",
        "rate limit",
        "429",
        "502",
        "503",
        "504",
        "ai core",
        "dispatch",
        "delivery",
        "sender error",
    ]

    for pattern in recoverable_patterns:
        if pattern in error_str:
            return ErrorCategory.RECOVERABLE

    return ErrorCategory.UNKNOWN


def calculate_backoff_delay(
    attempt: int,
    *,
    policy: RetryPolicy | None = None,
) -> float:
    """计算指数退避延迟时间

    公式：min(base_delay * 2^(attempt-1), max_delay) + jitter

    Args:
        attempt: 当前重试次数（从 1 开始）
        policy: 重试策略配置

    Returns:
        需要等待的秒数
    """
    p = policy or DEFAULT_RETRY_POLICY
    import random

    delay = min(p.base_delay_seconds * (2 ** (attempt - 1)), p.max_delay_seconds)

    if p.jitter:
        delay = delay * (0.5 + random.random() * 0.5)

    return delay


def should_retry(
    item: QueueItem,
    error: Exception | str = "",
    *,
    policy: RetryPolicy | None = None,
) -> tuple[bool, float | None]:
    """判断是否应该重试

    Args:
        item: 队列项
        error: 错误信息
        policy: 重试策略

    Returns:
        (是否应该重试, 下次重试时间/None)
    """
    p = policy or DEFAULT_RETRY_POLICY

    if item.attempt >= p.max_attempts:
        _log.debug(
            "[Retry] 达到最大重试次数 item=%s attempt=%d/%d",
            item.item_id,
            item.attempt,
            p.max_attempts,
        )
        return False, None

    category = classify_error(error)

    if category == ErrorCategory.NON_RECOVERABLE:
        _log.debug(
            "[Retry] 不可恢复错误，不重试 item=%s category=%s error=%s",
            item.item_id,
            category.value,
            error,
        )
        return False, None

    next_retry_at = time.time() + calculate_backoff_delay(item.attempt, policy=p)
    return True, next_retry_at


class RetryHandler:
    """重试处理器

    管理单个队列项的重试决策和状态更新。
    """

    def __init__(self, policy: RetryPolicy | None = None):
        self._policy = policy or DEFAULT_RETRY_POLICY

    def handle_failure(
        self,
        item: QueueItem,
        error: Exception | str = "",
    ) -> tuple[bool, float | None]:
        """处理失败事件，决定是否重试并更新状态

        Returns:
            (是否可以重试, 下次重试时间戳)
        """
        retry_ok, next_retry_at = should_retry(item, error, policy=self._policy)

        if retry_ok:
            _log.info(
                "[Retry] 将重试 item=%s trace=%s attempt=%d/%d next_retry_in=%.1fs",
                item.item_id,
                item.trace_id,
                item.attempt + 1,
                self._policy.max_attempts,
                (next_retry_at or 0) - time.time(),
            )

        return retry_ok, next_retry_at

    @property
    def max_attempts(self) -> int:
        return self._policy.max_attempts
