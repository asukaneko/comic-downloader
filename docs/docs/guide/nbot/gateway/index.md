# gateway - 消息网关层

## 概述

`gateway` 是 NekoBot 的消息与能力边界层，统一多频道消息入口，解决认证、路由、去重、限流、日志、回复投递等横切关注点。支持同步/异步双模式、SQLite 持久化、事件总线和节点控制平面。

## 架构总览

```
外部消息 ──► Gateway.receive()
                │
                ├── 1. 安全验证 (Security)
                ├── 2. 限流检查 (RateLimiter)
                ├── 3. 路由适配器 (Router)
                ├── 4. 解析平台事件 (Adapter)
                ├── 5. 二次限流
                ├── 6. 消息去重 (Dedupe)
                │
                ├─[同步模式]──► 7. 构建 ChatRequest
                │               8. 分发到 AI Core
                │               9. 投递回复
                │
                └─[异步模式]──► 7. 入队 (Queue)
                                └─► Worker 后台处理 7-9 步

内部任务 ──► Gateway.submit_internal_task()
                │
                ├── 创建追踪链路
                ├── 记录 received/dispatched 事件
                ├── 执行 handler
                └── 记录 completed/failed 事件
```

## 核心类

### ChannelGateway

网关主类，协调所有子系统。

```python
from nbot.gateway.gateway import ChannelGateway, create_gateway_with_storage

# 创建带持久化的网关
gateway = create_gateway_with_storage(data_dir="data")

# 处理外部消息
result = await gateway.receive(
    channel_id="qq",
    raw_event={"message": "你好"},
    headers={"X-NekoBot-Token": "xxx"},
    remote_addr="127.0.0.1",
    raw_body=b'...',
)

# 提交内部任务
result = await gateway.submit_internal_task(
    task_kind="heartbeat",
    task_id="heartbeat",
    handler=my_handler,
    trigger_source="scheduler",
)
```

### 工厂函数

| 函数 | 说明 |
|------|------|
| `create_gateway()` | 基础同步网关 |
| `create_async_gateway()` | 异步模式网关 |
| `create_gateway_with_storage(data_dir)` | 同步 + SQLite 持久化 |
| `create_async_gateway_with_storage(data_dir)` | 异步 + 持久化 |
| `create_gateway_from_config(config)` | 从配置字典构建 |

### 全局单例

```python
from nbot.gateway.gateway import get_gateway, set_gateway

set_gateway(gateway)  # 注册
gw = get_gateway()    # 获取
```

## 子模块一览

| 模块 | 文件 | 职责 |
|------|------|------|
| [处理管线](./pipeline.md) | `gateway.py` | 同步/异步消息处理流程 |
| [安全认证](./security.md) | `security.py` | Token / HMAC / IP 白名单 |
| [限流与去重](./security.md#限流) | `rate_limit.py`, `dedupe.py` | 滑动窗口限流、消息去重 |
| [存储与追踪](./storage.md) | `storage.py`, `trace.py`, `logs/` | SQLite 持久化、统一日志、链路追踪 |
| [队列与投递](./delivery.md) | `queue.py`, `delivery.py`, `retry.py` | 事件队列、回复投递、重试 |
| [内部任务](./internal-tasks.md) | `gateway.py` | 心跳/工作流/定时任务追踪 |
| [节点控制平面](./nodes.md) | `nodes/` | 节点注册、心跳、配对、权限 |
| [服务门面](../mcp/index.md) | `facade.py` | 面向 MCP 的稳定服务接口 |

## 数据流

```text
┌─────────────┐     ┌───────────┐     ┌──────────┐     ┌──────────┐
│  QQ / Web /  │────►│  Gateway  │────►│ AI Core  │────►│  投递层   │
│  Telegram    │     │  (receive)│     │(dispatch)│     │(delivery)│
└─────────────┘     └───────────┘     └──────────┘     └──────────┘
                          │
                    ┌─────┴─────┐
                    │  Storage  │  SQLite: gateway_logs / deliveries / dedupe
                    └───────────┘
                          │
                    ┌─────┴─────┐
                    │  Facade   │  MCP / HTTP API / Web Console
                    └───────────┘
```

## Gateway Facade

`facade.py` 是面向 MCP 的服务门面层，将 Gateway 内部组件的能力整理成稳定的方法签名。MCP 工具层不直接操作 `gateway.storage`、`gateway.queue` 等细节，全部通过 Facade 调用。

```python
from nbot.gateway.facade import GatewayFacade

facade = GatewayFacade(gateway)

# 查询状态
status = await facade.get_status()

# 查询 trace 链路（聚合 events + deliveries + mcp_logs）
trace = await facade.query_trace("gw_...")

# 查询统一日志
logs = await facade.query_logs(source="gateway", status="delivered")

# ID 类型识别
result = await facade.lookup_id("gw_20260601_xxx")
```

详细用法参见 [MCP 文档](../mcp/index.md)。
