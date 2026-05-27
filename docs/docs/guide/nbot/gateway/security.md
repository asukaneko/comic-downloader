# 安全认证与限流

## 认证模式

Gateway 支持 4 种认证模式，通过配置选择：

```python
gateway = create_gateway_from_config({
    "security": {
        "mode": "hmac",          # none / static / hmac / ip
        "token": "your-secret",  # static 模式的固定 token
        "secret": "hmac-key",    # hmac 模式的签名密钥
        "ip_whitelist": ["127.0.0.1", "10.0.0.0/8"],
    }
})
```

### none — 无认证

调试模式，跳过所有验证。

### static — 静态 Token

通过 `X-NekoBot-Token` 请求头验证固定 token。

```bash
curl -H "X-NekoBot-Token: your-secret" http://localhost:5000/api/webhook/qq
```

### hmac — HMAC-SHA256 签名

使用 `timestamp + "\n" + nonce + raw_body` 作为签名载荷，支持时间戳 + nonce 防重放。

请求头要求：

| 请求头 | 说明 |
|--------|------|
| `X-NekoBot-Timestamp` | Unix 时间戳 |
| `X-Nonce` | 随机一次性值 |
| `X-Signature` | HMAC-SHA256 签名（hex） |

签名验证使用 `hmac.compare_digest` 进行常量时间比较，防止时序攻击。nonce 基于 TTL 自动清理，防止内存增长。

### ip — IP 白名单

仅允许指定 IP 或 CIDR 段访问。所有其他模式也可叠加 IP 白名单。

## 限流

滑动窗口算法，4 个维度按顺序检查：

| 维度 | 默认限制 | 说明 |
|------|---------|------|
| 用户/分钟 | 20 | 单个用户消息频率 |
| 会话/分钟 | 60 | 单个会话消息频率 |
| IP/分钟 | 60 | 单个 IP 请求频率 |
| 通道/分钟 | 300 | 单个通道总请求频率 |

```python
from nbot.gateway.rate_limit import RateLimitConfig

config = RateLimitConfig(
    per_user_per_minute=20,
    per_conversation_per_minute=60,
    per_ip_per_minute=60,
    per_channel_per_minute=300,
)
```

超限时返回 `RateLimitedError`（HTTP 429）。

## 消息去重

两种后端可选：

| 后端 | 说明 | 适用场景 |
|------|------|---------|
| `MemoryDedupeStore` | LRU + TTL（默认 24h，最大 10000 条） | 单实例部署 |
| `SQLiteDedupeStore` | 持久化到 SQLite，重启后保留 | 多次重启场景 |

去重基于 `channel_id + message_id` 生成的 key。重复消息返回 `DuplicatedMessageError`（HTTP 200，`duplicated=True`）。

```python
from nbot.gateway.dedupe import DedupeStore

# 自动根据是否有 storage 选择后端
store = DedupeStore(storage=gateway.storage)
```
