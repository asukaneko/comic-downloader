"""Gateway 回复投递模块

统一管理将 ChatResponse 发送回各个频道的逻辑。

投递策略：
- 如果频道有专用 sender（如 QQSender、FeishuSender），调用专用 sender
- 如果没有 sender，则通过 ChannelAdapter 的 build_assistant_message 构建消息
- 发送失败时记录日志但不影响 Gateway 主流程崩溃

功能特性：
- 长文本自动分片发送
- 富文本降级（Markdown → 纯文本）
- 投递状态持久化（通过 DeliveryStore）
"""

import logging
import re
from typing import TYPE_CHECKING, Any

from nbot.core.chat_models import ChatResponse
from nbot.gateway.errors import DeliveryFailedError
from nbot.gateway.schemas import DeliveryRequest

if TYPE_CHECKING:
    from nbot.gateway.delivery_store import DeliveryStore

_log = logging.getLogger(__name__)

# 单条消息最大长度（超过此长度需要分片）
_MAX_MESSAGE_LENGTH = 4000


def split_long_text(text: str, max_length: int = _MAX_MESSAGE_LENGTH) -> list[str]:
    """将长文本按段落/句子智能分片

    优先在换行符、句号、逗号等位置切分，
    避免在单词或中文字符中间断开。
    """
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # 尝试在最后一个换行符处切分
        split_pos = _find_last_split_position(remaining[:max_length])
        chunk = remaining[:split_pos].rstrip()
        if not chunk:
            # 防止空块，强制截断
            chunk = remaining[:max_length]
            remaining = remaining[max_length:]
        else:
            remaining = remaining[split_pos:]

        chunks.append(chunk)

    return [c for c in chunks if c]


def _find_last_split_position(text: str) -> int:
    """在文本中找到最佳切分位置（从后向前查找）"""
    # 优先级：双换行 > 换行 > 中文句号 > 英文句号+空格 > 逗号 > 空格
    patterns = [
        ("\n\n", 0),
        ("\n", 0),
        ("。", 1),
        (". ", 2),
        ("，", 1),
        (", ", 2),
        (" ", 0),
    ]

    best_pos = len(text)
    for pattern, offset in patterns:
        pos = text.rfind(pattern)
        if pos != -1 and pos < best_pos:
            best_pos = pos + offset

    return best_pos or len(text)


def strip_markdown(text: str) -> str:
    """基础 Markdown 降级：去除常见 Markdown 标记，转为纯文本"""
    result = text
    # 移除标题标记
    result = re.sub(r"^#{1,6}\s+", "", result, flags=re.MULTILINE)
    # 移除加粗和斜体
    result = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", result)
    # 移除行内代码
    result = re.sub(r"`([^`]+)`", r"\1", result)
    # 移除代码块
    result = re.sub(r"```[\s\S]*?```", lambda m: m.group().strip("`").strip(), result)
    # 移除链接但保留文字
    result = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", result)
    # 移除图片标记
    result = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"[图片: \1]", result)
    # 移除无序列表标记
    result = re.sub(r"^[\s]*[-*+]\s+", "", result, flags=re.MULTILINE)
    # 移除有序列表标记
    result = re.sub(r"^[\s]*\d+\.\s+", "", result, flags=re.MULTILINE)
    # 移除分割线
    result = re.sub(r"^---+\s*$", "", result, flags=re.MULTILINE)
    # 移除引用标记
    result = re.sub(r"^>\s+", "", result, flags=re.MULTILINE)
    return result.strip()


