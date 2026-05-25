"""限流模块

保护 AI Core 免受过多请求冲击。

限流维度：
- user_id:       单用户频率限制
- conversation_id: 单会话频率限制
- remote_addr:   单 IP 频率限制
- channel_id:    单频道总频率限制

第一版使用滑动窗口 + 内存实现。
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass

from nbot.gateway.errors import RateLimitedError

_log = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """限流配置"""

    per_user_per_minute: int = 20
    per_conversation_per_minute: int = 60
    per_ip_per_minute: int = 60
    per_channel_per_minute: int = 300
    window_seconds: int = 60


@dataclass
class RateLimitResult:
    """限流检查结果"""

    allowed: bool = True
    remaining: int = 0
    reset_time: float = 0.0
    limit: int = 0
    dimension: str = ""


class SlidingWindowCounter:
    """滑动窗口计数器

    用于在固定时间窗口内统计请求数量。
    """

    def __init__(self, window_seconds: int = 60):
        self.window_seconds = window_seconds
        # key → list of timestamps
        self._timestamps: dict[str, list] = defaultdict(list)

    def check_and_increment(
        self, key: str, limit: int
    ) -> RateLimitResult:
        """检查并递增计数

        Args:
            key: 限流键
            limit: 该维度的上限

        Returns:
            限流结果
        """
        now = time.time()
        cutoff = now - self.window_seconds

        # 清理过期的时间戳
        timestamps = self._timestamps.get(key, [])
        if timestamps:
            # 二分查找移除过期数据（简单实现用列表推导）
            self._timestamps[key] = [t for t in timestamps if t > cutoff]
            timestamps = self._timestamps[key]

        current_count = len(timestamps)

        if current_count >= limit:
            # 找到最早请求的过期时间作为重置时间
            reset_time = timestamps[0] + self.window_seconds if timestamps else now + self.window_seconds
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_time=reset_time,
                limit=limit,
                dimension=key,
            )

        # 记录本次请求
        timestamps.append(now)
        return RateLimitResult(
            allowed=True,
            remaining=limit - current_count - 1,
            reset_time=now + self.window_seconds,
            limit=limit,
            dimension=key,
        )


class MemoryRateLimiter:
    """基于内存的限流器

    支持多维度限流，使用滑动窗口算法。
    """

    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig()
        self._windows: dict[int, SlidingWindowCounter] = {}

    def _get_window(self, window_seconds: int) -> SlidingWindowCounter:
        if window_seconds not in self._windows:
            self._windows[window_seconds] = SlidingWindowCounter(window_seconds)
        return self._windows[window_seconds]

    async def check(
        self,
        *,
        channel_id: str,
        user_id: str = "",
        conversation_id: str = "",
        remote_addr: str = "",
    ) -> None:
        """执行多维度限流检查

        按优先级依次检查各维度，任一维度超限即抛出异常。

        Raises:
            RateLimitedError: 触发限流时抛出
        """
        cfg = self.config
        ws = cfg.window_seconds

        # 单用户限流
        if user_id:
            result = self._get_window(ws).check_and_increment(
                f"user:{channel_id}:{user_id}",
                cfg.per_user_per_minute,
            )
            if not result.allowed:
                _log.warning(
                    "[RateLimit] 用户限流 channel=%s user=%s limit=%d",
                    channel_id,
                    user_id,
                    cfg.per_user_per_minute,
                )
                raise RateLimitedError(
                    f"user rate limit exceeded: {cfg.per_user_per_minute}/min"
                )

        # 单会话限流
        if conversation_id:
            result = self._get_window(ws).check_and_increment(
                f"conv:{channel_id}:{conversation_id}",
                cfg.per_conversation_per_minute,
            )
            if not result.allowed:
                _log.warning(
                    "[RateLimit] 会话限流 channel=%s conv=%s limit=%d",
                    channel_id,
                    conversation_id,
                    cfg.per_conversation_per_minute,
                )
                raise RateLimitedError(
                    f"conversation rate limit exceeded: {cfg.per_conversation_per_minute}/min"
                )

        # 单 IP 限流
        if remote_addr:
            result = self._get_window(ws).check_and_increment(
                f"ip:{channel_id}:{remote_addr}",
                cfg.per_ip_per_minute,
            )
            if not result.allowed:
                _log.warning(
                    "[RateLimit] IP 限流 channel=%s ip=%s limit=%d",
                    channel_id,
                    remote_addr,
                    cfg.per_ip_per_minute,
                )
                raise RateLimitedError(
                    f"IP rate limit exceeded: {cfg.per_ip_per_minute}/min"
                )

        # 单频道总限流
        result = self._get_window(ws).check_and_increment(
            f"channel:{channel_id}",
            cfg.per_channel_per_minute,
        )
        if not result.allowed:
            _log.warning(
                "[RateLimit] 频道限流 channel=%s limit=%d",
                channel_id,
                cfg.per_channel_per_minute,
            )
            raise RateLimitedError(
                f"channel rate limit exceeded: {cfg.per_channel_per_minute}/min"
            )


class RateLimiter:
    """限流器接口抽象

    第一版委托给 MemoryRateLimiter，
    后续可替换为 Redis 限流实现。
    """

    def __init__(self, limiter: MemoryRateLimiter | None = None):
        self._limiter = limiter or MemoryRateLimiter()

    async def check(
        self,
        *,
        channel_id: str,
        user_id: str = "",
        conversation_id: str = "",
        remote_addr: str = "",
    ) -> None:
        await self._limiter.check(
            channel_id=channel_id,
            user_id=user_id,
            conversation_id=conversation_id,
            remote_addr=remote_addr,
        )
