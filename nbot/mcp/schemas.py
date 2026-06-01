"""MCP 输入输出模型

使用 Pydantic 定义 MCP Tools 和 Resources 的输入输出 Schema。
"""

from pydantic import BaseModel, Field


# ========================
# Gateway Tools
# ========================


class GatewayGetStatusInput(BaseModel):
    """gateway_get_status 输入（无参数）"""
    pass


class GatewayGetStatusOutput(BaseModel):
    """gateway_get_status 输出"""
    ok: bool
    mode: str
    storage: str
    worker_running: bool
    queue: dict


class GatewayGetStatsInput(BaseModel):
    """gateway_get_stats 输入（无参数）"""
    pass


class GatewayGetStatsOutput(BaseModel):
    """gateway_get_stats 输出"""
    ok: bool
    events: dict
    deliveries: dict
    dedupe: dict
    queue: dict


# ========================
# Trace & Event Tools
# ========================


class QueryTraceInput(BaseModel):
    """gateway_query_trace 输入"""
    trace_id: str = Field(..., min_length=1, max_length=128, description="Gateway trace id")


class GatewayEventItem(BaseModel):
    """事件条目"""
    status: str
    channel_id: str
    created_at: str
    trace_id: str | None = None
    conversation_id: str | None = None
    user_id: str | None = None
    message_id: str | None = None
    event_type: str | None = None
    error: str | None = None
    metadata: dict | None = None


class QueryTraceOutput(BaseModel):
    """gateway_query_trace 输出"""
    ok: bool
    trace_id: str
    events: list[GatewayEventItem]


class QueryEventsInput(BaseModel):
    """gateway_query_events 输入"""
    channel_id: str = Field(default="", description="频道 ID 筛选")
    status: str = Field(default="", description="状态筛选 (failed, delivered, etc.)")
    event_type: str = Field(default="", description="事件类型筛选")
    limit: int = Field(default=50, ge=1, le=200, description="返回数量上限")


class QueryEventsOutput(BaseModel):
    """gateway_query_events 输出"""
    ok: bool
    items: list[GatewayEventItem]


# ========================
# Delivery Tools
# ========================


class QueryDeliveriesInput(BaseModel):
    """gateway_query_deliveries 输入"""
    trace_id: str = Field(default="", description="按 trace_id 查询")
    channel_id: str = Field(default="", description="频道 ID 筛选")
    status: str = Field(default="", description="状态筛选 (failed, dead, etc.)")
    limit: int = Field(default=20, ge=1, le=100, description="返回数量上限")


class DeliveryItem(BaseModel):
    """投递记录条目"""
    id: int | None = None
    trace_id: str | None = None
    channel_id: str | None = None
    conversation_id: str | None = None
    status: str | None = None
    attempts: int | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class QueryDeliveriesOutput(BaseModel):
    """gateway_query_deliveries 输出"""
    ok: bool
    items: list[DeliveryItem]


# ========================
# Queue Tools
# ========================


class GetQueueStatsInput(BaseModel):
    """gateway_get_queue_stats 输入（无参数）"""
    pass


class GetQueueStatsOutput(BaseModel):
    """gateway_get_queue_stats 输出"""
    ok: bool
    enqueued: int
    completed: int
    failed: int
    dead: int
    status_breakdown: dict


class RetryDeadLetterInput(BaseModel):
    """gateway_retry_dead_letter 输入"""
    item_id: str = Field(..., min_length=1, max_length=128, description="死信队列项 ID")


class RetryDeadLetterOutput(BaseModel):
    """gateway_retry_dead_letter 输出"""
    ok: bool
    item_id: str
    status: str | None = None
    error: str | None = None


# ========================
# Message Tools
# ========================


class ReceiveMessageInput(BaseModel):
    """gateway_receive_message 输入"""
    channel_id: str = Field(..., min_length=1, max_length=64, description="频道标识符 (qq, web, telegram, etc.)")
    raw_event: dict = Field(..., min_length=1, description="平台原始事件数据（非空 dict）")
    headers: dict | None = Field(default=None, description="HTTP 请求头")
    remote_addr: str = Field(default="127.0.0.1", max_length=45, description="请求来源 IP")


class ReceiveMessageOutput(BaseModel):
    """gateway_receive_message 输出"""
    ok: bool
    trace_id: str
    status: str
    queued: bool | None = None
    error: str | None = None


class SendMessageInput(BaseModel):
    """gateway_send_message 输入"""
    channel_id: str = Field(..., min_length=1, max_length=64, description="频道标识符")
    conversation_id: str = Field(..., min_length=1, max_length=128, description="会话 ID")
    content: str = Field(..., min_length=1, max_length=8000, description="消息内容")
    metadata: dict | None = Field(default=None, description="附加元数据")


class SendMessageOutput(BaseModel):
    """gateway_send_message 输出"""
    ok: bool
    trace_id: str | None = None
    status: str | None = None
    error: str | None = None


# ========================
# Internal Task Tools
# ========================


class SubmitInternalTaskInput(BaseModel):
    """gateway_submit_internal_task 输入"""
    task_kind: str = Field(..., min_length=1, max_length=64, description="任务类型 (heartbeat, workflow, cron, custom)")
    task_id: str = Field(..., min_length=1, max_length=128, description="任务 ID")
    trigger_source: str = Field(default="mcp", max_length=32, description="触发来源")
    metadata: dict | None = Field(default=None, description="附加元数据")


class SubmitInternalTaskOutput(BaseModel):
    """gateway_submit_internal_task 输出"""
    ok: bool
    trace_id: str
    status: str
    error: str | None = None


# ========================
# Node Tools
# ========================


class ListNodesInput(BaseModel):
    """gateway_list_nodes 输入"""
    node_type: str = Field(default="", description="节点类型筛选 (gateway, worker, channel)")
    status: str = Field(default="", description="状态筛选 (online, busy, idle, offline)")


class NodeInfoItem(BaseModel):
    """节点信息"""
    node_id: str
    node_type: str
    status: str
    version: str | None = None
    address: str | None = None
    current_load: float | None = None
    last_heartbeat: float | None = None


class ListNodesOutput(BaseModel):
    """gateway_list_nodes 输出"""
    ok: bool
    nodes: list[NodeInfoItem]


class GetNodeInput(BaseModel):
    """gateway_get_node 输入"""
    node_id: str = Field(..., min_length=1, max_length=128, description="节点 ID")


class GetNodeOutput(BaseModel):
    """gateway_get_node 输出"""
    ok: bool
    node: NodeInfoItem | None = None
    error: str | None = None


class RegisterNodeInput(BaseModel):
    """gateway_register_node 输入"""
    node_id: str = Field(..., min_length=1, max_length=128, description="节点 ID")
    node_type: str = Field(default="worker", max_length=32, description="节点类型")
    version: str = Field(default="", max_length=32, description="版本号")
    address: str = Field(default="", max_length=256, description="节点地址")
    metadata: dict | None = Field(default=None, description="附加元数据")


class RegisterNodeOutput(BaseModel):
    """gateway_register_node 输出"""
    ok: bool
    node_id: str | None = None
    error: str | None = None


# ========================
# Capability
# ========================


class CapabilityManifest(BaseModel):
    """能力清单"""
    tools: list[str]
    resources: list[str]
    permissions: list[str]
    node_capabilities: list[dict] | None = None
