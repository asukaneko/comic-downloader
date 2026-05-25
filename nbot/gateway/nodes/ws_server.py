"""WebSocket 控制面服务

提供 WebSocket 接口供外部节点连接和控制 Gateway：

支持的命令（从 Client → Server）：
  - node.register      节点注册
  - node.unregister    节点注销
  - node.heartbeat     心跳上报
  - gateway.stats      查询统计
  - gateway.config     查询配置
  - event.subscribe    订阅事件
  - event.query        查询事件历史
  - pairing.create     发起配对
  - pairing.approve    批准配对（需 admin 权限）

服务端推送（Server → Client）：
  - event.published    事件通知
  - node.status_changed 节点状态变更
  - system.notification 系统通知
  - command.response   命令响应
"""

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

_log = logging.getLogger(__name__)


class WSCommand(StrEnum):
    """WebSocket 命令类型"""

    # 节点管理
    NODE_REGISTER = "node.register"
    NODE_UNREGISTER = "node.unregister"
    NODE_HEARTBEAT = "node.heartbeat"

    # Gateway 查询
    GATEWAY_STATS = "gateway.stats"
    GATEWAY_HEALTH = "gateway.health"
    QUEUE_STATUS = "queue.status"
    WORKER_STATUS = "worker.status"

    # 事件操作
    EVENT_SUBSCRIBE = "event.subscribe"
    EVENT_UNSUBSCRIBE = "event.unsubscribe"
    EVENT_QUERY = "event.query"

    # 配对
    PAIRING_CREATE = "pairing.create"
    PAIRING_APPROVE = "pairing.approve"
    PAIRING_REJECT = "pairing.reject"
    PAIRING_LIST = "pairing.list"


class WSEventType(StrEnum):
    """WebSocket 推送事件类型"""

    EVENT_PUBLISHED = "event.published"
    NODE_ONLINE = "node.online"
    NODE_OFFLINE = "node.offline"
    NODE_STATUS_CHANGED = "node.status_changed"
    SYSTEM_NOTIFICATION = "system.notification"
    COMMAND_RESPONSE = "command.response"
    ERROR = "error"


