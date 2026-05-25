"""Gateway 频道路由器

根据 channel_id 获取对应的 ChannelAdapter，
不负责业务逻辑，只做适配器查找。
"""

import logging
from typing import TYPE_CHECKING, Optional

from nbot.channels.registry import get_channel_adapter

if TYPE_CHECKING:
    from nbot.channels.base import BaseChannelAdapter

_log = logging.getLogger(__name__)


class GatewayRouter:
    """频道路由器

    负责根据 channel_id 查找对应的 ChannelAdapter。
    复用已有的 ChannelRegistry，保持与现有频道系统的一致性。
    """

    def __init__(self):
        self._fallback_adapter: BaseChannelAdapter | None = None

    def get_adapter(self, channel_id: str) -> Optional["BaseChannelAdapter"]:
        """根据 channel_id 获取 ChannelAdapter

        Args:
            channel_id: 频道标识符（如 "qq"、"web"、"feishu"、自定义频道ID）

        Returns:
            对应的 ChannelAdapter 实例，未找到返回 None
        """
        adapter = get_channel_adapter(channel_id)
        if adapter:
            _log.debug("[Router] 找到适配器 channel_id=%s", channel_id)
            return adapter

        if self._fallback_adapter:
            _log.debug("[Router] 使用 fallback 适配器 channel_id=%s", channel_id)
            return self._fallback_adapter

        _log.warning("[Router] 未找到适配器 channel_id=%s", channel_id)
        return None

    def set_fallback(self, adapter: "BaseChannelAdapter") -> None:
        """设置默认 fallback 适配器

        当无法找到具体频道适配器时使用。
        """
        self._fallback_adapter = adapter

    def has_channel(self, channel_id: str) -> bool:
        """检查频道是否已注册"""
        return get_channel_adapter(channel_id) is not None
