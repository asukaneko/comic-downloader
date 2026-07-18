import asyncio
import hashlib
import logging
import uuid
from datetime import datetime

from flask import request
from flask_socketio import emit, join_room, leave_room

from nbot.channels.registry import get_channel_adapter
from nbot.channels.web import WebChannelAdapter
from nbot.core import WebSessionStore
from nbot.web.message_adapter import WebMessageAdapter
from nbot.web.sessions_db import get_session as get_session_from_db

_log = logging.getLogger(__name__)


def register_socket_events(server):
    session_store = WebSessionStore(
        server.sessions, save_callback=lambda: server._save_data("sessions")
    )
    adapter = getattr(server, "web_channel_adapter", None) or get_channel_adapter("web") or WebChannelAdapter()

    @server.socketio.on("connect")
    def handle_connect(auth=None):
        token = ""
        if isinstance(auth, dict):
            token = str(auth.get("token") or "").strip()

        if not token:
            auth_header = request.headers.get("Authorization", "").strip()
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:].strip()

        if not token:
            token = (
                request.headers.get("X-Auth-Token", "").strip()
                or request.headers.get("X-Token", "").strip()
                or request.cookies.get("nbot_auth_token", "").strip()
            )

        username = server._validate_login_token(token)
        if not username:
            _log.warning("Rejected unauthenticated WebSocket connection")
            return False

        user_id = request.args.get("user_id", "web_user")
        server.web_users[request.sid] = user_id
        server.active_connections[f"auth:{request.sid}"] = username
        _log.info(f"Web client connected: {user_id}")

    @server.socketio.on("disconnect")
    def handle_disconnect():
        user_id = server.web_users.pop(request.sid, "unknown")
        server.active_connections.pop(f"auth:{request.sid}", None)
        getattr(server, "visible_web_sessions", {}).pop(request.sid, None)
        session_id = server.active_connections.pop(request.sid, None)
        if session_id:
            leave_room(session_id)
        _log.info(f"Web client disconnected: {user_id}")

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
            server.socketio.emit(
                "joined_session", {"session_id": session_id}, room=request.sid
            )
        else:
            _log.warning(f"Client tried to join non-existent session: {session_id}")

    @server.socketio.on("leave_session")
    def handle_leave_session():
        session_id = server.active_connections.pop(request.sid, None)
        getattr(server, "visible_web_sessions", {}).pop(request.sid, None)
        if session_id:
            leave_room(session_id)

    @server.socketio.on("web_visibility")
    def handle_web_visibility(data):
        session_id = (data or {}).get("session_id")
        visible = bool((data or {}).get("visible"))
        visible_sessions = getattr(server, "visible_web_sessions", None)
        if visible_sessions is None:
            server.visible_web_sessions = {}
            visible_sessions = server.visible_web_sessions
        if visible and session_id:
            visible_sessions[request.sid] = session_id
        else:
            visible_sessions.pop(request.sid, None)

    @server.socketio.on("debug_stream_demo")
    def handle_debug_stream_demo(data):
        """Emit a synthetic stream to the caller for frontend timing tests."""
        payload = data or {}
        target_sid = request.sid
        text = str(payload.get("text") or "").strip()
        if not text:
            text = (
                "This is a synthetic streaming demo. "
                "Each fragment should appear in the chat bubble as it arrives, "
                "and the skeleton should disappear after the first visible token. "
                "If everything arrives at once, the flush or frontend queue is still blocked."
            )

        try:
            chunk_size = int(payload.get("chunk_size") or 4)
        except (TypeError, ValueError):
            chunk_size = 4
        try:
            delay_ms = int(payload.get("delay_ms") or 60)
        except (TypeError, ValueError):
            delay_ms = 60

        chunk_size = max(1, min(chunk_size, 80))
        delay_seconds = max(0, min(delay_ms, 2000)) / 1000
        session_id = str(payload.get("session_id") or f"debug-stream-{target_sid}")
        message_id = str(uuid.uuid4())
        message = {
            "id": message_id,
            "role": "assistant",
            "sender": "Stream Demo",
            "content": "",
            "timestamp": datetime.now().astimezone().isoformat(),
            "session_id": session_id,
        }

        def run_demo_stream():
            server.socketio.emit(
                "ai_stream_start",
                {"session_id": session_id, "message": message},
                room=target_sid,
            )
            server.socketio.sleep(0)

            for offset in range(0, len(text), chunk_size):
                chunk = text[offset : offset + chunk_size]
                server.socketio.emit(
                    "ai_stream_chunk",
                    {
                        "session_id": session_id,
                        "message_id": message_id,
                        "chunk": chunk,
                        "is_end": False,
                    },
                    room=target_sid,
                )
                server.socketio.sleep(delay_seconds)

            server.socketio.emit(
                "ai_stream_end",
                {"session_id": session_id, "message_id": message_id, "is_end": True},
                room=target_sid,
            )

        server.socketio.start_background_task(run_demo_stream)

    @server.socketio.on("send_message")
    def handle_send_message(data):
        try:
            session_id = data.get("session_id")
            raw_content = data.get("content", "")
            sender = data.get("sender", "web_user")
            raw_attachments = data.get("attachments", [])

            session = server.sessions.get(session_id)
            if session and session.get("read_only"):
                server.socketio.emit("error", {"message": "此会话为只读归档，无法发送消息"}, to=request.sid)
                return
            content = adapter.normalize_inbound_message(raw_content)
            attachments = adapter.normalize_attachments(raw_attachments)

            attachment_info = ""
            if attachments and isinstance(attachments, list):
                for att in attachments:
                    if isinstance(att, dict):
                        att_name = att.get("name", "unknown")
                        att_type = att.get("type", "")
                        attachment_info += f"\n[Attachment: {att_name}, type: {att_type}]"

            preview = content[:50] if content else ""
            server.log_message(
                "info",
                f"Received Web message from {sender}: {preview}... {len(attachments)} attachments",
            )
            _log.info(
                f"Received Web message: session={session_id}, sender={sender}, attachments={len(attachments)}"
            )

            if not session_store.get_session(session_id):
                disk_session = get_session_from_db(server.data_dir, session_id)
                if disk_session:
                    session_store.set_session(session_id, disk_session)

            if not session_store.get_session(session_id):
                server.socketio.emit(
                    "error", {"message": "Session not found"}, room=request.sid
                )
                return

            matched_handler = None
            if content and content.startswith("/"):
                try:
                    from nbot.commands import match_command
                    matched_handler, matched_cmd = match_command(content)
                    if matched_handler:
                        _log.info(f"Matched command: {matched_cmd}")
                    else:
                        _log.warning(f"Unknown command: {content}")
                except ImportError as e:
                    _log.warning(f"Failed to import command handlers: {e}")
                except Exception as e:
                    _log.error(f"Command matching failed: {e}", exc_info=True)

            temp_id = data.get("tempId")

            processed_attachments = []
            if attachments and isinstance(attachments, list):
                for att in attachments:
                    if isinstance(att, dict):
                        processed_att = {
                            "name": att.get("name", "unknown"),
                            "type": att.get("type", ""),
                            "size": att.get("size", 0),
                            "source": att.get("source", "web"),
                            "path": att.get("path", ""),
                            "url": att.get("url", att.get("path", "")),
                            "download_url": att.get("download_url", ""),
                            "preview_url": att.get("preview_url", ""),
                            "data": att.get("data", ""),
                            "content": att.get("content"),
                            "preview": att.get("preview")
                            if att.get("type", "").startswith("image/")
                            else att.get("url", att.get("path", "")),
                        }
                        processed_attachments.append(processed_att)

            is_edit_resend = data.get("is_edit_resend", False)

            # 从 data 或 session 读取 plot_mode 传入 pipeline
            req_metadata = {"tempId": temp_id}
            session_data = server.sessions.get(session_id, {})
            plot_mode = data.get("plot_mode") or session_data.get("plot_mode")
            if plot_mode:
                req_metadata["plot_mode"] = True
                plot_real_time_sync = data.get("plot_real_time_sync")
                if plot_real_time_sync is None:
                    plot_real_time_sync = session_data.get("plot_real_time_sync")
                if plot_real_time_sync:
                    req_metadata["plot_real_time_sync"] = True
                plot_choice_style = data.get("plot_choice_style")
                if plot_choice_style is None:
                    plot_choice_style = session_data.get("plot_choice_style")
                if plot_choice_style:
                    req_metadata["plot_choice_style"] = str(plot_choice_style)

            chat_request = adapter.build_chat_request(
                conversation_id=session_id,
                content=content,
                sender=sender,
                attachments=processed_attachments,
                parent_message_id=temp_id,
                metadata=req_metadata,
            )

            if not is_edit_resend:
                message = adapter.build_message(
                    role="user",
                    content=chat_request.content,
                    sender=chat_request.sender,
                    conversation_id=chat_request.conversation_id,
                    attachments=chat_request.attachments,
                    metadata=req_metadata,
                )

                session_store.append_message(session_id, message)
                if message.get("filter_blocked"):
                    server.socketio.emit(
                        "message_filtered",
                        {
                            "session_id": session_id,
                            "tempId": temp_id,
                            "message": "当前内容被过滤",
                        },
                        room=request.sid,
                    )
                    return

                chat_request.content = message.get("content", chat_request.content)

                if getattr(server, "MESSAGE_MODULE_AVAILABLE", False) and getattr(
                    server, "message_manager", None
                ):
                    manager_payload = adapter.build_manager_payload_from_message(
                        message,
                        default_role="user",
                        default_content=chat_request.content,
                        default_sender=chat_request.sender,
                        default_conversation_id=chat_request.conversation_id,
                        metadata=req_metadata,
                    )
                    server.message_manager.add_web_message(
                        session_id,
                        server.create_message(**manager_payload),
                    )

                server.socketio.emit("new_message", message, room=session_id)

            if matched_handler:
                web_user_id = str(int(hashlib.md5(session_id.encode()).hexdigest(), 16))[
                    :10
                ]
                msg_adapter = WebMessageAdapter(content, web_user_id, session_id, server)

                def run_command():
                    original_bot = None
                    try:
                        import nbot.commands as cmd_module

                        original_bot = getattr(cmd_module, "bot", None)
                        cmd_module.bot = msg_adapter.bot
                        _log.info("Patched command bot for Web mock adapter")
                        asyncio.run(matched_handler(msg_adapter, is_group=True))
                    except Exception as e:
                        _log.error(f"Command execution failed: {e}", exc_info=True)
                        try:
                            asyncio.run(msg_adapter.reply(text=f"Command error: {e}"))
                        except Exception as reply_error:
                            _log.error(f"Failed to send command error reply: {reply_error}")
                    finally:
                        if original_bot:
                            cmd_module.bot = original_bot
                            _log.info("Restored command bot")

                server.socketio.start_background_task(run_command)
            else:
                parent_msg_id = temp_id if temp_id else (message["id"] if not is_edit_resend else temp_id)
                server._trigger_ai_response(
                    chat_request.conversation_id,
                    chat_request.content,
                    chat_request.sender,
                    chat_request.attachments,
                    parent_msg_id,
                    metadata=chat_request.metadata,
                )

        except Exception as e:
            _log.error(f"Failed to handle Web message: {e}", exc_info=True)
            server.socketio.emit(
                "error", {"message": f"Message handling failed: {str(e)}"}, room=request.sid
            )

    @server.socketio.on("typing")
    def handle_typing(data):
        session_id = data.get("session_id")
        emit(
            "user_typing",
            {"sender": server.web_users.get(request.sid)},
            room=session_id,
        )

    @server.socketio.on("confirm_exec")
    def handle_confirm_exec(data):
        """处理用户对 exec_command 的确认/拒绝"""
        try:
            request_id = data.get("request_id", "")
            approved = data.get("approved", False)
            session_id = data.get("session_id", "")

            if not request_id:
                _log.warning("[confirm_exec] 缺少 request_id")
                return

            _log.info(f"[confirm_exec] request_id={request_id[:8]}, approved={approved}, session={session_id}")

            from nbot.services.tools import (
                execute_pending_command,
                get_pending_info,
                reject_pending_command,
            )

            pending_info = get_pending_info(request_id) or {}
            effective_session_id = session_id or pending_info.get("session_id", "")
            command_for_step = pending_info.get("command", "")
            parent_message_id = pending_info.get("parent_message_id", "")
            progress_card_id = pending_info.get("progress_card_id", "")
            todo_card_id = pending_info.get("todo_card_id", "")
            exec_step_result = None

            if approved:
                exec_result = execute_pending_command(request_id)
                exec_step_result = exec_result
                if exec_result.get("executed"):
                    cmd = exec_result.get("command", "")
                    command_for_step = cmd
                    stdout = exec_result.get("stdout", "")
                    stderr = exec_result.get("stderr", "")
                    result_content = (
                        f"已确认并执行命令：`{cmd}`\n\n"
                        f"退出码：{exec_result.get('returncode')}\n\n"
                        f"标准输出：\n{stdout or '(无输出)'}"
                    )
                    if stderr:
                        result_content += f"\n\n标准错误：\n{stderr}"
                else:
                    result_content = f"命令执行失败：{exec_result.get('error', '未知错误')}"
            else:
                reject_result = reject_pending_command(request_id)
                exec_step_result = reject_result
                command_for_step = reject_result.get("command", command_for_step)
                result_content = f"已取消执行命令：`{reject_result.get('command', '')}`"

            if effective_session_id:
                # 仅作为系统上下文保存，不直接在 Web 对话区展示执行结果气泡
                session_store.append_message(
                    effective_session_id,
                    {
                        "id": f"exec_ctx_{request_id}",
                        "role": "system",
                        "content": f"[exec_command_result]\n{result_content}",
                    },
                )

            # Fallback: always notify the requesting socket so frontend can clear loading state.
            server.socketio.emit(
                "exec_confirm_result",
                {
                    "session_id": effective_session_id,
                    "approved": bool(approved),
                },
                room=request.sid,
            )
            if (
                effective_session_id
                and getattr(server, "PROGRESS_CARD_AVAILABLE", False)
                and getattr(server, "progress_card_manager", None)
            ):
                if command_for_step and exec_step_result is not None:
                    progress_card = (
                        server.progress_card_manager.get_card(progress_card_id)
                        if progress_card_id
                        else None
                    )
                    if progress_card and progress_card.session_id == effective_session_id:
                        progress_card.complete_exec_command_step(
                            command_for_step,
                            exec_step_result,
                        )
                    else:
                        server.progress_card_manager.complete_exec_command_step(
                            effective_session_id,
                            command_for_step,
                            exec_step_result,
                        )
            if effective_session_id:
                followup_prompt = (
                    "The pending exec_command is resolved. Use the execution result already in context "
                    "to continue answering the user. If additional commands are needed, you may call "
                    "exec_command again — each non-whitelisted command will require its own confirmation."
                )
                followup_metadata = {"exec_confirmation_followup": True}
                if progress_card_id:
                    followup_metadata["resume_progress_card_id"] = progress_card_id
                if todo_card_id:
                    followup_metadata["resume_todo_card_id"] = todo_card_id
                server._trigger_ai_response(
                    effective_session_id,
                    followup_prompt,
                    "system",
                    parent_message_id=parent_message_id or None,
                    metadata=followup_metadata,
                    channel_id="web",
                )
            _log.info(
                f"[confirm_exec] result emitted sid={request.sid}, session={effective_session_id}, approved={approved}"
            )
        except Exception as e:
            _log.error(f"[confirm_exec] 处理出错: {e}", exc_info=True)