@dataclass
class WSMessage:
    """WebSocket 消息格式"""

    type: str = ""          # command 或 event
    command: str = ""       # 命令类型
    event: str = ""         # 事件类型
    payload: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""    # 请求 ID（用于匹配响应）
    timestamp: float = 0.0
    source: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_json(self) -> str:
        return json.dumps({
            "type": self.type,
            "command": self.command,
            "event": self.event,
            "payload": self.payload,
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "source": self.source,
        }, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "WSMessage":
        try:
            data = json.loads(raw)
            return cls(**data)
        except (json.JSONDecodeError, TypeError):
            return cls(type="error", payload={"raw": raw})


@dataclass
class WSConnection:
    """WebSocket 连接信息"""

    conn_id: str = ""
    node_id: str = ""
    connected_at: float = 0.0
    last_activity: float = 0.0
    subscriptions: set[str] = field(default_factory=set)
    authenticated: bool = False
    scopes: list[str] = field(default_factory=list)


class ControlPlaneServer:
    """控制面 WebSocket 服务器

    注意：这是一个抽象层，不直接绑定具体的 WebSocket 库。
    集成时需要适配到具体框架（如 Flask-SocketIO、aiohttp 等）。
    """

    def __init__(
        self,
        *,
        event_bus=None,
        node_registry=None,
        heartbeat_manager=None,
        pairing_manager=None,
        permission_checker=None,
    ):
        from nbot.gateway.bus.event_bus import EventBus, get_event_bus
        from nbot.gateway.nodes.heartbeat import HeartbeatManager
        from nbot.gateway.nodes.pairing import PairingManager
        from nbot.gateway.nodes.permissions import PermissionChecker
        from nbot.gateway.nodes.registry import NodeRegistry

        self._event_bus: EventBus = event_bus or get_event_bus()
        self._registry: NodeRegistry = node_registry or NodeRegistry()
        self._heartbeat: HeartbeatManager = heartbeat_manager or HeartbeatManager(self._registry)
        self._pairing: PairingManager = pairing_manager or PairingManager()
        self._permissions: PermissionChecker = permission_checker or PermissionChecker()

        self._connections: dict[str, WSConnection] = {}
        self._conn_by_node: dict[str, str] = {}  # node_id → conn_id
        self._handlers: dict[str, Callable] = {}
        self._running = False

        # 注册默认命令处理器
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """注册内置命令处理器"""
        self.register_handler(WSCommand.NODE_REGISTER.value, self._handle_register)
        self.register_handler(WSCommand.NODE_UNREGISTER.value, self._handle_unregister)
        self.register_handler(WSCommand.NODE_HEARTBEAT.value, self._handle_heartbeat)
        self.register_handler(WSCommand.GATEWAY_STATS.value, self._handle_stats)
        self.register_handler(WSCommand.GATEWAY_HEALTH.value, self._handle_health)
        self.register_handler(WSCommand.EVENT_SUBSCRIBE.value, self._handle_subscribe)
        self.register_handler(WSCommand.EVENT_QUERY.value, self._handle_event_query)
        self.register_handler(WSCommand.PAIRING_CREATE.value, self._handle_pairing_create)
        self.register_handler(WSCommand.PAIRING_LIST.value, self._handle_pairing_list)

    def register_handler(self, command: str, handler: Callable) -> None:
        """注册自定义命令处理器"""
        self._handlers[command] = handler
        _log.debug("[ControlPlane] 注册命令处理器 cmd=%s", command)

    async def on_connect(self, conn_id: str) -> WSMessage:
        """处理新连接"""
        conn = WSConnection(conn_id=conn_id, connected_at=time.time(), last_activity=time.time())
        self._connections[conn_id] = conn

        _log.info("[ControlPlane] 新连接 conn=%s", conn_id)

        return WSMessage(
            type="event",
            event=WSEventType.SYSTEM_NOTIFICATION.value,
            payload={
                "message": "connected",
                "conn_id": conn_id,
            },
            source="server",
        )

    async def on_message(self, conn_id: str, raw_message: str) -> WSMessage | None:
        """处理收到的消息"""
        conn = self._connections.get(conn_id)
        if not conn:
            return None

        conn.last_activity = time.time()

        try:
            msg = WSMessage.from_json(raw_message)
        except Exception:
            return WSMessage(
                type="event",
                event=WSEventType.ERROR.value,
                payload={"error": "invalid message format"},
                request_id=msg.request_id if 'msg' in dir() else "",
                source="server",
            )

        if msg.type != "command":
            return None

        handler = self._handlers.get(msg.command)
        if not handler:
            return WSMessage(
                type="event",
                event=WSEventType.COMMAND_RESPONSE.value,
                payload={"ok": False, "error": f"unknown command: {msg.command}"},
                request_id=msg.request_id,
                source="server",
            )

        try:
            response = await handler(conn, msg)
            if response is None:
                response = WSMessage(
                    type="event",
                    event=WSEventType.COMMAND_RESPONSE.value,
                    payload={"ok": True},
                    request_id=msg.request_id,
                    source="server",
                )
            elif not isinstance(response, WSMessage):
                response = WSMessage(
                    type="event",
                    event=WSEventType.COMMAND_RESPONSE.value,
                    payload={"ok": True, "data": response},
                    request_id=msg.request_id,
                    source="server",
                )
            else:
                response.request_id = msg.request_id
                response.source = "server"
            return response
        except Exception as e:
            _log.error(
                "[ControlPlane] 命令处理异常 cmd=%s error=%s", msg.command, str(e)
            )
            return WSMessage(
                type="event",
                event=WSEventType.COMMAND_RESPONSE.value,
                payload={"ok": False, "error": str(e)},
                request_id=msg.request_id,
                source="server",
            )

    async def on_disconnect(self, conn_id: str) -> None:
        """处理断开连接"""
        conn = self._connections.pop(conn_id, None)
        if conn and conn.node_id:
            self._conn_by_node.pop(conn.node_id, None)
            _log.info(
                "[ControlPlane] 连接断开 conn=%s node=%s",
                conn_id,
                conn.node_id,
            )

    async def broadcast(self, event_type: str, payload: dict[str, Any], *, topic_filter: str = "") -> int:
        """广播消息给所有订阅了对应主题的连接"""
        count = 0
        for conn in self._connections.values():
            if not topic_filter or topic_filter in conn.subscriptions:
                count += 1
        return count

    async def send_to_node(self, node_id: str, message: WSMessage) -> bool:
        """发送消息给指定节点的连接"""
        conn_id = self._conn_by_node.get(node_id)
        if not conn_id:
            return False
        return True

    # ========================
    # 内置命令处理器
    # ========================

    async def _handle_register(self, conn: WSConnection, msg: WSMessage) -> dict[str, Any]:
        """处理节点注册"""
        payload = msg.payload
        node_id = payload.get("node_id", "")
        node_type = payload.get("node_type", "worker")

        if not node_id:
            return {"ok": False, "error": "node_id required"}

        from nbot.gateway.nodes.registry import NodeInfo

        node_info = NodeInfo(
            node_id=node_id,
            node_type=node_type,
            address=payload.get("address", ""),
            version=payload.get("version", ""),
            metadata=payload.get("metadata", {}),
        )

        self._registry.register(node_info)
        conn.node_id = node_id
        conn.authenticated = True
        self._conn_by_node[node_id] = conn.conn_id

        return {"ok": True, "message": "registered"}

    async def _handle_unregister(self, conn: WSConnection, msg: WSMessage) -> dict[str, Any]:
        """处理节点注销"""
        node_id = conn.node_id or msg.payload.get("node_id", "")
        if not node_id:
            return {"ok": False, "error": "node_id required"}

        self._registry.unregister(node_id)
        self._conn_by_node.pop(node_id, None)
        conn.node_id = ""
        conn.authenticated = False

        return {"ok": True, "message": "unregistered"}

    async def _handle_heartbeat(self, conn: WSConnection, msg: WSMessage) -> dict[str, Any]:
        """处理心跳"""
        node_id = conn.node_id or msg.payload.get("node_id", "")
        if not node_id:
            return {"ok": False, "error": "node_id required"}

        from nbot.gateway.nodes.heartbeat import HeartbeatPayload

        payload = HeartbeatPayload(
            node_id=node_id,
            status=msg.payload.get("status", "online"),
            load=msg.payload.get("load", 0.0),
            tasks_completed=msg.payload.get("tasks_completed", 0),
            tasks_failed=msg.payload.get("tasks_failed", 0),
        )
        result = await self._heartbeat.receive_heartbeat(payload)
        return result

    async def _handle_stats(self, conn: WSConnection, msg: WSMessage) -> dict[str, Any]:
        """返回统计信息"""
        return {
            "ok": True,
            "data": {
                "registry": self._registry.get_stats(),
                "connections": len(self._connections),
                "pairing": self._pairing.get_stats(),
            },
        }

    async def _handle_health(self, conn: WSConnection, msg: WSMessage) -> dict[str, Any]:
        """健康检查"""
        health = self._registry.check_health()
        return {"ok": True, "data": health}

    async def _handle_subscribe(self, conn: WSConnection, msg: WSMessage) -> dict[str, Any]:
        """订阅事件主题"""
        topics = msg.payload.get("topics", [])
        if isinstance(topics, str):
            topics = [topics]

        for topic in topics:
            conn.subscriptions.add(topic)

        return {"ok": True, "subscribed": list(conn.subscriptions)}

    async def _handle_event_query(self, conn: WSConnection, msg: WSMessage) -> dict[str, Any]:
        """查询事件历史"""
        history = self._event_bus.get_history(
            topic=msg.payload.get("topic", ""),
            limit=msg.payload.get("limit", 50),
        )
        return {"ok": True, "events": history}

    async def _handle_pairing_create(self, conn: WSConnection, msg: WSMessage) -> dict[str, Any]:
        """创建配对请求"""
        req = self._pairing.create_pairing_request(
            node_id=msg.payload.get("node_id", ""),
            node_type=msg.payload.get("node_type", "worker"),
            metadata=msg.payload.get("metadata"),
        )
        return {"ok": True, **req.to_dict()}

    async def _handle_pairing_list(self, conn: WSConnection, msg: WSMessage) -> dict[str, Any]:
        """列出配对请求"""
        pending = self._pairing.list_pending()
        return {"ok": True, "pending": pending}

    def get_stats(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "connections": len(self._connections),
            "authenticated_nodes": len(self._conn_by_node),
            "handlers_registered": len(self._handlers),
            "registry": self._registry.get_stats(),
            "pairing": self._pairing.get_stats(),
        }
