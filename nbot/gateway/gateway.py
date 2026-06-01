"""NekoBot Gateway 主入口

ChannelGateway 是 Gateway 模块的核心类，
负责编排完整的外部事件处理链路：

  同步模式（默认）：
  HTTP Webhook
    ↓
  Gateway.receive(channel_id, raw_event, headers)
    ↓
  security.verify()          → 鉴权
    ↓
  rate_limiter.check()       → 限流
    ↓
  router.get_adapter()       → 获取频道适配器
    ↓
  adapter.parse_event()      → 解析平台事件
    ↓
  dedupe_store.exists()      → 去重检查
    ↓
  adapter.build_chat_request() → 构建 ChatRequest
    ↓
  dispatcher.dispatch()      → 调用 AI Core
    ↓
  delivery.send_response()   → 投递回复
    ↓
  return GatewayResult

  异步模式（async_mode=True）：
  HTTP Webhook
    ↓
  Gateway.receive(channel_id, raw_event, headers)
    ↓
  security.verify()          → 鉴权（同步）
    ↓
  rate_limiter.check()       → 限流（同步）
    ↓
  router + parse + dedup     → 解析+去重（同步）
    ↓
  queue.enqueue(item)        → 入队
    ↓
  return GatewayResult(queued=True) ← 立即返回 200 OK

  Worker 后台消费队列：
    dequeue → dispatch AI Core → delivery reply

设计原则：
- Gateway 不理解 AI（不处理 Prompt、角色卡、记忆等）
- Adapter 只做平台格式转换
- 所有内部组件可替换
"""

import asyncio
import inspect
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from nbot.gateway.dedupe import DedupeStore
from nbot.gateway.delivery import GatewayDelivery
from nbot.gateway.dispatcher import GatewayDispatcher
from nbot.gateway.errors import GatewayError
from nbot.gateway.queue import EventQueue, QueueItem
from nbot.gateway.rate_limit import RateLimiter
from nbot.gateway.router import GatewayRouter
from nbot.gateway.schemas import GatewayEvent, GatewayResult
from nbot.gateway.security import SecurityProvider, build_security_provider
from nbot.gateway.trace import TraceFactory, trace_context
from nbot.gateway.worker import GatewayWorker

if TYPE_CHECKING:
    from nbot.gateway.storage import GatewayStorage

_log = logging.getLogger(__name__)

_LIFECYCLE_LOG_FIELDS: dict[str, tuple[str, str, str, str]] = {
    "received": ("info", "received", "receive", "Event received"),
    "verified": ("info", "validation", "verify", "Event verified"),
    "dispatched": ("info", "dispatch", "dispatch", "Dispatched to AI core"),
    "delivering": ("info", "delivery", "deliver", "Delivering response"),
    "delivered": ("info", "completed", "deliver", "Response delivered"),
    "built": ("info", "completed", "deliver", "Response built"),
    "no_sender": ("info", "completed", "deliver", "No sender available"),
    "model_selected": ("info", "dispatch", "model", "Model selected"),
    "model_failover": ("warning", "dispatch", "model", "Model failover"),
    "dispatch_failed": ("error", "failed", "dispatch", "AI core dispatch failed"),
    "delivery_failed": ("error", "failed", "deliver", "Response delivery failed"),
    "failed": ("error", "failed", "event", "Event failed"),
}


def _lifecycle_log_fields(status: str) -> tuple[str, str, str, str]:
    return _LIFECYCLE_LOG_FIELDS.get(status, ("info", status or "event", "event", status))


def _merge_internal_task_metadata(
    base_metadata: dict[str, Any],
    result: Any,
) -> dict[str, Any]:
    metadata = dict(base_metadata)
    if not isinstance(result, dict):
        metadata.setdefault("result_summary", "task completed")
        return metadata

    extra_metadata = result.get("metadata")
    if isinstance(extra_metadata, dict):
        metadata.update(extra_metadata)

    for key in ("content", "workflow_id", "response_preview", "context_target"):
        value = result.get(key)
        if value not in (None, ""):
            metadata.setdefault(key, value)

    for source_key in ("target_session_id", "session_id", "appended_session_id"):
        value = result.get(source_key)
        if value not in (None, ""):
            metadata.setdefault("target_session_id", value)
            break

    message_count = result.get("message_count")
    if not isinstance(message_count, int):
        messages_sent = result.get("messages_sent")
        if isinstance(messages_sent, int):
            message_count = messages_sent

    if isinstance(message_count, int):
        metadata.setdefault("message_count", message_count)
        metadata.setdefault(
            "result_summary",
            f"sent {message_count} message" if message_count == 1 else f"sent {message_count} messages",
        )

    if "result_summary" not in metadata:
        result_summary = result.get("result_summary")
        if isinstance(result_summary, str) and result_summary.strip():
            metadata["result_summary"] = result_summary.strip()
        else:
            metadata["result_summary"] = "task completed"

    return metadata


