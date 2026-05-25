"""心跳保活机制

管理 Node 的心跳检测：
- 接收并记录节点心跳
- 检测超时未上报心跳的节点
- 支持可配置的心跳间隔和超时时间
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nbot.gateway.nodes.registry import NodeRegistry

_log = logging.getLogger(__name__)


@dataclass
class HeartbeatConfig:
    """心跳配置"""

    interval_seconds: float = 30.0      # 心跳间隔
    timeout_seconds: float = 120.0       # 超时阈值
    check_interval: float = 15.0         # 健康检查间隔


@dataclass
class HeartbeatPayload:
    """心跳载荷"""

    node_id: str = ""
    timestamp: float = 0.0
    status: str = "online"
    load: float = 0.0
    tasks_completed: int = 0
    tasks_failed: int = 0
    metadata: dict[str, str] = {}

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


class HeartbeatManager:
    """心跳管理器"""

    def __init__(
        self,
        registry: "NodeRegistry",
        config: HeartbeatConfig | None = None,
    ):
        self._registry = registry
        self._config = config or HeartbeatConfig()
        self._check_task: asyncio.Task | None = None
        self._running = False
        self._on_node_offline_callbacks: list[Callable[[str], None]] = []

    async def receive_heartbeat(self, payload: HeartbeatPayload) -> dict[str, Any]:
        """接收节点心跳

        Args:
            payload: 心跳载荷

        Returns:
            处理结果字典
        """
        node_id = payload.node_id
        if not node_id:
            return {"ok": False, "error": "node_id required"}

        updated = self._registry.update_heartbeat(
            node_id,
            status=payload.status,
            load=payload.load,
            tasks_completed=payload.tasks_completed,
            tasks_failed=payload.tasks_failed,
        )

        if not updated:
            return {"ok": False, "error": f"unknown node: {node_id}"}

        _log.debug(
            "[Heartbeat] 收到心跳 node=%s status=%s load=%.2f",
            node_id,
            payload.status,
            payload.load,
        )

        return {
            "ok": True,
            "node_id": node_id,
            "server_time": time.time(),
            "next_interval": self._config.interval_seconds,
        }

    def on_node_offline(self, callback: Callable[[str], None]) -> None:
        """注册节点离线回调"""
        self._on_node_offline_callbacks.append(callback)

    async def start_monitor(self) -> None:
        """启动健康检查监控循环"""
        if self._running:
            return

        self._running = True
        self._check_task = asyncio.create_task(self._monitor_loop())
        _log.info(
            "[Heartbeat] 监控已启动 interval=%.1fs timeout=%.1fs",
            self._config.check_interval,
            self._config.timeout_seconds,
        )

    async def stop_monitor(self) -> None:
        """停止健康检查监控"""
        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        _log.info("[Heartbeat] 监控已停止")

    async def _monitor_loop(self) -> None:
        """健康检查主循环"""
        while self._running:
            try:
                await asyncio.sleep(self._config.check_interval)
                health_result = self._registry.check_health()

                if health_result["offline_nodes"] > 0:
                    for node_id in health_result["offline_node_ids"]:
                        for cb in self._on_node_offline_callbacks:
                            try:
                                cb(node_id)
                            except Exception as e:
                                _log.error(
                                    "[Heartbeat] 离线回调异常 node=%s error=%s",
                                    node_id,
                                    str(e),
                                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                _log.error("[Heartbeat] 监控循环异常 error=%s", str(e))
                await asyncio.sleep(5)

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._registry.get_stats(),
            "monitor_running": self._running,
            "interval": self._config.interval_seconds,
            "timeout": self._config.timeout_seconds,
        }
