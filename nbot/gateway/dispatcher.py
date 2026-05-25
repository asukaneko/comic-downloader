"""Gateway 调度器

负责将 ChatRequest 交给 AI Core（AgentService）处理，
并返回 ChatResponse。
"""

import logging
import time
from typing import TYPE_CHECKING, Any, Optional

from nbot.core.chat_models import ChatRequest, ChatResponse
from nbot.gateway.errors import DispatchFailedError

if TYPE_CHECKING:
    from nbot.channels.base import BaseChannelAdapter

_log = logging.getLogger(__name__)


class GatewayDispatcher:
    """Gateway 调度器

    作为 Gateway 与 AI Core 之间的桥梁，
    将解析后的 ChatRequest 分发给 AgentService 处理。
    """

    def __init__(self, agent_service=None):
        self._agent_service = agent_service

    def set_agent_service(self, agent_service) -> None:
        """设置 AgentService 实例（支持延迟注入）"""
        self._agent_service = agent_service

    async def dispatch(
        self,
        chat_request: ChatRequest,
        *,
        adapter: Optional["BaseChannelAdapter"] = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """将 ChatRequest 分发给 AI Core

        Args:
            chat_request: 解析后的聊天请求
            adapter: 可选的频道适配器，传递给 AgentService
            **kwargs: 额外参数传递给 handler

        Returns:
            AI Core 的回复 ChatResponse

        Raises:
            DispatchFailedError: AI Core 处理失败时抛出
        """
        if not self._agent_service:
            _log.error("[Dispatcher] AgentService 未初始化")
            raise DispatchFailedError("AgentService is not initialized")

        start_time = time.time()
        try:
            _log.debug(
                "[Dispatcher] 开始调度 channel=%s conv=%s",
                chat_request.channel,
                chat_request.conversation_id,
            )

            # 调用 AgentService.process()
            result = await self._agent_service.process(chat_request, adapter=adapter, **kwargs)

            elapsed = time.time() - start_time
            _log.info(
                "[Dispatcher] 调度完成 channel=%s conv=%s耗时=%.2fs",
                chat_request.channel,
                chat_request.conversation_id,
                elapsed,
            )

            return result

        except ValueError as e:
            _log.error(
                "[Dispatcher] 无效请求 channel=%s error=%s",
                chat_request.channel,
                str(e),
            )
            raise DispatchFailedError(f"invalid request: {e}") from e
        except Exception as e:
            elapsed = time.time() - start_time
            _log.error(
                "[Dispatcher] AI Core 异常 channel=%s conv=%s耗时=%.2fs error=%s",
                chat_request.channel,
                chat_request.conversation_id,
                elapsed,
                str(e),
            )
            raise DispatchFailedError(f"AI core error: {e}") from e
