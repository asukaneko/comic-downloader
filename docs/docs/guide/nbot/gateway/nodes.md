# 节点控制平面

## 概述

Gateway 的节点控制平面提供节点注册、心跳监控、安全配对、权限管理和能力声明等功能，支持多节点分布式部署。

## 节点注册

### 节点类型与状态

**节点类型：**

| 类型 | 说明 |
|------|------|
| `gateway` | 网关节点 |
| `worker` | 工作节点 |
| `channel` | 频道节点 |

**节点状态：**

| 状态 | 说明 |
|------|------|
| `online` | 在线 |
| `busy` | 忙碌 |
| `idle` | 空闲 |
| `offline` | 离线 |
| `draining` | 排水中（不接受新任务） |

### 注册与查找

```python
from nbot.gateway.nodes.registry import NodeRegistry

registry = NodeRegistry()

# 注册节点
registry.register(node_id="gw-1", node_type="gateway", version="1.0.0")

# 查找最佳节点（优先空闲、低负载）
best = registry.find_best_node(node_type="worker")

# 健康检查（标记超时节点为 offline）
registry.check_health()
```

## 心跳管理

`HeartbeatManager` 接收节点心跳，更新注册表，检测离线节点。

```python
from nbot.gateway.nodes.heartbeat import HeartbeatManager, HeartbeatPayload

manager = HeartbeatManager(
    registry=registry,
    interval_seconds=30,     # 节点上报间隔
    timeout_seconds=120,     # 超时阈值
    check_interval=15,       # 检查间隔
)

# 心跳载荷
payload = HeartbeatPayload(
    node_id="gw-1",
    timestamp=datetime.now(),
    status="online",
    load=0.3,
    tasks_completed=100,
    tasks_failed=2,
)
```

## 节点配对

安全的一次性配对流程：

```
节点请求配对 → Gateway 生成 8 位一次性码 → 管理员审批 → 颁发 token
```

```python
from nbot.gateway.nodes.pairing import PairingManager

manager = PairingManager()

# 发起配对
request = manager.create_request(node_id="gw-2", node_type="worker")

# 审批
manager.approve(request.request_id)  # 颁发 token
# 或拒绝
manager.reject(request.request_id, reason="未授权节点")
```

**配对状态：**

| 状态 | 说明 |
|------|------|
| `PENDING` | 等待审批 |
| `APPROVED` | 已批准 |
| `REJECTED` | 已拒绝 |
| `COMPLETED` | 已完成（token 已颁发） |
| `EXPIRED` | 已过期（默认 300 秒） |

## 权限管理

### 权限范围（PermissionScope）

18 种权限，按类别分组：

| 类别 | 权限 |
|------|------|
| admin | `admin`（全部权限） |
| gateway | `gateway.manage`, `gateway.read` |
| events | `events.subscribe`, `events.query`, `events.publish` |
| channels | `channels.manage`, `channels.read`, `channels.send` |
| queue | `queue.manage`, `queue.read` |
| worker | `worker.manage`, `worker.read` |
| node | `node.register`, `node.heartbeat`, `node.manage`, `node.read` |

层级关系：`admin` 包含所有权限，`manage` 包含 `read` + `write`。

### Token 管理

```python
from nbot.gateway.nodes.permissions import PermissionChecker

checker = PermissionChecker()

# 颁发 token
token = checker.issue_token(
    token_type="node",
    scopes=["node.heartbeat", "events.subscribe"],
    node_id="gw-1",
)

# 验证权限
checker.check_permission(token.token_id, "events.subscribe")

# 撤销 token
checker.revoke_token(token.token_id)
```

## 能力声明

### 通道能力（ChannelCapability）

27 种能力，涵盖：

- **消息收发：** `webhook.receive`, `message.send`, `message.edit`, `message.delete`
- **富文本：** `rich_text`, `markdown`
- **媒体：** `image`, `file`, `voice`, `video`
- **互动：** `reactions`, `keyboards`
- **群组：** `group.manage`, `group.members`
- **会话：** `conversation.create`, `conversation.history`

### 工具能力（ToolCapability）

16 种能力，涵盖：

- 搜索、代码执行、计算器
- 图片生成、TTS/STT、翻译
- 天气/地图/新闻/股票
- 文件操作、数据库/知识库搜索

## WebSocket 控制面

### 客户端命令

| 命令 | 说明 |
|------|------|
| `node.register` | 注册节点 |
| `node.unregister` | 注销节点 |
| `node.heartbeat` | 上报心跳 |
| `gateway.stats` | 查询统计 |
| `gateway.health` | 健康检查 |
| `event.subscribe` | 订阅事件 |
| `event.unsubscribe` | 取消订阅 |
| `event.query` | 查询事件历史 |
| `pairing.create` | 发起配对 |
| `pairing.approve` | 审批配对 |
| `pairing.reject` | 拒绝配对 |
| `pairing.list` | 列出待审批 |

### 服务端推送

| 事件 | 说明 |
|------|------|
| `event.published` | 事件通知 |
| `node.online` | 节点上线 |
| `node.offline` | 节点离线 |
| `node.status_changed` | 节点状态变化 |
| `system.notification` | 系统通知 |
| `command.response` | 命令响应 |
| `error` | 错误通知 |

## 事件总线（EventBus）

内部发布/订阅总线，支持通配符匹配：

```python
from nbot.gateway.bus.event_bus import get_event_bus

bus = get_event_bus()

# 订阅（支持通配符）
@bus.on("event.received.*")
async def on_event(data):
    print(f"Event received: {data}")

# 一次性订阅
bus.once("node.online", lambda data: print("Node online!"))

# 查询历史
history = bus.query_history(
    topic="event.received",
    since=datetime.now() - timedelta(hours=1),
)
```

26 个预定义 topic，覆盖：网关生命周期、事件处理阶段、队列事件、Worker 事件、节点事件、安全事件。

## 错误体系

所有异常继承自 `GatewayError(message, code, status_code)`：

| 异常 | Code | HTTP |
|------|------|------|
| `UnknownChannelError` | `unknown_channel` | 404 |
| `DisabledChannelError` | `disabled_channel` | 403 |
| `SecurityVerificationError` | 可配置 | 401 |
| `InvalidSignatureError` | `invalid_signature` | 401 |
| `InvalidTokenError` | `invalid_token` | 401 |
| `TimestampExpiredError` | `timestamp_expired` | 401 |
| `ReplayDetectedError` | `replay_detected` | 401 |
| `RateLimitedError` | `rate_limited` | 429 |
| `DuplicatedMessageError` | `duplicated` | 200 |
| `ParseFailedError` | `parse_failed` | 400 |
| `DispatchFailedError` | `dispatch_failed` | 502 |
| `DeliveryFailedError` | `delivery_failed` | 502 |
