# 限流模块

## 概述

限流模块保护 AI Core 免受过多请求冲击。Gateway 使用滑动窗口算法，在内存中维护四维独立的限流计数器。

## 限流维度

| 维度 | 键格式 | 默认限制 | 说明 |
|------|--------|----------|------|
| 单用户 | `user:{channel}:{user_id}` | 20 次/分钟 | 按用户 ID 统计 |
| 单会话 | `conv:{channel}:{conversation_id}` | 60 次/分钟 | 按会话 ID 统计 |
| 单 IP | `ip:{channel}:{remote_addr}` | 60 次/分钟 | 按请求来源 IP |
| 单频道 | `channel:{channel_id}` | 300 次/分钟 | 频道级别总量控制 |

## 滑动窗口算法

### SlidingWindowCounter

使用内存中的 `defaultdict[str, list]` 存储每个 key 的时间戳列表。窗口到期后自动清理过期条目。

```python
class SlidingWindowCounter:
    def __init__(self, window_seconds: int = 60):
        self._timestamps: dict[str, list] = defaultdict(list)

    def check_and_increment(self, key: str, limit: int) -> RateLimitResult:
        now = time.time()
        cutoff = now - self.window_seconds

        # 移除窗口外的时间戳
        timestamps = [t for t in self._timestamps[key] if t > cutoff]
        self._timestamps[key] = timestamps

        if len(timestamps) >= limit:
            return RateLimitResult(allowed=False, ...)

        timestamps.append(now)
        return RateLimitResult(allowed=True, ...)
```

### RateLimitResult

每次检查返回的结果包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `allowed` | bool | 是否允许通过 |
| `remaining` | int | 本周期剩余配额 |
| `reset_time` | float | 配额重置时间戳 |
| `limit` | int | 该维度上限 |
| `dimension` | str | 限流键 |

## 管线集成

限流在 Gateway 管线中被调用两次，分别在管线状态表中有不同的映射：

```
Step 2 — IP/频道维度限流  → status: rate_limited → stage: rate_limited
Step 5 — 用户/会话维度限流  → status: rate_limited → stage: rate_limited
```

```python
# Step 2: IP/频道维度
await self.rate_limiter.check(
    channel_id=channel_id,
    remote_addr=remote_addr,
)
# 此时尚未解析事件，只有 IP 和频道信息可用

# Step 5: 用户/会话维度
await self.rate_limiter.check(
    channel_id=channel_id,
    user_id=user_id,           # 从解析结果中提取
    conversation_id=conversation_id,  # 从解析结果中提取
    remote_addr=remote_addr,
)
```

任一维度触发限流时，`MemoryRateLimiter.check()` 抛出 `RateLimitedError`，Gateway 捕捉后立即返回 `GatewayResult(status="rate_limited")`，跳过后续处理。

## MemoryRateLimiter

多维度限流的编排入口：

```python
class MemoryRateLimiter:
    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig()
        self._windows: dict[int, SlidingWindowCounter] = {}

    async def check(
        self,
        *,
        channel_id: str,
        user_id: str = "",
        conversation_id: str = "",
        remote_addr: str = "",
    ) -> None:
        # 按顺序检查：user → conversation → ip → channel
        # 任一维度超限立即抛出 RateLimitedError
```

检查顺序为：用户 → 会话 → IP → 频道。优先拒绝恶意用户，再保护会话和频道整体稳定。

## RateLimiter 接口抽象

```python
class RateLimiter:
    """当前委托 MemoryRateLimiter，后续可替换为 Redis 实现"""

    def __init__(self, limiter: MemoryRateLimiter | None = None):
        self._limiter = limiter or MemoryRateLimiter()

    async def check(self, **kwargs) -> None:
        await self._limiter.check(**kwargs)
```

接口仅暴露 `check()` 方法，底层实现可插拔。后续版本可以替换为 Redis 滑动窗口实现以支持多实例部署。

## 配置限流

### 通过配置字典

```python
from nbot.gateway.rate_limit import MemoryRateLimiter, RateLimitConfig, RateLimiter

config = RateLimitConfig(
    per_user_per_minute=20,
    per_conversation_per_minute=60,
    per_ip_per_minute=60,
    per_channel_per_minute=300,
)
rate_limiter = RateLimiter(MemoryRateLimiter(config))
```

### 通过 `create_gateway_from_config`

```python
gateway = create_gateway_from_config({
    "gateway": {
        "rate_limit": {
            "per_user_per_minute": 10,
            "per_conversation_per_minute": 30,
            "per_ip_per_minute": 30,
            "per_channel_per_minute": 100,
        }
    }
})
```

### 通过 `.env` 环境变量

限流配置也可以通过 `.env` 文件注入，由应用层读取后传入 `RateLimitConfig`。

## 最佳实践

- **调低用户限制**：单人聊天机器人的场景，`per_user_per_minute` 设为 10-15 即可。
- **保持频道宽限**：群聊场景下 `per_channel_per_minute` 应足够容纳所有活跃用户的总和。
- **监控重置时间**：`RateLimitResult.reset_time` 可返回给客户端用于实现指数退避。
- **IP 限流兜底**：即便没有 `user_id` 的场景，IP 限流也能提供基础保护。
