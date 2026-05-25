"""Node 注册表

管理所有已注册的 Gateway 节点信息。

节点类型：
- gateway:  主网关节点（处理 Webhook、调度 AI）
- worker:    工作节点（消费队列、执行任务）
- channel:   频道节点（处理特定平台的接入/发送）

每个节点注册时提供：
- node_id:     唯一标识
- node_type:   节点类型
- capabilities: 能力声明
- metadata:    元数据（版本、地址等）
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

_log = logging.getLogger(__name__)


class NodeStatus(str, Enum):
    """节点状态"""

    ONLINE = "online"
    BUSY = "busy"
    IDLE = "idle"
    OFFLINE = "offline"
    DRAINING = "draining"  # 正在排空中（不再接收新任务）


class NodeType(str, Enum):
    """节点类型"""

    GATEWAY = "gateway"
    WORKER = "worker"
    CHANNEL = "channel"


@dataclass
class NodeInfo:
    """节点注册信息"""

    node_id: str = ""
    node_type: str = NodeType.GATEWAY.value
    status: str = NodeStatus.ONLINE.value
    version: str = ""
    address: str = ""
    capabilities: Any | None = None

    # 时间戳
    registered_at: float = 0.0
    last_heartbeat: float = 0.0
    last_seen: float = 0.0

    # 统计
    tasks_completed: int = 0
    tasks_failed: int = 0
    current_load: float = 0.0  # 0.0 ~ 1.0

    # 元数据
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.registered_at:
            self.registered_at = time.time()
        if not self.last_heartbeat:
            self.last_heartbeat = time.time()
        if not self.last_seen:
            self.last_seen = time.time()

    @property
    def is_alive(self) -> bool:
        return self.status != NodeStatus.OFFLINE.value

    @property
    def age_seconds(self) -> float:
        return time.time() - self.registered_at

    @property
    def heartbeat_age(self) -> float:
        return time.time() - self.last_heartbeat

    def to_dict(self) -> dict[str, Any]:
        caps_dict = None
        if self.capabilities and hasattr(self.capabilities, "to_dict"):
            caps_dict = self.capabilities.to_dict()

        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "status": self.status,
            "version": self.version,
            "address": self.address,
            "capabilities": caps_dict,
            "registered_at": self.registered_at,
            "last_heartbeat": self.last_heartbeat,
            "last_seen": self.last_seen,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "current_load": self.current_load,
            "metadata": self.metadata,
        }


class NodeRegistry:
    """节点注册表

    管理节点的注册、注销、发现和查询。
    """

    def __init__(self, *, heartbeat_timeout: float = 120.0):
        self._nodes: dict[str, NodeInfo] = {}
        self._heartbeat_timeout = heartbeat_timeout
        self._total_registered = 0
        self._total_unregistered = 0

    def register(self, node_info: NodeInfo) -> None:
        """注册新节点"""
        if not node_info.node_id:
            raise ValueError("node_id is required")

        existing = self._nodes.get(node_info.node_id)
        if existing:
            _log.warning(
                "[Registry] 节点重复注册，更新信息 node=%s", node_info.node_id
            )
            # 更新已有节点的信息（保留统计）
            existing.node_type = node_info.node_type
            existing.version = node_info.version
            existing.address = node_info.address
            existing.capabilities = node_info.capabilities
            existing.metadata.update(node_info.metadata)
            existing.last_heartbeat = time.time()
            existing.last_seen = time.time()
            existing.status = NodeStatus.ONLINE.value
            return

        self._nodes[node_info.node_id] = node_info
        self._total_registered += 1
        _log.info(
            "[Registry] 节点注册成功 id=%s type=%s addr=%s",
            node_info.node_id,
            node_info.node_type,
            node_info.address or "N/A",
        )

    def unregister(self, node_id: str) -> NodeInfo | None:
        """注销节点"""
        node = self._nodes.pop(node_id, None)
        if node:
            node.status = NodeStatus.OFFLINE.value
            self._total_unregistered += 1
            _log.info("[Registry] 节点注销 id=%s", node_id)
            return node
        _log.warning("[Registry] 注销未知节点 id=%s", node_id)
        return None

    def get_node(self, node_id: str) -> NodeInfo | None:
        return self._nodes.get(node_id)

    def update_heartbeat(
        self,
        node_id: str,
        *,
        status: str | None = None,
        load: float | None = None,
        tasks_completed: int | None = None,
        tasks_failed: int | None = None,
    ) -> bool:
        """更新节点心跳"""
        node = self._nodes.get(node_id)
        if not node:
            return False

        now = time.time()
        node.last_heartbeat = now
        node.last_seen = now

        if status is not None:
            node.status = status
        if load is not None:
            node.current_load = min(1.0, max(0.0, load))
        if tasks_completed is not None:
            node.tasks_completed = tasks_completed
        if tasks_failed is not None:
            node.tasks_failed = tasks_failed

        return True

    def find_nodes(
        self,
        *,
        node_type: str = "",
        status: str = "",
        capability: str = "",
        limit: int = 50,
    ) -> list[NodeInfo]:
        """查找符合条件的节点"""
        results = list(self._nodes.values())

        if node_type:
            results = [n for n in results if n.node_type == node_type]
        if status:
            results = [n for n in results if n.status == status]

        if capability and results:
            filtered = []
            for node in results:
                if node.capabilities and hasattr(node.capabilities, "has_channel_capability"):
                    if node.capabilities.has_channel_capability(capability):
                        filtered.append(node)
                        continue
                if node.capabilities and hasattr(node.capabilities, "has_tool_capability"):
                    if node.capabilities.has_tool_capability(capability):
                        filtered.append(node)
                        continue
                # 无能力声明或无匹配时不过滤掉（兼容性）
                filtered.append(node)
            results = filtered

        # 按负载排序（空闲优先）
        results.sort(key=lambda n: n.current_load)

        return results[:limit]

    def find_best_node(
        self,
        *,
        node_type: str = "",
        capability: str = "",
    ) -> NodeInfo | None:
        """查找最佳可用节点（在线 + 空闲 + 低负载）"""
        candidates = self.find_nodes(
            node_type=node_type,
            status=NodeStatus.IDLE.value,
            capability=capability,
            limit=1,
        )
        if candidates:
            return candidates[0]

        # 没有空闲节点，尝试在线节点
        candidates = self.find_nodes(
            node_type=node_type,
            status=NodeStatus.ONLINE.value,
            capability=capability,
            limit=10,
        )
        if candidates:
            return min(candidates, key=lambda n: n.current_load)

        return None

    def check_health(self) -> dict[str, Any]:
        """检查所有节点健康状态，标记超时节点为离线"""
        now = time.time()
        offline_nodes = []

        for node in self._nodes.values():
            if (now - node.last_heartbeat) > self._heartbeat_timeout and node.is_alive:
                old_status = node.status
                node.status = NodeStatus.OFFLINE.value
                offline_nodes.append((node.node_id, old_status))
                _log.warning(
                    "[Registry] 节点超时离线 id=%s last_heartbeat=%.0fs ago",
                    node.node_id,
                    now - node.last_heartbeat,
                )

        online_count = sum(1 for n in self._nodes.values() if n.is_alive)
        total_count = len(self._nodes)

        return {
            "total_nodes": total_count,
            "online_nodes": online_count,
            "offline_nodes": len(offline_nodes),
            "offline_node_ids": [n[0] for n in offline_nodes],
        }

    def get_stats(self) -> dict[str, Any]:
        """获取注册表统计信息"""
        health = self.check_health()

        type_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        for node in self._nodes.values():
            type_counts[node.node_type] = type_counts.get(node.node_type, 0) + 1
            status_counts[node.status] = status_counts.get(node.status, 0) + 1

        return {
            **health,
            "type_breakdown": type_counts,
            "status_breakdown": status_counts,
            "total_registered": self._total_registered,
            "total_unregistered": self._total_unregistered,
            "heartbeat_timeout": self._heartbeat_timeout,
        }

    def list_all(self) -> list[dict[str, Any]]:
        """列出所有节点"""
        return [n.to_dict() for n in self._nodes.values()]
