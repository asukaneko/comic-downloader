# token_stats - Token 用量统计

## 概述

`token_stats.py` 提供线程安全的 AI Token 用量统计管理器。支持按会话、模型、用户多维度记录，自动计算费用，提供排行榜和历史查询。

## 数据结构

每条用量记录（record）包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | UUID 唯一标识 |
| `timestamp` | string | ISO 格式时间戳 |
| `date` | string | 日期 `YYYY-MM-DD` |
| `model` | string | 模型名称 |
| `session_id` | string | 会话 ID |
| `channel_type` | string | 频道类型 (`web` / `qq` / `qq_group`) |
| `user_id` | string | 用户标识 |
| `input` | int | 输入 Token 数 |
| `output` | int | 输出 Token 数 |
| `total` | int | 总 Token 数 |
| `cost` | float | 估算费用（美元） |
| `source` | string | 来源标识 |
| `duration_ms` | float | 响应耗时（毫秒，可选） |

## 模型定价

内置主流模型定价表（$/M tokens）：

| 模型 | 输入价格 | 输出价格 |
|------|----------|----------|
| claude-opus-4-7 | $15.0 | $75.0 |
| claude-sonnet-4-6 | $3.0 | $15.0 |
| claude-haiku-4-5 | $1.0 | $5.0 |
| gpt-4o | $2.5 | $10.0 |
| gpt-4o-mini | $0.15 | $0.60 |
| deepseek-v3 | $0.27 | $1.10 |
| deepseek-r1 | $0.55 | $2.19 |

未匹配的模型默认按 $1.0/$4.0 估算。

## 核心 API

### 初始化与单例

```python
from nbot.core.token_stats import init_token_stats_manager, get_token_stats_manager

# 服务启动时初始化
init_token_stats_manager(data_dir="data/web")

# 任意位置获取单例
manager = get_token_stats_manager()
```

### record_usage()

记录一次 AI 调用用量。所有频道（Web、QQ）的回调中自动调用。

```python
manager.record_usage(
    prompt_tokens=1500,         # 输入 Token
    completion_tokens=800,      # 输出 Token
    total_tokens=2300,          # 总 Token（可选，默认 prompt+completion）
    model="claude-sonnet-4-6",  # 模型名（用于定价匹配）
    session_id="abc123",        # 会话 ID
    channel_type="web",         # 频道类型
    user_id="user_001",         # 用户 ID
    source="web",               # 来源标识
    duration_ms=1234.5,         # 响应耗时 ms（可选）
)
```

::: info 自动调用点
- `WebCallbacks.on_usage()` → `_update_web_token_stats()` — Web 频道流式响应完成后
- `QQCallbacks.on_usage()` → 直接调用 — QQ 频道响应完成后
- source 参数用于区分 `web` / `qq` 来源
:::

### get_stats()

返回指定时间范围的统计数据。

```python
# 支持 "today" / "7d" / "30d" / "all"
stats = manager.get_stats(date_range="7d")

print(stats["total_tokens"])       # 总 Token
print(stats["message_count"])      # 消息数
print(stats["estimated_cost"])     # 估算费用
print(stats["avg_response_time"])  # 平均响应时间（秒）
print(stats["active_sessions"])    # 活跃会话数
print(stats["recent_records"])     # 最近 100 条记录
print(stats["history"])            # 每日汇总历史
```

返回字段说明：

| 字段 | 说明 |
|------|------|
| `today` | 今日总 Token（顶层聚合） |
| `month` | 本月总 Token |
| `total` | 全部历史总 Token |
| `total_tokens` | 所选范围总 Token |
| `today_input` | 所选范围输入 Token |
| `today_output` | 所选范围输出 Token |
| `message_count` | 所选范围消息数 |
| `avg_tokens_per_msg` | 平均每条消息 Token |
| `estimated_cost` | 估算费用（美元，字符串） |
| `active_sessions` | 活跃会话数 |
| `avg_response_time` | 平均响应时间（秒） |
| `history` | 每日汇总列表 |
| `recent_records` | 最近 100 条详细记录 |
| `sessions` | 会话维度统计 |
| `models` | 模型维度统计 |
| `users` | 用户维度统计 |

### get_rankings()

返回会话 / 模型 / 用户排行榜。

```python
rankings = manager.get_rankings(limit=10)

# 会话排行榜
for s in rankings["sessions"]:
    print(s["name"], s["value"], s["cost"])

# 模型排行榜（含 input/output/message_count/cost）
for m in rankings["models"]:
    print(m["name"], m["input"], m["output"], m["cost"])

# 用户排行榜
for u in rankings["users"]:
    print(u["name"], u["value"])
```

### 重置

```python
manager.reset_daily()   # 重置今日计数器
manager.reset_monthly() # 重置本月计数器
```

## 持久化

数据保存在 `{data_dir}/token_stats.json`，每次 `record_usage()` 后自动写入。文件结构：

```json
{
  "today": 0,
  "month": 0,
  "total": 0,
  "estimated_cost": 0.0,
  "history": [],
  "sessions": {},
  "models": {},
  "users": {},
  "records": []
}
```

- **history**: 每日汇总，自动合并同日重复条目，保留 90 天
- **records**: 详细调用记录，最多保留 5000 条（FIFO）
- **跨天/跨月**: 加载时自动检测并重置对应计数器

## 用量归一化

`model_adapter.py` 中的 `normalize_usage_dict()` 负责将不同提供商的 Token 字段统一为 OpenAI 命名：

```python
from nbot.core.model_adapter import normalize_usage_dict

# 任意格式的 usage → 标准格式
usage = normalize_usage_dict({
    "input_tokens": 100,         # Anthropic 风格
    "output_tokens": 50,
})
# → {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
```

支持的输入字段：

| 方向 | 识别的字段名 |
|------|-------------|
| 输入 | `prompt_tokens`, `input_tokens`, `prompt_token_count` |
| 输出 | `completion_tokens`, `output_tokens`, `completion_token_count`, `generated_tokens` |
| 总计 | `total_tokens`, `total_token_count` |
| 缓存 | `cached_tokens`, `prompt_tokens_details.cached_tokens` |
| 推理 | `reasoning_tokens`, `completion_tokens_details.reasoning_tokens` |

## 流式响应中的 Usage 提取

在 `_stream_to_web()` 中，每个 SSE chunk 如果包含 `usage` 字段，会通过 `normalize_usage_dict()` 归一化后 yield 出去：

```python
# ai_service.py: _stream_to_web()
data = json.loads(data_str)
usage = normalize_usage_dict(data.get("usage"))
if usage:
    yield {"usage": usage}
```

同时请求体默认携带 `stream_options: {"include_usage": True}`，如果提供商返回 400/422（不支持），会自动回退到不带 usage 选项的请求。
