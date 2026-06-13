# failover - 模型故障转移

## 概述

`failover.py` 实现了 NekoBot 的模型故障转移与健康管理机制。当 AI 模型调用遇到可恢复的 HTTP 错误（429、5xx 等）时，自动切换到备用模型，并使用指数退避冷却避免对故障提供商的重复请求。

核心约束：本模块位于 `nbot/core/`，严禁引入 `nbot/web/` 或 `nbot/channels/`。

## 核心类

### ModelHealth

模型健康状态数据类，记录单模型的连续失败次数、冷却时间、每日失败计数。

```python
@dataclass
class ModelHealth:
    model_id: str
    consecutive_failures: int = 0        # 连续失败次数
    last_failure_at: float = 0.0
    last_failure_code: int = 0
    cooldown_until: float = 0.0
    daily_failures: int = 0              # 当日累计失败
    daily_failures_date: str = ""        # 记录日期 (YYYY-MM-DD)
```

### FailoverState

线程安全的故障转移队列管理器。按用途（purpose）维护多模型的健康状态，支持冷却期内自动跳过。

```
select_model(configs)      → 从有序列表中选出最佳可用模型
record_success(id)         → 重置连续失败计数
record_failure(id, code)   → 记录失败并计算冷却时间
is_available(id)           → 冷却是否已过期
get_all_health_summary()   → 所有模型健康快照
reset(model_id)            → 重置一个或全部模型状态
```

## 错误分类

### classify_http_error(status_code)

| 范围 | 类别 | 行为 |
|------|------|------|
| 400-499 | failover | 尝试下一个模型 |
| 500-599 | failover | 尝试下一个模型 |
| < 0（连接错误/超时） | transient | 短冷却后重试 |

### _compute_cooldown(consecutive_failures, status_code)

按错误类别使用不同的冷却参数，公式：`base * 2^(consecutive - 1)`，取上限。

| 类别 | 基础冷却 | 最大冷却 |
|------|----------|----------|
| rate_limit (429) | 60s | 300s |
| server (5xx) | 30s | 120s |
| bad_request (400) | 30s | 120s |
| transient | 15s | 60s |
| config | 0s | 0s |

## 持久化

健康状态持久化到 `failover_health.json`：

- 保存：使用原子写入（`.tmp` + `os.replace`），将 monotonic 时间转换为 wall-clock 时间
- 加载：wall-clock 转回 monotonic，已过期的冷却重置为 0
- 每日失败计数跨天自动重置

## 与 model_adapter 集成

`model_adapter.py` 在调用模型前调用 `get_failover_state().select_model(configs)` 选择可用模型。尝试失败后调用 `record_failure()` 使故障模型进入冷却，然后 `select_model()` 自动跳过该模型尝试下一个。

```python
from nbot.core.failover import get_failover_state

state = get_failover_state()
model = state.select_model(model_configs)

# 成功时
state.record_success(model["model_id"])

# 失败时
state.record_failure(model["model_id"], status_code=429)
```

## 单例

```python
from nbot.core.failover import get_failover_state, init_failover_state

# 全局访问
state = get_failover_state()

# 初始化持久化（启动时调用）
init_failover_state(data_dir="data/")
```

## 设计原则

1. **线程安全** - 所有状态操作通过 threading.Lock 保护
2. **优雅降级** - 全部不可用时返回第一个模型作为最后手段
3. **Token 限额感知** - 检查 `token_limit_daily` / `token_limit_weekly`，超限模型自动跳过
4. **故障隔离** - 单模型故障不影响其他模型的正常调用
