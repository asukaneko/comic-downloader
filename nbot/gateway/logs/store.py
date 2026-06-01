"""Gateway 日志存储抽象接口

定义 GatewayLogStore 抽象基类，
具体实现（如 SQLite）继承此接口。
"""

from abc import ABC, abstractmethod
from typing import Any

from nbot.gateway.logs.models import GatewayLogRecord


class GatewayLogStore(ABC):
    """日志存储抽象基类"""

    @abstractmethod
    def insert(self, record: GatewayLogRecord) -> None:
        """插入一条日志记录"""

    @abstractmethod
    def query(
        self,
        *,
        trace_id: str = "",
        source: str = "",
        type: str = "",
        level: str = "",
        status: str = "",
        tool_name: str = "",
        channel_id: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[GatewayLogRecord]:
        """按条件查询日志"""

    @abstractmethod
    def get_by_trace(self, trace_id: str) -> list[GatewayLogRecord]:
        """根据 trace_id 查询所有关联日志"""

    @abstractmethod
    def get_by_id(self, log_id: str) -> GatewayLogRecord | None:
        """根据日志 ID 查询单条记录"""

    @abstractmethod
    def count(self) -> int:
        """获取日志总数"""

    @abstractmethod
    def cleanup(self, *, keep_days: int = 30) -> int:
        """清理旧日志，返回清理数量"""