class GatewayDelivery:
    """Gateway 回复投递器

    统一将 AI 回复投递到对应频道。
    支持长文本分片、富文本降级和投递状态记录。
    """

    def __init__(self, delivery_store: "DeliveryStore | None" = None):
        self._senders: dict[str, Any] = {}
        self._delivery_store = delivery_store
        self._enable_text_split = True
        self._enable_markdown_strip = True

    @property
    def enable_text_split(self) -> bool:
        return self._enable_text_split

    @enable_text_split.setter
    def enable_text_split(self, value: bool) -> None:
        self._enable_text_split = value

    @property
    def enable_markdown_strip(self) -> bool:
        return self._enable_markdown_strip

    @enable_markdown_strip.setter
    def enable_markdown_strip(self, value: bool) -> None:
        self._enable_markdown_strip = value

    def register_sender(self, channel_id: str, send_func: Any) -> None:
        """注册频道专用发送函数

        Args:
            channel_id: 频道标识
            send_func: 异步发送函数，签名为：
                       async def send(chat_response, delivery_request) -> bool
        """
        self._senders[channel_id] = send_func
        _log.debug("[Delivery] 注册发送器 channel=%s", channel_id)

    async def send_response(
        self,
        *,
        channel_id: str,
        chat_request,
        chat_response: ChatResponse,
        trace_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """发送回复到对应频道

        完整流程：
        1. 创建投递记录
        2. 内容预处理（长文本分片 / Markdown 降级）
        3. 选择发送方式并执行
        4. 更新投递状态

        Returns:
            投递结果字典，包含 status 等信息
        """
        content = chat_response.final_content or ""

        # 记录投递到存储
        delivery_id = None
        if self._delivery_store:
            try:
                delivery_id = self._delivery_store.create(
                    trace_id=trace_id,
                    channel_id=channel_id,
                    conversation_id=chat_request.conversation_id,
                    content=content,
                )
            except Exception as e:
                _log.warning("[Delivery] 投递记录创建失败 trace=%s error=%s", trace_id, str(e))

        try:
            # 内容预处理：Markdown 降级
            processed_content = content
            if self._enable_markdown_strip:
                processed_content = strip_markdown(processed_content)

            # 内容预处理：长文本分片
            chunks = [processed_content]
            if self._enable_text_split and len(processed_content) > _MAX_MESSAGE_LENGTH:
                chunks = split_long_text(processed_content)
                _log.info(
                    "[Delivery] 长文本分片 trace=%s channel=%s total_len=%d chunks=%d",
                    trace_id,
                    channel_id,
                    len(processed_content),
                    len(chunks),
                )

            results: list[dict[str, Any]] = []
            for idx, chunk in enumerate(chunks):
                # 构建分片请求
                chunk_delivery = DeliveryRequest(
                    trace_id=trace_id,
                    channel_id=channel_id,
                    conversation_id=chat_request.conversation_id,
                    content=chunk,
                    reply_to_message_id=chat_request.parent_message_id if idx == 0 else None,
                    metadata={
                        **dict(metadata or {}),
                        "chunk_index": idx,
                        "chunk_total": len(chunks),
                    },
                )
                # 分片响应包装
                chunk_response = ChatResponse(
                    final_content=chunk,
                    assistant_message=chat_response.assistant_message,
                    tool_trace=chat_response.tool_trace,
                    metadata={**dict(chat_response.metadata), "_chunk": True},
                )

                result = await self._do_send(
                    channel_id, chunk_response, chunk_delivery, chat_request
                )
                results.append(result)

                # 任一分片失败则整体标记为部分失败
                if result.get("status") not in ("delivered",):
                    _log.warning(
                        "[Delivery] 分片 %d/%d 投递异常 trace=%s status=%s",
                        idx + 1,
                        len(chunks),
                        trace_id,
                        result.get("status"),
                    )

            # 汇总结果
            all_ok = all(r.get("status") == "delivered" for r in results)
            final_status = "delivered" if all_ok else "partial_failed"

            if self._delivery_store and delivery_id is not None:
                try:
                    if all_ok:
                        self._delivery_store.mark_delivered(delivery_id)
                    else:
                        self._delivery_store.mark_failed(delivery_id=delivery_id, error="partial failure")
                except Exception as e:
                    _log.warning("[Delivery] 投递状态更新失败 trace=%s error=%s", trace_id, str(e))

            return {
                "status": final_status,
                "trace_id": trace_id,
                "chunks": len(results),
                "results": results,
            }

        except DeliveryFailedError:
            if self._delivery_store and delivery_id is not None:
                try:
                    self._delivery_store.mark_failed(delivery_id=delivery_id, error=str(DeliveryFailedError()))
                except Exception:
                    pass
            raise
        except Exception as e:
            _log.error(
                "[Delivery] 投递异常 trace=%s channel=%s error=%s",
                trace_id,
                channel_id,
                str(e),
            )
            if self._delivery_store and delivery_id is not None:
                try:
                    self._delivery_store.mark_failed(delivery_id=delivery_id, error=str(e))
                except Exception:
                    pass
            raise DeliveryFailedError(str(e)) from e

    async def _do_send(
        self,
        channel_id: str,
        chat_response: ChatResponse,
        delivery_req: DeliveryRequest,
        chat_request,
    ) -> dict[str, Any]:
        """执行单次投递操作"""
        sender = self._senders.get(channel_id)
        if sender:
            return await self._send_via_sender(sender, chat_response, delivery_req)
        return await self._send_via_adapter(channel_id, chat_request, chat_response, delivery_req)

    async def _send_via_sender(
        self,
        sender: Any,
        chat_response: ChatResponse,
        delivery_req: DeliveryRequest,
    ) -> dict[str, Any]:
        """通过专用发送器投递"""
        try:
            success = await sender(chat_response, delivery_req)
            if success:
                _log.debug(
                    "[Delivery] 投递成功 trace=%s channel=%s",
                    delivery_req.trace_id,
                    delivery_req.channel_id,
                )
                return {"status": "delivered", "trace_id": delivery_req.trace_id}
            _log.warning(
                "[Delivery] 发送器返回失败 trace=%s channel=%s",
                delivery_req.trace_id,
                delivery_req.channel_id,
            )
            return {"status": "failed", "trace_id": delivery_req.trace_id}
        except Exception as e:
            _log.error(
                "[Delivery] 发送器异常 trace=%s channel=%s error=%s",
                delivery_req.trace_id,
                delivery_req.channel_id,
                str(e),
            )
            raise DeliveryFailedError(f"sender error: {e}") from e

    async def _send_via_adapter(
        self,
        channel_id: str,
        chat_request,
        chat_response: ChatResponse,
        delivery_req: DeliveryRequest,
    ) -> dict[str, Any]:
        """通过 ChannelAdapter 构建消息（默认方式）"""
        from nbot.channels.registry import get_channel_adapter

        adapter = get_channel_adapter(channel_id)
        if adapter and hasattr(adapter, "build_assistant_message"):
            message = adapter.build_assistant_message(
                chat_response,
                conversation_id=delivery_req.conversation_id,
                metadata=delivery_req.metadata,
            )
            _log.debug(
                "[Delivery] 通过 Adapter 构建消息 trace=%s channel=%s",
                delivery_req.trace_id,
                channel_id,
            )
            return {
                "status": "delivered",
                "trace_id": delivery_req.trace_id,
                "message": message,
            }

        _log.debug(
            "[Delivery] 直接返回内容 trace=%s channel=%s",
            delivery_req.trace_id,
            channel_id,
        )
        return {
            "status": "delivered",
            "trace_id": delivery_req.trace_id,
            "content": delivery_req.content,
        }
