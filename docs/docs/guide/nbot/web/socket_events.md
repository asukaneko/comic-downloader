# socket_events - Socket.IO 事件系统

## 概述

`socket_events.py` 是 NekoBot Web 后台的实时通信层，基于 Flask-SocketIO 实现客户端与服务器的双向消息推送。所有 Web 面板的聊天、命令、流式输出、执行确认等交互均通过此模块转发。

## 连接生命周期

```python
@server.socketio.on("connect")
def handle_connect(auth=None):
    token = extract_token(auth, request)
    username = server._validate_login_token(token)
    if not username:
        return False
    server.web_users[request.sid] = user_id
```

Token 支持四种传递方式：`auth` 参数、`Authorization: Bearer` 头、`X-Auth-Token` / `X-Token` 头、`nbot_auth_token` Cookie。
@server.socketio.on("disconnect")
def handle_disconnect():
    server.web_users.pop(request.sid, "unknown")
    session_id = server.active_connections.pop(request.sid, None)
    if session_id:
        leave_room(session_id)
```

断开时自动清理用户映射和可见会话列表，并离开已加入的会话房间。

## 会话管理事件

```python
@server.socketio.on("join_session")
def handle_join_session(data):
    session_id = data.get("session_id")
    if not session_store.get_session(session_id):
        disk_session = get_session_from_db(server.data_dir, session_id)
        if disk_session:
            session_store.set_session(session_id, disk_session)
    if session_store.get_session(session_id):
        join_room(session_id)
        server.active_connections[request.sid] = session_id
        emit("joined_session", {"session_id": session_id})
```

加入会话时优先从内存查找，未命中则从 SQLite 磁盘加载。

```python
@server.socketio.on("leave_session")
def handle_leave_session():
    session_id = server.active_connections.pop(request.sid, None)
    server.visible_web_sessions.pop(request.sid, None)
    if session_id:
        leave_room(session_id)
```

### 可见性管理

```python
@server.socketio.on("web_visibility")
def handle_web_visibility(data):
    session_id = (data or {}).get("session_id")
    visible = bool((data or {}).get("visible"))
    visible_sessions = getattr(server, "visible_web_sessions", None)
    if visible and session_id:
        visible_sessions[request.sid] = session_id
    else:
        visible_sessions.pop(request.sid, None)
```

`web_visibility` 标记前端当前会话，`persistence.py` 据此过滤 Web API 可见范围。

## 消息传递

```python
@server.socketio.on("send_message")
def handle_send_message(data):
    session_id = data.get("session_id")
    raw_content = data.get("content", "")
    sender = data.get("sender", "web_user")

    if server.sessions.get(session_id, {}).get("read_only"):
        emit("error", {"message": "此会话为只读归档，无法发送消息"})
        return

    content = adapter.normalize_inbound_message(raw_content)
    attachments = adapter.normalize_attachments(data.get("attachments", []))
```

消息处理流程：

1. **只读检查** — 归档会话禁止发送
2. **规范化** — 通过 `WebChannelAdapter` 标准化消息和附件
3. **命令匹配** — 以 `/` 开头的消息尝试匹配命令处理器
4. **构建 ChatRequest** — 封装为统一请求格式，传入 AI 管线
5. **广播消息** — 通过 `new_message` 事件推送给会话房间
6. **触发 AI 响应** — 调用 `_trigger_ai_response()` 启动异步推理

```python
    chat_request = adapter.build_chat_request(
        conversation_id=session_id, content=content, sender=sender,
    )
    message = adapter.build_message(role="user", content=chat_request.content, ...)
    session_store.append_message(session_id, message)
    server.socketio.emit("new_message", message, room=session_id)

    server._trigger_ai_response(
        chat_request.conversation_id, chat_request.content,
        chat_request.sender, chat_request.attachments, parent_msg_id,
    )
```

### 流式输出

前端通过以下三个事件接收流式回复：

| 事件 | 说明 |
|------|------|
| `ai_stream_start` | 流开始，附带完整 message 对象 |
| `ai_stream_chunk` | 逐块文本，含 `chunk`、`message_id`、`is_end` |
| `ai_stream_end` | 流结束，标记 `is_end: true` |

### 流式调试

```python
@server.socketio.on("debug_stream_demo")
def handle_debug_stream_demo(data):
    """向调用者发送合成流，用于前端流式渲染的时序测试。"""
    text = data.get("text") or "默认测试文本..."
    chunk_size = max(1, min(int(data.get("chunk_size", 4)), 80))
    delay_ms = max(0, min(int(data.get("delay_ms", 60)), 2000))
```

## 执行确认

```python
@server.socketio.on("confirm_exec")
def handle_confirm_exec(data):
    request_id = data.get("request_id", "")
    approved = data.get("approved", False)
    session_id = data.get("session_id", "")

    if approved:
        exec_result = execute_pending_command(request_id)
        result = f"已确认并执行命令\n退出码：{exec_result.get('returncode')}"
    else:
        reject_result = reject_pending_command(request_id)
        result = f"已取消执行命令：`{reject_result.get('command', '')}`"

    session_store.append_message(effective_session_id, {
        "id": f"exec_ctx_{request_id}", "role": "system", "content": result,
    })
    server.socketio.emit("exec_confirm_result", {
        "session_id": effective_session_id, "approved": approved,
    }, room=request.sid)

    server._trigger_ai_response(effective_session_id, "请根据执行结果继续", "system")
```

处理流程：

1. 接收确认/拒绝指令，调用 `execute_pending_command()` 或 `reject_pending_command()`
2. 将执行结果作为 `system` 角色消息追加到会话上下文
3. 发送 `exec_confirm_result` 事件清除前端加载状态
4. 触发 AI 管线继续对话

## 其他事件

| 事件 | 说明 |
|------|------|
| `typing` | 转发 `user_typing` 到同会话房间 |

## 数据流汇总

```
客户端          Socket.IO 服务端          AI管线
  │                │                      │
  ├─ connect ─────→│ 验证 Token           │
  ├─ join_session →│ 加入房间，加载会话    │
  ├─ send_message →│ 构建 ChatRequest ───→│
  │← new_message ──┤ 广播用户消息         │
  │← ai_stream_* ──┤←─────── 流式输出     │
  ├─ confirm_exec →│ 执行/拒绝命令 ──────→│
  │← exec_confirm ─┤ 通知前端结果         │
```

## 错误处理

```python
except Exception as e:
    _log.error(f"Failed to handle Web message: {e}", exc_info=True)
    server.socketio.emit(
        "error", {"message": f"Message handling failed: {str(e)}"}, room=request.sid
    )
```

所有事件处理器捕获异常后通过 `error` 事件推送至前端。认证失败直接返回 `False`，Socket.IO 自动断开。