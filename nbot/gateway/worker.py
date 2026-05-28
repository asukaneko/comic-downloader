"""Gateway 后台 Worker

从异步队列中消费事件，执行完整的处理链路：
  出队 → 解析 → 去重 → 构建 ChatRequest → 调度 AI Core → 投递回复

Worker 设计为可独立启停的异步任务，
支持优雅关闭（处理完当前项后退出）。
"""

import asyncio
import logging
import time
from typing import Any

from nbot.gateway.delivery import GatewayDelivery
from nbot.gateway.dispatcher import GatewayDispatcher
from nbot.gateway.errors import (
    DeliveryFailedError,
    DispatchFailedError,
    GatewayError,
)
from nbot.gateway.queue import EventQueue, QueueItem
from nbot.gateway.retry import ErrorCategory, RetryHandler, classify_error
from nbot.gateway.router import GatewayRouter
from nbot.gateway.schemas import GatewayResult
from nbot.gateway.trace import TraceFactory, trace_context

_log = logging.getLogger(__name__)


class GatewayWorker:
    """Gateway 后台事件消费者

    持续从队列中取出事件，完成鉴权后的完整处理链路。
    """

    def __init__(
        self,
        *,
        queue: EventQueue | None = None,
        router: GatewayRouter | None = None,
        dispatcher: GatewayDispatcher | None = None,
        delivery: GatewayDelivery | None = None,
        retry_handler: RetryHandler | None = None,
        trace_factory: TraceFactory | None = None,
        dedupe_store=None,
        event_store=None,
        concurrency: int = 1,
        idle_timeout: float = 30.0,
    ):
        self._queue = queue or EventQueue()
        self._router = router or GatewayRouter()
        self._dispatcher = dispatcher or GatewayDispatcher()
        self._delivery = delivery or GatewayDelivery()
        self._retry_handler = retry_handler or RetryHandler()
        self._trace_factory = trace_factory or TraceFactory()
        self._dedupe_store = dedupe_store
        self._event_store = event_store

        # Worker 控制状态
        self._running = False
        self._task: asyncio.Task | None = None
        self._concurrency = concurrency  # 并发 Worker 数量
        self._idle_timeout = idle_timeout  # 空闲超时（秒）
        self._processed_count = 0
        self._error_count = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def processed_count(self) -> int:
        return self._processed_count

    @property
    def error_count(self) -> int:
        return self._error_count

    async def start(self) -> None:
        """启动 Worker 后台任务"""
        if self._running:
            _log.warning("[Worker] 已经在运行中")
            return

        self._running = True
        self._task = asyncio.create_task(self._worker_loop())
        _log.info(
            "[Worker] 已启动 concurrency=%d idle_timeout=%ds",
            self._concurrency,
            self._idle_timeout,
        )

    async def stop(self, *, graceful: bool = True) -> None:
        """停止 Worker

        Args:
            graceful: 是否优雅关闭（等待当前任务完成）
        """
        if not self._running:
            return

        self._running = False
        if graceful:
            _log.info("[Worker] 正在优雅关闭...")
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
        else:
            if self._task:
                self._task.cancel()

        stats = self.get_stats()
        _log.info(
            "[Worker] 已停止 processed=%d errors=%d",
            stats["processed"],
            stats["errors"],
        )

    async def process_single(self, item: QueueItem) -> GatewayResult:
        """处理单个队列项（可供外部调用）

        完整链路：路由 → 解析 → 去重 → 构建请求 → 调度 AI → 投递回复

        Args:
            item: 队列中的事件项

        Returns:
            处理结果
        """
        with trace_context(item.trace_id):
            try:
                result = await self._process_item(item)
                return result
            except Exception as e:
                _log.error(
                    "[Worker] 未预期的异常 item=%s trace=%s error=%s",
                    item.item_id,
                    item.trace_id,
                    str(e),
                )
                self._error_count += 1
                self._queue.mark_failed(item, error=str(e))
                return GatewayResult(
                    ok=False,
                    trace_id=item.trace_id,
                    channel_id=item.channel_id,
                    status="worker_error",
                    error=f"unexpected error: {e}",
                )

    async def _worker_loop(self) -> None:
        """Worker 主循环：持续从队列取事件并处理"""
        _log.info("[Worker] 主循环启动")

        while self._running:
            try:
                # 从队列取出事件（带超时，便于定期检查运行状态）
                item = await self._queue.dequeue(timeout=self._idle_timeout)

                if item is None:
                    # 队列为空，继续等待
                    continue

                # 检查是否需要延迟重试
                if item.status.value == "failed" and item.next_retry_at:
                    wait_seconds = item.next_retry_at - time.time()
                    if wait_seconds > 0:
                        _log.info(
                            "[Worker] 延迟重试 item=%s trace=%s wait=%.1fs",
                            item.item_id,
                            item.trace_id,
                            wait_seconds,
                        )
                        # 将 item 放回队列尾部，稍后重试
                        await self._queue.enqueue(item)
                        await asyncio.sleep(min(wait_seconds, 1.0))
                        continue

                # 处理事件
                await self.process_single(item)

            except asyncio.CancelledError:
                _log.info("[Worker] 收到取消信号，退出主循环")
                break
            except Exception as e:
                _log.error("[Worker] 主循环异常 error=%s", str(e), exc_info=True)
                # 短暂休眠后继续，避免异常时 CPU 空转
                await asyncio.sleep(1)

        _log.info("[Worker] 主循环已退出")

    async def _process_item(self, item: QueueItem) -> GatewayResult:
        """处理单个队列项的核心逻辑"""

        # 标记为正在处理
        self._queue.mark_processing(item)
        channel_id = item.channel_id
        trace_id = item.trace_id

        _log.info(
            "[Worker] 开始处理 item=%s trace=%s channel=%s attempt=%d",
            item.item_id,
            trace_id,
            channel_id,
            item.attempt,
        )

        # === Step 1: 路由到 Adapter ===
        adapter = self._router.get_adapter(channel_id)
        if not adapter:
            error_msg = f"unknown channel: {channel_id}"
            _log.warning("[Worker] %s trace=%s", error_msg, trace_id)
            self._handle_item_error(item, error_msg, non_recoverable=True)
            return GatewayResult(
                ok=False,
                trace_id=trace_id,
                channel_id=channel_id,
                status="unknown_channel",
                error=error_msg,
            )

        if not hasattr(adapter, "parse_event"):
            error_msg = f"channel {channel_id} has no parse_event"
            _log.warning("[Worker] %s trace=%s", error_msg, trace_id)
            self._handle_item_error(item, error_msg, non_recoverable=True)
            return GatewayResult(
                ok=False,
                trace_id=trace_id,
                channel_id=channel_id,
                status="missing_parser",
                error=error_msg,
            )

        # === Step 2: 解析平台事件 ===
        try:
            parsed = adapter.parse_event(item.raw_event)
        except Exception as e:
            error_msg = f"parse error: {e}"
            _log.error("[Worker] 事件解析失败 trace=%s error=%s", trace_id, str(e))
            self._handle_item_error(item, error_msg)
            return GatewayResult(
                ok=False,
                trace_id=trace_id,
                channel_id=channel_id,
                status="parse_failed",
                error=error_msg,
            )

        if not parsed:
            _log.debug("[Worker] 忽略空事件 trace=%s", trace_id)
            self._queue.mark_completed(item)
            return GatewayResult(
                ok=True,
                trace_id=trace_id,
                channel_id=channel_id,
                status="ignored",
                ignored=True,
            )

        # 缓存解析结果
        item.parsed_data = parsed

        # === Step 3: 构建 ChatRequest ===
        try:
            request_kwargs = {
                "conversation_id": parsed.get("conversation_id"),
                "content": parsed.get("content", ""),
                "sender": parsed.get("sender", ""),
                "user_id": parsed.get("user_id"),
                "attachments": parsed.get("attachments"),
                "parent_message_id": parsed.get("parent_message_id"),
                "metadata": parsed.get("metadata"),
            }
            chat_request = adapter.build_chat_request(**request_kwargs)
        except Exception as e:
            error_msg = f"build chat request failed: {e}"
            _log.error("[Worker] ChatRequest 构建失败 trace=%s error=%s", trace_id, str(e))
            self._handle_item_error(item, error_msg)
            return GatewayResult(
                ok=False,
                trace_id=trace_id,
                channel_id=channel_id,
                status="build_request_failed",
                error=error_msg,
            )

        item.chat_request = chat_request

        # === Step 4: 调度到 AI Core ===
        start_time = time.time()
        try:
            chat_response = await self._dispatcher.dispatch(chat_request, adapter=adapter)
        except GatewayError as e:
            elapsed = time.time() - start_time
            error_msg = e.message
            _log.error(
                "[Worker] AI Core 失败 trace=%s耗时=%.2fs error=%s",
                trace_id,
                elapsed,
                error_msg,
            )
            self._handle_dispatch_error(item, e)
            return GatewayResult(
                ok=False,
                trace_id=trace_id,
                channel_id=channel_id,
                conversation_id=chat_request.conversation_id,
                status=e.code,
                error=error_msg,
            )
        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = f"AI core exception: {e}"
            _log.error(
                "[Worker] AI Core 异常 trace=%s耗时=%.2fs error=%s",
                trace_id,
                elapsed,
                str(e),
            )
            self._handle_dispatch_error(item, DispatchFailedError(str(e)))
            return GatewayResult(
                ok=False,
                trace_id=trace_id,
                channel_id=channel_id,
                conversation_id=chat_request.conversation_id,
                status="dispatch_failed",
                error=error_msg,
            )

        # 记录模型信息和故障转移事件
        resp_metadata = getattr(chat_response, "metadata", None) or {}
        used_model_id = resp_metadata.get("model_id", "")
        used_model_name = resp_metadata.get("model_name", "")
        failover_events = resp_metadata.get("failover_events", [])
        if used_model_id or used_model_name:
            self._record_event(
                trace_id=trace_id, channel_id=channel_id,
                status="model_selected",
                conversation_id=chat_request.conversation_id,
                metadata={
                    k: v for k, v in {
                        "model_id": used_model_id,
                        "model_name": used_model_name,
                    }.items() if v
                },
            )
        for ev in failover_events:
            self._record_event(
                trace_id=trace_id, channel_id=channel_id,
                status="model_failover",
                conversation_id=chat_request.conversation_id,
                metadata={
                    "failed_model_id": ev.get("model_id", ""),
                    "failed_model_name": ev.get("model_name", ""),
                    "status_code": ev.get("status_code", 0),
                    "category": ev.get("category", ""),
                },
            )

        # === Step 5: 投递回复 ===
        try:
            delivery_result = await self._delivery.send_response(
                channel_id=channel_id,
                chat_request=chat_request,
                chat_response=chat_response,
                trace_id=trace_id,
            )
        except DeliveryFailedError as e:
            _log.error(
                "[Worker] 投递失败 trace=%s channel=%s error=%s",
                trace_id,
                channel_id,
                e.message,
            )
            self._handle_delivery_error(item, e)
            return GatewayResult(
                ok=True,
                trace_id=trace_id,
                channel_id=channel_id,
                conversation_id=chat_request.conversation_id,
                status="delivery_failed",
                error=e.message,
                data={"response_content": chat_response.final_content},
            )
        except Exception as e:
            _log.error(
                "[Worker] 投递异常 trace=%s channel=%s error=%s",
                trace_id,
                channel_id,
                str(e),
            )
            self._handle_delivery_error(item, DeliveryFailedError(str(e)))
            return GatewayResult(
                ok=True,
                trace_id=trace_id,
                channel_id=channel_id,
                conversation_id=chat_request.conversation_id,
                status="delivery_failed",
                error=str(e),
                data={"response_content": chat_response.final_content},
            )

        # === 完成 ===
        total_elapsed = time.time() - start_time
        self._processed_count += 1
        self._queue.mark_completed(item, result=delivery_result)

        # Worker 处理成功后标记去重（异步模式 dedupe 推迟到这里）
        delivery_status = delivery_result.get("status", "unknown")
        if self._dedupe_store and delivery_status in ("delivered", "built"):
            parsed = item.parsed_data or {}
            message_id = self._extract_message_id(channel_id, parsed)
            if message_id:
                try:
                    await self._dedupe_store.mark(
                        message_id,
                        channel_id=channel_id,
                        message_id=message_id.split(":")[-1] if ":" in message_id else "",
                    )
                except Exception as e:
                    _log.debug(
                        "[Worker] dedupe 标记失败 trace=%s error=%s", trace_id, str(e)
                    )

        _log.info(
            "[Worker] 处理完成 item=%s trace=%s channel=%s status=%s耗时=%.2fs",
            item.item_id,
            trace_id,
            channel_id,
            delivery_status,
            total_elapsed,
        )

        return GatewayResult(
            ok=delivery_status in ("delivered", "built"),
            trace_id=trace_id,
            channel_id=channel_id,
            conversation_id=chat_request.conversation_id,
            status=delivery_status,
            data={
                "delivery": delivery_result,
                "response_content": chat_response.final_content,
            },
        )

    def _record_event(
        self,
        *,
        trace_id: str,
        channel_id: str,
        status: str,
        conversation_id: str = "",
        user_id: str = "",
        message_id: str = "",
        metadata: dict | None = None,
        error: str = "",
    ) -> None:
        """记录事件到 EventStore（如果可用）"""
        if not self._event_store:
            return
        try:
            self._event_store.record(
                trace_id=trace_id,
                channel_id=channel_id,
                status=status,
                conversation_id=conversation_id,
                user_id=user_id,
                message_id=message_id,
                metadata=metadata,
                error=error,
            )
        except Exception as e:
            _log.debug("[Worker] 事件记录失败 trace=%s status=%s error=%s", trace_id, status, str(e))

    def _handle_item_error(
        self,
        item: QueueItem,
        error: str,
        *,
        non_recoverable: bool = False,
    ) -> None:
        """处理错误并决定是否重试"""
        self._error_count += 1

        if non_recoverable:
            # 不可恢复错误直接进入死信
            self._queue.mark_failed(item, error=error)
        else:
            # 通过重试策略判断
            retry_ok, next_retry_at = self._retry_handler.handle_failure(item, error)
            if retry_ok:
                self._queue.mark_failed(item, error=error, next_retry_at=next_retry_at)
            else:
                self._queue.mark_failed(item, error=error)

    def _handle_dispatch_error(self, item: QueueItem, error: GatewayError) -> None:
        """处理调度错误"""
        category = classify_error(error)
        non_recoverable = category != ErrorCategory.RECOVERABLE
        self._handle_item_error(
            item, error.message or str(error), non_recoverable=non_recoverable
        )

    def _handle_delivery_error(self, item: QueueItem, error: Exception) -> None:
        """处理投递错误"""
        category = classify_error(error)
        non_recoverable = category != ErrorCategory.RECOVERABLE
        self._handle_item_error(
            item, str(error), non_recoverable=non_recoverable
        )

    def _extract_message_id(self, channel_id: str, parsed: dict[str, Any]) -> str:
        """从解析结果中提取消息 ID，构建去重键"""
        metadata = parsed.get("metadata") or {}
        raw_id = (
            metadata.get("message_id")
            or metadata.get(f"{channel_id}_message_id")
            or parsed.get("message_id")
        )
        return f"{channel_id}:{raw_id}" if raw_id else ""

    def get_stats(self) -> dict[str, Any]:
        """获取 Worker 运行统计"""
        queue_stats = self._queue.get_stats()
        return {
            "running": self._running,
            "processed": self._processed_count,
            "errors": self._error_count,
            "concurrency": self._concurrency,
            **queue_stats,
        }
