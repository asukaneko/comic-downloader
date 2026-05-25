"""
NekoBot Gateway - 消息与能力边界层

统一多频道消息接入，解决鉴权、路由、去重、限流、日志、回复投递等重复问题。
支持同步/异步双模式、SQLite 持久化、事件总线、节点控制面。
"""

from nbot.gateway.gateway import ChannelGateway
from nbot.gateway.schemas import DeliveryRequest, GatewayEvent, GatewayResult

__all__ = [
    "ChannelGateway",
    "DeliveryRequest",
    "GatewayEvent",
    "GatewayResult",
]