class ChannelGateway:
    """NekoBot 频道网关主类

    统一管理外部事件的接收、验证、路由、去重、调度和回复投递。
    支持可选的 SQLite 持久化和异步队列模式。
    """

    def __init__(
        self,
        *,
        router: GatewayRouter | None = None,
        security: SecurityProvider | None = None,
        dedupe_store: DedupeStore | None = None,
        rate_limiter: RateLimiter | None = None,
        dispatcher: GatewayDispatcher | None = None,
        delivery: GatewayDelivery | None = None,
        trace_factory: TraceFactory | None = None,
        storage: "GatewayStorage | None" = None,
        async_mode: bool = False,
        queue: EventQueue | None = None,
        worker: GatewayWorker | None = None,
    ):
        self.router = router or GatewayRouter()
        self.security = security or SecurityProvider(mode="none")
        self.trace_factory = trace_factory or TraceFactory()
        self.storage = storage
        self.async_mode = async_mode

        # 持久化组件：根据是否传入 storage 决定启用
        self.event_store: Any = None
        self.delivery_store_obj: Any = None

        if storage:
            from nbot.gateway.delivery_store import DeliveryStore
            from nbot.gateway.event_store import EventStore

            self.event_store = EventStore(storage)
            self.delivery_store_obj = DeliveryStore(storage)

            if dedupe_store is None:
                self.dedupe_store = DedupeStore(storage=storage)
                _log.info("[Gateway] 使用 SQLite 去重后端")
            else:
                self.dedupe_store = dedupe_store

            if delivery is None:
                self.delivery = GatewayDelivery(delivery_store=self.delivery_store_obj)
            else:
                self.delivery = delivery
        else:
            self.dedupe_store = dedupe_store or DedupeStore()
            self.delivery = delivery or GatewayDelivery()

        self.rate_limiter = rate_limiter or RateLimiter()
        self.dispatcher = dispatcher or GatewayDispatcher()

        # 统一日志服务
        self.log_service: Any = None
        if storage:
            try:
                from nbot.gateway.logs.service import GatewayLogService
                from nbot.gateway.logs.sqlite_store import SQLiteGatewayLogStore

                log_store = SQLiteGatewayLogStore(data_dir=storage.data_dir)
                self.log_service = GatewayLogService(log_store)
                print("[Gateway] 统一日志服务已启用", flush=True)
            except Exception as e:
                print(f"[Gateway] 统一日志服务初始化失败: {e}", flush=True)
        else:
            print("[Gateway] storage=None, 统一日志服务未启用", flush=True)

        # 异步模式组件
        self._queue = queue
        self._worker = worker

        if async_mode:
            self._queue = queue or EventQueue()
            _log.info("[Gateway] 异步模式已启用")

    @property
    def queue(self) -> EventQueue | None:
        return self._queue

    @property
    def worker(self) -> GatewayWorker | None:
        return self._worker

    async def start_worker(self) -> None:
        """启动异步 Worker"""
        if not self._worker and self._queue:
            from nbot.gateway.retry import RetryHandler

            self._worker = GatewayWorker(
                queue=self._queue,
                router=self.router,
                dispatcher=self.dispatcher,
                delivery=self.delivery,
                retry_handler=RetryHandler(),
                trace_factory=self.trace_factory,
                dedupe_store=self.dedupe_store,
                event_store=self.event_store,
            )
        if self._worker:
            await self._worker.start()

    async def stop_worker(self, *, graceful: bool = True) -> None:
        """停止异步 Worker"""
        if self._worker:
            await self._worker.stop(graceful=graceful)

    async def receive(
        self,
        *,
        channel_id: str,
        raw_event: dict[str, Any],
        headers: dict[str, str] | None = None,
        remote_addr: str = "",
        raw_body: str = "",
    ) -> GatewayResult:
        """接收并处理外部事件（核心入口方法）

        同步模式：完整 9 步链路，等待 AI 完成后返回
        异步模式：前 6 步同步完成，入队后立即返回，Worker 后台处理剩余步骤

        Args:
            channel_id: 频道标识符
            raw_event: 平台原始事件数据
            headers: HTTP 请求头
            remote_addr: 请求来源 IP
            raw_body: 原始请求体字符串（用于 HMAC 签名验证）

        Returns:
            GatewayResult 处理结果
        """
        trace_id = self.trace_factory.new_trace_id()
        headers = dict(headers or {})
        received_at = datetime.now().isoformat()
        print(f"[Gateway] receive() called channel={channel_id} log_service={'YES' if self.log_service else 'NO'}", flush=True)

        with trace_context(trace_id):
            _log.info(
                "[Gateway] 收到事件 trace=%s channel=%s addr=%s mode=%s",
                trace_id,
                channel_id,
                remote_addr or "local",
                "async" if self.async_mode else "sync",
            )

            # 记录事件：received
            self._record_event(
                trace_id=trace_id, channel_id=channel_id, status="received",
                raw_event=raw_event, remote_addr=remote_addr,
            )

            # === Step 1: 安全鉴权 ===
            try:
                await self.security.verify(
                    channel_id=channel_id,
                    raw_event=raw_event,
                    headers=headers,
                    remote_addr=remote_addr,
                    raw_body=raw_body,
                )
            except GatewayError as e:
                _log.warning(
                    "[Gateway] 鉴权失败 trace=%s channel=%s code=%s error=%s",
                    trace_id,
                    channel_id,
                    e.code,
                    e.message,
                )
                self._record_event(
                    trace_id=trace_id, channel_id=channel_id, status=e.code,
                    error=e.message,
                )
                return GatewayResult(
                    ok=False,
                    trace_id=trace_id,
                    channel_id=channel_id,
                    status=e.code,
                    error=e.message,
                )

            self._record_event(trace_id=trace_id, channel_id=channel_id, status="verified")

            # === Step 2: 限流检查（IP/频道维度）===
            try:
                await self.rate_limiter.check(
                    channel_id=channel_id,
                    remote_addr=remote_addr,
                )
            except GatewayError as e:
                _log.warning(
                    "[Gateway] 限流触发 trace=%s channel=%s error=%s",
                    trace_id,
                    channel_id,
                    e.message,
                )
                return GatewayResult(
                    ok=False,
                    trace_id=trace_id,
                    channel_id=channel_id,
                    status=e.code,
                    error=e.message,
                )

            # === Step 3: 路由到 Adapter ===
            adapter = self.router.get_adapter(channel_id)
            if not adapter:
                _log.warning("[Gateway] 未知频道 trace=%s channel=%s", trace_id, channel_id)
                return GatewayResult(
                    ok=False,
                    trace_id=trace_id,
                    channel_id=channel_id,
                    status="unknown_channel",
                    error=f"unknown channel: {channel_id}",
                )

            if not hasattr(adapter, "parse_event"):
                _log.warning(
                    "[Gateway] Adapter 缺少 parse_event trace=%s channel=%s",
                    trace_id,
                    channel_id,
                )
                return GatewayResult(
                    ok=False,
                    trace_id=trace_id,
                    channel_id=channel_id,
                    status="missing_parser",
                    error=f"channel {channel_id} has no parse_event method",
                )

            # === Step 4: 解析平台事件 ===
            try:
                parsed = adapter.parse_event(raw_event)
            except Exception as e:
                _log.error(
                    "[Gateway] 事件解析失败 trace=%s channel=%s error=%s",
                    trace_id,
                    channel_id,
                    str(e),
                )
                self._record_event(
                    trace_id=trace_id, channel_id=channel_id, status="parse_failed",
                    error=str(e), raw_event=raw_event,
                )
                return GatewayResult(
                    ok=True,
                    trace_id=trace_id,
                    channel_id=channel_id,
                    status="parse_failed",
                    error=f"parse error: {e}",
                )

            if not parsed:
                _log.debug("[Gateway] 忽略空事件 trace=%s channel=%s", trace_id, channel_id)
                self._record_event(trace_id=trace_id, channel_id=channel_id, status="ignored")
                return GatewayResult(
                    ok=True,
                    trace_id=trace_id,
                    channel_id=channel_id,
                    status="ignored",
                    ignored=True,
                )

            self._record_event(trace_id=trace_id, channel_id=channel_id, status="parsed")

            user_id = parsed.get("user_id") or ""
            conversation_id = parsed.get("conversation_id") or ""

            # === Step 5: 限流（用户/会话维度）===
            try:
                await self.rate_limiter.check(
                    channel_id=channel_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    remote_addr=remote_addr,
                )
            except GatewayError as e:
                self._record_event(
                    trace_id=trace_id, channel_id=channel_id, status="rate_limited",
                    error=e.message, user_id=user_id, conversation_id=conversation_id,
                )
                return GatewayResult(
                    ok=False,
                    trace_id=trace_id,
                    channel_id=channel_id,
                    status=e.code,
                    error=e.message,
                )

            # === Step 6: 消息去重（仅检查，不标记）===
            message_id = self._extract_message_id(channel_id, parsed)
            if message_id:
                is_dup = await self.dedupe_store.exists(message_id)
                if is_dup:
                    _log.info(
                        "[Gateway] 重复消息 trace=%s channel=%s msg_id=%s",
                        trace_id,
                        channel_id,
                        message_id,
                    )
                    self._record_event(
                        trace_id=trace_id, channel_id=channel_id, status="duplicated",
                        message_id=message_id,
                    )
                    return GatewayResult(
                        ok=True,
                        trace_id=trace_id,
                        channel_id=channel_id,
                        status="duplicated",
                        duplicated=True,
                    )

            self._record_event(trace_id=trace_id, channel_id=channel_id, status="deduped")

            # ========================
            # 分支：异步模式 vs 同步模式
            # ========================
            if self.async_mode and self._queue:
                return await self._receive_async(
                    trace_id=trace_id,
                    channel_id=channel_id,
                    raw_event=raw_event,
                    headers=headers,
                    remote_addr=remote_addr,
                    received_at=received_at,
                    adapter=adapter,
                    parsed=parsed,
                    message_id=message_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                )

            # === 同步模式：继续 Steps 7-9 ===
            return await self._receive_sync(
                trace_id=trace_id,
                channel_id=channel_id,
                raw_event=raw_event,
                headers=headers,
                remote_addr=remote_addr,
                received_at=received_at,
                adapter=adapter,
                parsed=parsed,
                message_id=message_id,
                user_id=user_id,
                conversation_id=conversation_id,
            )

    async def _receive_async(
        self,
        *,
        trace_id: str,
        channel_id: str,
        raw_event: dict[str, Any],
        headers: dict[str, str],
        remote_addr: str,
        received_at: str,
        adapter,
        parsed: dict[str, Any],
        message_id: str,
        user_id: str,
        conversation_id: str,
    ) -> GatewayResult:
        """异步模式：入队后立即返回，Worker 后台处理"""

        # 构建队列项
        item = QueueItem(
            trace_id=trace_id,
            channel_id=channel_id,
            raw_event=raw_event,
            headers=headers,
            remote_addr=remote_addr,
            parsed_data=parsed,
        )

        # 入队
        enqueued = await self._queue.enqueue(item)

        if not enqueued:
            _log.error("[Gateway] 队列已满，丢弃事件 trace=%s", trace_id)
            self._record_event(
                trace_id=trace_id, channel_id=channel_id, status="queue_full",
            )
            return GatewayResult(
                ok=False,
                trace_id=trace_id,
                channel_id=channel_id,
                status="queue_full",
                error="event queue is full",
            )

        # 记录事件：queued（dedupe 标记推迟到 Worker 处理成功后）
        self._record_event(trace_id=trace_id, channel_id=channel_id, status="queued")

        _log.info(
            "[Gateway] 事件已入队 trace=%s channel=%s queue_size=%d",
            trace_id,
            channel_id,
            self._queue.size,
        )

        return GatewayResult(
            ok=True,
            trace_id=trace_id,
            channel_id=channel_id,
            status="queued",
            queued=True,
            data={
                "item_id": item.item_id,
                "queue_size": self._queue.size,
            },
        )

    async def _receive_sync(
        self,
        *,
        trace_id: str,
        channel_id: str,
        raw_event: dict[str, Any],
        headers: dict[str, str],
        remote_addr: str,
        received_at: str,
        adapter,
        parsed: dict[str, Any],
        message_id: str,
        user_id: str,
        conversation_id: str,
    ) -> GatewayResult:
        """同步模式：完整处理链路（Steps 7-9）"""

        # === Step 7: 构建 ChatRequest ===
        try:
            # 只提取 build_chat_request() 接受的参数
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
            _log.error(
                "[Gateway] ChatRequest 构建失败 trace=%s channel=%s error=%s",
                trace_id,
                channel_id,
                str(e),
            )
            self._record_event(
                trace_id=trace_id, channel_id=channel_id,
                status="build_request_failed", error=str(e),
            )
            return GatewayResult(
                ok=False,
                trace_id=trace_id,
                channel_id=channel_id,
                status="build_request_failed",
                error=f"build chat request failed: {e}",
            )

        gateway_event = GatewayEvent(
            trace_id=trace_id,
            channel_id=channel_id,
            event_type="message",
            raw_event=raw_event,
            headers=headers,
            remote_addr=remote_addr,
            received_at=received_at,
            message_id=message_id,
            conversation_id=chat_request.conversation_id,
            user_id=chat_request.user_id,
            content=chat_request.content,
            sender=chat_request.sender,
        )

        self._record_event(
            trace_id=trace_id, channel_id=channel_id, status="dispatched",
            conversation_id=chat_request.conversation_id,
            user_id=user_id, message_id=message_id,
        )

        # === Step 8: 调度到 AI Core ===
        start_time = time.time()
        try:
            chat_response = await self.dispatcher.dispatch(chat_request, adapter=adapter)
        except GatewayError as e:
            elapsed = time.time() - start_time
            _log.error(
                "[Gateway] AI Core 处理失败 trace=%s channel=%s耗时=%.2fs error=%s",
                trace_id,
                channel_id,
                elapsed,
                e.message,
            )
            self._record_event(
                trace_id=trace_id, channel_id=channel_id, status=e.code,
                error=e.message, conversation_id=chat_request.conversation_id,
            )
            return GatewayResult(
                ok=False,
                trace_id=trace_id,
                channel_id=channel_id,
                conversation_id=chat_request.conversation_id,
                status=e.code,
                error=e.message,
            )
        except Exception as e:
            elapsed = time.time() - start_time
            _log.error(
                "[Gateway] AI Core 异常 trace=%s channel=%s耗时=%.2fs error=%s",
                trace_id,
                channel_id,
                elapsed,
                str(e),
            )
            self._record_event(
                trace_id=trace_id, channel_id=channel_id,
                status="dispatch_failed", error=str(e),
                conversation_id=chat_request.conversation_id,
            )
            return GatewayResult(
                ok=False,
                trace_id=trace_id,
                channel_id=channel_id,
                conversation_id=chat_request.conversation_id,
                status="dispatch_failed",
                error=f"AI core exception: {e}",
            )

        self._record_event(
            trace_id=trace_id, channel_id=channel_id, status="delivering",
            conversation_id=chat_request.conversation_id,
        )

        # 记录模型信息和故障转移事件到 Gateway 日志
        resp_metadata = getattr(chat_response, "metadata", None) or {}
        used_model_id = resp_metadata.get("model_id", "")
        used_model_name = resp_metadata.get("model_name", "")
        failover_events = resp_metadata.get("failover_events", [])
        model_info = {}
        if used_model_id:
            model_info["model_id"] = used_model_id
        if used_model_name:
            model_info["model_name"] = used_model_name
        if model_info:
            self._record_event(
                trace_id=trace_id, channel_id=channel_id, status="model_selected",
                conversation_id=chat_request.conversation_id,
                metadata=model_info,
            )
        for ev in failover_events:
            self._record_event(
                trace_id=trace_id, channel_id=channel_id, status="model_failover",
                conversation_id=chat_request.conversation_id,
                metadata={
                    "failed_model_id": ev.get("model_id", ""),
                    "failed_model_name": ev.get("model_name", ""),
                    "status_code": ev.get("status_code", 0),
                    "category": ev.get("category", ""),
                },
            )

        # === Step 9: 投递回复 ===
        try:
            delivery_result = await self.delivery.send_response(
                channel_id=channel_id,
                chat_request=chat_request,
                chat_response=chat_response,
                trace_id=trace_id,
                metadata={"gateway_event": gateway_event.to_dict()},
            )
        except GatewayError as e:
            _log.error(
                "[Gateway] 回复投递失败 trace=%s channel=%s error=%s",
                trace_id,
                channel_id,
                e.message,
            )
            self._record_event(
                trace_id=trace_id, channel_id=channel_id, status="delivery_failed",
                error=e.message, conversation_id=chat_request.conversation_id,
            )
            return GatewayResult(
                ok=True,
                trace_id=trace_id,
                channel_id=channel_id,
                conversation_id=chat_request.conversation_id,
                status="delivery_failed",
                error=e.message,
                data={"response_content": chat_response.final_content},
            )

        total_elapsed = time.time() - start_time
        delivery_status = delivery_result.get("status", "unknown")

        # 根据 delivery 实际状态决定 Gateway 最终状态
        if delivery_status == "delivered":
            final_status = "delivered"
            should_mark_dedupe = True
        elif delivery_status == "built":
            final_status = "built"
            should_mark_dedupe = True  # Web/内部频道可以 mark
        elif delivery_status == "no_sender":
            final_status = "no_sender"
            should_mark_dedupe = False  # 外部频道没有 sender，不要 mark
        else:
            final_status = "delivery_failed"
            should_mark_dedupe = False

        _log.info(
            "[Gateway] 处理完成 trace=%s channel=%s conv=%s status=%s耗时=%.2fs",
            trace_id,
            channel_id,
            chat_request.conversation_id,
            final_status,
            total_elapsed,
        )

        self._record_event(
            trace_id=trace_id, channel_id=channel_id, status=final_status,
            conversation_id=chat_request.conversation_id,
        )

        # 同步模式：只有真正成功或 built 后才标记去重
        if message_id and should_mark_dedupe:
            await self.dedupe_store.mark(
                message_id,
                channel_id=channel_id,
                message_id=message_id.split(":")[-1] if ":" in message_id else "",
            )

        return GatewayResult(
            ok=final_status in ("delivered", "built"),
            trace_id=trace_id,
            channel_id=channel_id,
            conversation_id=chat_request.conversation_id,
            status=final_status,
            data={
                "delivery": delivery_result,
                "response_content": chat_response.final_content,
            },
        )

    async def submit_internal_task(
        self,
        *,
        task_kind: str,
        task_id: str,
        handler,
        task_name: str = "",
        trigger_source: str = "system",
        channel_id: str = "internal",
        conversation_id: str = "",
        user_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> GatewayResult:
        """Submit an internal scheduled task through Gateway tracing."""
        trace_id = self.trace_factory.new_trace_id()
        base_metadata = {
            "task_kind": task_kind,
            "task_id": task_id,
            "task_name": task_name,
            "trigger_source": trigger_source,
        }
        if metadata:
            base_metadata.update(metadata)

        raw_event = {
            "task_kind": task_kind,
            "task_id": task_id,
            "task_name": task_name,
            "trigger_source": trigger_source,
        }

        with trace_context(trace_id):
            self._record_event(
                trace_id=trace_id,
                channel_id=channel_id,
                status="received",
                conversation_id=conversation_id,
                user_id=user_id,
                raw_event=raw_event,
                event_type="internal_task",
                metadata=base_metadata,
            )
            self._record_event(
                trace_id=trace_id,
                channel_id=channel_id,
                status="dispatched",
                conversation_id=conversation_id,
                user_id=user_id,
                event_type="internal_task",
                metadata=base_metadata,
            )

            try:
                result = handler()
                if inspect.isawaitable(result):
                    result = await result

                completion_metadata = _merge_internal_task_metadata(base_metadata, result)

                self._record_event(
                    trace_id=trace_id,
                    channel_id=channel_id,
                    status="completed",
                    conversation_id=conversation_id,
                    user_id=user_id,
                    raw_event=raw_event,
                    event_type="internal_task",
                    metadata=completion_metadata,
                )
                return GatewayResult(
                    ok=True,
                    trace_id=trace_id,
                    channel_id=channel_id,
                    conversation_id=conversation_id,
                    status="completed",
                    data={
                        "task_kind": task_kind,
                        "task_id": task_id,
                        "task_name": task_name,
                        "result": result if isinstance(result, dict) else {"value": result},
                    },
                )
            except Exception as e:
                self._record_event(
                    trace_id=trace_id,
                    channel_id=channel_id,
                    status="failed",
                    conversation_id=conversation_id,
                    user_id=user_id,
                    raw_event=raw_event,
                    error=str(e),
                    event_type="internal_task",
                    metadata=base_metadata,
                )
                return GatewayResult(
                    ok=False,
                    trace_id=trace_id,
                    channel_id=channel_id,
                    conversation_id=conversation_id,
                    status="failed",
                    error=str(e),
                    data={
                        "task_kind": task_kind,
                        "task_id": task_id,
                        "task_name": task_name,
                    },
                )

    def submit_internal_task_sync(self, **kwargs: Any) -> GatewayResult:
        """Synchronous wrapper for internal task submission."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.submit_internal_task(**kwargs))
        raise RuntimeError("submit_internal_task_sync cannot run inside an active event loop")

    def record_lifecycle_event(
        self,
        *,
        trace_id: str,
        channel_id: str,
        status: str,
        event_type: str = "message",
        conversation_id: str = "",
        user_id: str = "",
        message_id: str = "",
        raw_event: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        error: str = "",
        action: str = "",
        level: str = "",
        stage: str = "",
        message: str = "",
    ) -> None:
        """Record one gateway lifecycle state to both legacy events and unified logs."""
        self._record_event(
            trace_id=trace_id,
            channel_id=channel_id,
            status=status,
            conversation_id=conversation_id,
            user_id=user_id,
            message_id=message_id,
            raw_event=raw_event,
            error=error,
            event_type=event_type,
            metadata=metadata,
        )

        default_level, default_stage, default_action, default_message = (
            _lifecycle_log_fields(status)
        )

    # 状态 → (action, stage, level) 映射
    _EVENT_STATUS_MAP: dict[str, tuple[str, str, str]] = {
        "received": ("receive", "receive_start", "info"),
        "verified": ("verify", "auth_passed", "info"),
        "rate_limited": ("rate_limit", "rate_limited", "warning"),
        "unknown_channel": ("route", "route_failed", "warning"),
        "missing_parser": ("route", "route_failed", "warning"),
        "parsed": ("parse", "parsed", "info"),
        "parse_failed": ("parse", "parse_failed", "error"),
        "ignored": ("parse", "ignored", "info"),
        "duplicated": ("dedupe", "dedupe_hit", "info"),
        "deduped": ("dedupe", "deduped", "info"),
        "queued": ("queue", "queued", "info"),
        "queue_full": ("queue", "queue_failed", "error"),
        "dispatched": ("dispatch", "dispatched", "info"),
        "delivering": ("deliver", "delivering", "info"),
        "delivered": ("deliver", "completed", "info"),
        "built": ("deliver", "completed", "info"),
        "no_sender": ("deliver", "completed", "info"),
        "delivery_failed": ("deliver", "delivery_failed", "error"),
        "dispatch_failed": ("dispatch", "dispatch_failed", "error"),
        "build_request_failed": ("dispatch", "build_failed", "error"),
        "model_selected": ("dispatch", "dispatched", "info"),
        "model_failover": ("dispatch", "dispatched", "warning"),
    }

    def _record_event(
        self,
        *,
        trace_id: str,
        channel_id: str,
        status: str,
        conversation_id: str = "",
        user_id: str = "",
        message_id: str = "",
        raw_event: dict[str, Any] | None = None,
        error: str = "",
        remote_addr: str = "",
        event_type: str = "message",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """记录事件状态变更到统一日志 gateway_logs"""
        if not self.log_service:
            return
        action, stage, level = self._EVENT_STATUS_MAP.get(status, ("event", "", "info"))
        merged_meta = dict(metadata or {})
        if remote_addr:
            merged_meta.setdefault("remote_addr", remote_addr)
        try:
            self.log_service.record(
                source="gateway",
                type=event_type or "message",
                action=action,
                status=status,
                message=status,
                level=level,
                stage=stage,
                trace_id=trace_id,
                channel_id=channel_id or None,
                conversation_id=conversation_id or None,
                user_id=user_id or None,
                message_id=message_id or None,
                error_message=error or None,
                metadata=merged_meta or None,
            )
        except Exception as e:
            _log.debug("[Gateway] 事件记录失败 trace=%s status=%s error=%s", trace_id, status, str(e))

    def _record_log(
        self,
        *,
        action: str,
        status: str,
        log_type: str = "receive",
        message: str = "",
        level: str = "info",
        stage: str = "",
        trace_id: str | None = None,
        channel_id: str | None = None,
        conversation_id: str | None = None,
        user_id: str | None = None,
        message_id: str | None = None,
        queue_item_id: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """写入统一日志（委托给 _record_event）"""
        self._record_event(
            trace_id=trace_id or "",
            channel_id=channel_id or "",
            status=status,
            conversation_id=conversation_id or "",
            user_id=user_id or "",
            message_id=message_id or "",
            error=error_message or "",
            event_type=log_type,
            metadata=metadata,
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
        """获取 Gateway 运行统计信息"""
        stats: dict[str, Any] = {
            "mode": "async" if self.async_mode else "sync",
            "dedupe_backend": self.dedupe_store.backend_name,
            "has_persistence": self.storage is not None,
            "has_event_store": self.event_store is not None,
            "has_delivery_store": self.delivery_store_obj is not None,
            "has_worker": self._worker is not None,
        }
        if self.storage:
            stats.update(self.storage.get_stats())
        if self._queue:
            stats["queue"] = self._queue.get_stats()
        if self._worker:
            stats["worker"] = self._worker.get_stats()
        return stats


def create_gateway(**kwargs) -> ChannelGateway:
    """工厂函数：创建配置好的 ChannelGateway 实例"""
    return ChannelGateway(**kwargs)


def create_async_gateway(**kwargs) -> ChannelGateway:
    """工厂函数：创建异步模式的 Gateway 实例

    启用异步队列，Webhook 收到事件后快速入队并返回 200，
    由后台 Worker 完成 AI 调度和回复投递。
    """
    return ChannelGateway(async_mode=True, **kwargs)


def create_gateway_with_storage(
    data_dir: str = "",
    **kwargs,
) -> ChannelGateway:
    """工厂函数：创建带 SQLite 持久化的 Gateway 实例"""
    from nbot.gateway.storage import init_gateway_storage

    storage = init_gateway_storage(data_dir=data_dir)
    return ChannelGateway(storage=storage, **kwargs)


def create_async_gateway_with_storage(data_dir: str = "", **kwargs) -> ChannelGateway:
    """工厂函数：创建带持久化的异步模式 Gateway"""
    from nbot.gateway.storage import init_gateway_storage

    storage = init_gateway_storage(data_dir=data_dir)
    return ChannelGateway(async_mode=True, storage=storage, **kwargs)


def create_gateway_from_config(config: dict[str, Any]) -> ChannelGateway:
    """从配置字典创建 Gateway 实例"""
    gateway_config = config.get("gateway", {})

    security = build_security_provider(config)

    rate_limit_cfg = gateway_config.get("rate_limit", {})
    from nbot.gateway.rate_limit import MemoryRateLimiter, RateLimitConfig

    rate_config = RateLimitConfig(
        per_user_per_minute=rate_limit_cfg.get("per_user_per_minute", 20),
        per_conversation_per_minute=rate_limit_cfg.get("per_conversation_per_minute", 60),
        per_ip_per_minute=rate_limit_cfg.get("per_ip_per_minute", 60),
        per_channel_per_minute=rate_limit_cfg.get("per_channel_per_minute", 300),
    )
    rate_limiter = RateLimiter(MemoryRateLimiter(rate_config))

    enable_storage = gateway_config.get("storage", {}).get("enabled", False)
    enable_async = gateway_config.get("async", {}).get("enabled", False)
    data_dir = config.get("data_dir", "")

    if enable_async and enable_storage:
        return create_async_gateway_with_storage(
            data_dir=data_dir,
            security=security,
            rate_limiter=rate_limiter,
        )
    elif enable_async:
        return create_async_gateway(
            security=security,
            rate_limiter=rate_limiter,
        )
    elif enable_storage:
        return create_gateway_with_storage(
            data_dir=data_dir,
            security=security,
            rate_limiter=rate_limiter,
        )

    return ChannelGateway(
        security=security,
        rate_limiter=rate_limiter,
    )


# ============================
# 全局 Gateway 实例管理
# ============================

_global_gateway_instance: "ChannelGateway | None" = None


def get_gateway() -> "ChannelGateway | None":
    """获取全局 Gateway 实例"""
    return _global_gateway_instance


def set_gateway(gateway: "ChannelGateway | None") -> None:
    """设置全局 Gateway 实例（用于依赖注入）

    Args:
        gateway: 已配置好的 ChannelGateway 实例
    """
    global _global_gateway_instance
    _global_gateway_instance = gateway
