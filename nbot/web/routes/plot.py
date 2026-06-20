import logging

from flask import jsonify, request

from nbot.plot.graph_manager import get_plot_graph_manager
from nbot.web.routes.sessions import restore_runtime_state_to_path

_log = logging.getLogger(__name__)


def register_plot_routes(app, server):

    @app.route("/api/plot/toggle", methods=["POST"])
    def toggle_plot_mode():
        data = request.json or {}
        session_id = data.get("session_id", "")
        enabled = data.get("enabled", False)

        if not session_id:
            return jsonify({"error": "session_id is required"}), 400

        # Try to set plot_mode on the session
        sessions = getattr(server, "sessions", {})
        if session_id in sessions:
            sessions[session_id]["plot_mode"] = enabled
            try:
                server._save_data("sessions")
            except Exception:
                _log.debug("[PlotRoutes] failed to persist plot_mode", exc_info=True)

        _log.info(
            "[PlotRoutes] plot_mode toggled session=%s enabled=%s",
            session_id,
            enabled,
        )
        return jsonify({"session_id": session_id, "plot_mode": enabled})

    @app.route("/api/plot/<conversation_id>/graph")
    def get_plot_graph(conversation_id):
        data_dir = getattr(server, "data_dir", "data/web")
        manager = get_plot_graph_manager(data_dir=data_dir)
        graph = manager.get_graph(conversation_id)
        # 暴露当前激活节点（会话所在位置的单一真相来源）
        graph["active_node_id"] = manager.get_active_node_id(conversation_id)
        return jsonify(graph)

    @app.route("/api/plot/<conversation_id>/latest-choices")
    def get_latest_plot_choices(conversation_id):
        data_dir = getattr(server, "data_dir", "data/web")
        manager = get_plot_graph_manager(data_dir=data_dir)
        choices = manager.get_latest_choices(conversation_id)
        return jsonify({"choices": choices})

    @app.route("/api/plot/<conversation_id>/mermaid")
    def get_plot_mermaid(conversation_id):
        data_dir = getattr(server, "data_dir", "data/web")
        manager = get_plot_graph_manager(data_dir=data_dir)
        mermaid = manager.generate_mermaid(conversation_id)
        return jsonify({"mermaid": mermaid})

    @app.route("/api/plot/<conversation_id>/select", methods=["POST"])
    def select_plot_choice(conversation_id):
        data = request.json or {}
        choice_id = data.get("choice_id", "")

        if not choice_id:
            return jsonify({"error": "choice_id is required"}), 400

        data_dir = getattr(server, "data_dir", "data/web")
        manager = get_plot_graph_manager(data_dir=data_dir)
        success = manager.select_choice(choice_id)

        if not success:
            return jsonify({"error": "choice not found or already selected"}), 404

        _log.info(
            "[PlotRoutes] choice selected conversation=%s choice=%s",
            conversation_id,
            choice_id,
        )
        return jsonify({"success": True, "choice_id": choice_id})

    @app.route("/api/plot/<conversation_id>/regenerate-choices", methods=["POST"])
    def regenerate_plot_choices(conversation_id):
        """重新生成当前激活节点的剧情选项。"""
        import asyncio as _asyncio

        data_dir = getattr(server, "data_dir", "data/web")
        manager = get_plot_graph_manager(data_dir=data_dir)

        # 找到当前激活节点（或最新节点）
        active_id = manager.get_active_node_id(conversation_id)
        node = manager.get_node(active_id) if active_id else manager.get_latest_node(conversation_id)
        if node is None:
            return jsonify({"error": "no plot node found"}), 404

        # 删除该节点下未选中的旧选项
        manager.delete_choices_for_node(node.id)

        # 获取最后一条助手消息作为生成上下文
        session = server.session_store.get_session(conversation_id) or {}
        messages = session.get("messages") or []
        last_assistant = ""
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                last_assistant = msg.get("content", "") or ""
                break

        # 构建 turn_context（简化版，从 session metadata 提取）
        session_meta = session.get("metadata", {}) or {}
        turn_context = {
            "mood": session_meta.get("mood", ""),
            "relationship": session_meta.get("relationship", ""),
        }

        # 提取最近几轮对话，供选项生成避免重复并取材
        recent_history = [
            {"role": m.get("role"), "content": m.get("content") or ""}
            for m in messages[-8:]
            if isinstance(m, dict)
            and m.get("role") in ("user", "assistant")
            and (m.get("content") or "").strip()
        ]

        # 调用 AI 生成新选项
        from nbot.plot.choice_generator import PlotChoiceGenerator
        from nbot.plot.models import PlotChoice as PlotChoiceModel

        generator = PlotChoiceGenerator()
        try:
            loop = _asyncio.new_event_loop()
            try:
                choices_data = loop.run_until_complete(
                    generator.generate(
                        last_assistant[:800],
                        turn_context,
                        recent_history=recent_history,
                    )
                )
            finally:
                loop.close()
        except Exception as e:
            _log.error("[PlotRoutes] regenerate choices failed: %s", e)
            return jsonify({"error": "generation failed"}), 500

        if not choices_data:
            return jsonify({"error": "generation returned empty"}), 500

        # 创建新选项并关联到节点
        new_choices = []
        for cd in choices_data:
            pc = PlotChoiceModel(
                node_id=node.id,
                text=cd.get("text", ""),
                level=cd.get("level", "normal"),
                intent=cd.get("intent", ""),
            )
            manager.add_choice(pc)
            new_choices.append({
                "id": pc.id,
                "node_id": pc.node_id,
                "text": pc.text,
                "level": pc.level,
                "intent": pc.intent,
                "selected": False,
            })

        graph = manager.get_graph(conversation_id)
        _log.info(
            "[PlotRoutes] regenerated %d choices for node=%s conversation=%s",
            len(new_choices), node.id, conversation_id,
        )
        return jsonify({"choices": new_choices, "graph": graph})

    @app.route("/api/plot/<conversation_id>/rollback", methods=["POST"])
    def rollback_plot(conversation_id):
        data = request.json or {}
        node_id = data.get("node_id", "")

        if not node_id:
            return jsonify({"error": "node_id is required"}), 400

        data_dir = getattr(server, "data_dir", "data/web")
        manager = get_plot_graph_manager(data_dir=data_dir)

        session = server.session_store.get_session(conversation_id)
        if not session:
            return jsonify({"error": "session not found"}), 404
        if manager.get_node(node_id) is None:
            return jsonify({"error": "node not found"}), 404

        # 回溯前先物化根→节点路径（删除后代前，路径仍完整）
        path_nodes = [n.to_dict() for n in manager.path_to_node(conversation_id, node_id)]
        messages = manager.materialize_path(
            conversation_id, node_id, _resolve_system_prompt(session),
        )

        # 删除后代节点、保留目标节点、激活指向目标
        success = manager.rollback(node_id, conversation_id=conversation_id)
        if not success:
            return jsonify({"error": "rollback failed"}), 500

        # 回退会话可见消息
        server.session_store.replace_messages(conversation_id, messages)
        session = server.session_store.get_session(conversation_id) or session
        # 回退角色运行时状态/时间线
        try:
            restore_runtime_state_to_path(server, conversation_id, session, path_nodes)
        except Exception as exc:
            _log.warning("[PlotRoutes] rollback runtime restore failed: %s", exc, exc_info=True)
        session["plot_active_node_id"] = node_id
        server.session_store.set_session(conversation_id, session)

        _log.info(
            "[PlotRoutes] rollback conversation=%s node=%s (%d msgs)",
            conversation_id, node_id, len(messages),
        )
        return jsonify({
            "success": True,
            "node_id": node_id,
            "message_count": len([m for m in messages if m.get("role") != "system"]),
        })

    # ---- 会话内分支 (in-session branching) ----

    def _resolve_system_prompt(session):
        if not isinstance(session, dict):
            return ""
        sp = str(session.get("system_prompt") or "").strip()
        if sp:
            return sp
        msgs = session.get("messages") or []
        sysm = next((m for m in msgs if isinstance(m, dict) and m.get("role") == "system"), None)
        return str((sysm or {}).get("content") or "").strip()

    @app.route("/api/plot/<conversation_id>/branch-preview")
    def plot_branch_preview(conversation_id):
        """只读预览：返回从根到指定节点的完整消息列表，不改动会话。"""
        node_id = request.args.get("node_id", "")
        if not node_id:
            return jsonify({"error": "node_id is required"}), 400
        data_dir = getattr(server, "data_dir", "data/web")
        manager = get_plot_graph_manager(data_dir=data_dir)
        session = server.session_store.get_session(conversation_id) or {}
        messages = manager.materialize_path(
            conversation_id, node_id, _resolve_system_prompt(session),
        )
        # 预览不含 system 提示
        visible = [m for m in messages if m.get("role") != "system"]
        return jsonify({"node_id": node_id, "messages": visible})

    @app.route("/api/plot/<conversation_id>/switch", methods=["POST"])
    def plot_switch_branch(conversation_id):
        """切换到指定节点所在分支：把会话可见消息编排成根→该节点的路径。"""
        data = request.json or {}
        node_id = data.get("node_id", "")
        if not node_id:
            return jsonify({"error": "node_id is required"}), 400

        session = server.session_store.get_session(conversation_id)
        if not session:
            return jsonify({"error": "session not found"}), 404

        data_dir = getattr(server, "data_dir", "data/web")
        manager = get_plot_graph_manager(data_dir=data_dir)
        if manager.get_node(node_id) is None:
            return jsonify({"error": "node not found"}), 404

        messages = manager.materialize_path(
            conversation_id, node_id, _resolve_system_prompt(session),
        )
        server.session_store.replace_messages(conversation_id, messages)
        session = server.session_store.get_session(conversation_id) or session
        # 回退/定位角色运行时状态到该分支末端
        path_nodes = [n.to_dict() for n in manager.path_to_node(conversation_id, node_id)]
        try:
            restore_runtime_state_to_path(server, conversation_id, session, path_nodes)
        except Exception as exc:
            _log.warning("[PlotRoutes] switch runtime restore failed: %s", exc, exc_info=True)
        session["plot_active_node_id"] = node_id
        server.session_store.set_session(conversation_id, session)
        # 图谱激活节点（单一真相来源），保证后续续聊从此分支延伸
        manager.set_active_node(conversation_id, node_id)

        _log.info(
            "[PlotRoutes] switched branch conversation=%s node=%s (%d msgs)",
            conversation_id, node_id, len(messages),
        )
        return jsonify({
            "success": True,
            "node_id": node_id,
            "message_count": len([m for m in messages if m.get("role") != "system"]),
        })

    @app.route("/api/plot/<conversation_id>/branch", methods=["POST"])
    def plot_create_branch(conversation_id):
        """从某节点的某个未走选项创建新分支并立即生成 AI 回复。

        流程：物化根→父节点写回会话 → 追加 user(选项文本) →
        以分支元数据触发 AI，pipeline 会创建以父节点为父的新子节点。
        """
        data = request.json or {}
        node_id = data.get("node_id", "")
        choice_id = data.get("choice_id", "")
        if not node_id or not choice_id:
            return jsonify({"error": "node_id and choice_id are required"}), 400

        session = server.session_store.get_session(conversation_id)
        if not session:
            return jsonify({"error": "session not found"}), 404

        data_dir = getattr(server, "data_dir", "data/web")
        manager = get_plot_graph_manager(data_dir=data_dir)
        node = manager.get_node(node_id)
        choice = manager.get_choice(choice_id)
        if node is None or choice is None:
            return jsonify({"error": "node or choice not found"}), 404
        if choice.node_id != node_id:
            return jsonify({"error": "choice does not belong to node"}), 400

        choice_text = (choice.text or "").strip()
        if not choice_text:
            return jsonify({"error": "choice text is empty"}), 400

        trigger = getattr(server, "_trigger_ai_response", None)
        if not trigger:
            return jsonify({"error": "AI trigger unavailable"}), 500

        # 1) 把会话编排到父节点路径
        base_messages = manager.materialize_path(
            conversation_id, node_id, _resolve_system_prompt(session),
        )
        server.session_store.replace_messages(conversation_id, base_messages)
        # 把角色运行时状态定位到父节点，使新分支从正确状态生成
        session = server.session_store.get_session(conversation_id) or session
        path_nodes = [n.to_dict() for n in manager.path_to_node(conversation_id, node_id)]
        try:
            restore_runtime_state_to_path(server, conversation_id, session, path_nodes)
        except Exception as exc:
            _log.warning("[PlotRoutes] branch runtime restore failed: %s", exc, exc_info=True)
        # 激活节点先指向父节点，触发后 pipeline 会把它推进到新子节点
        manager.set_active_node(conversation_id, node_id)
        server.session_store.set_session(conversation_id, session)

        # 2) 追加用户选项消息
        import uuid
        from datetime import datetime
        user_msg = {
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": choice_text,
            "timestamp": datetime.now().isoformat(),
            "sender": "web_user",
            "session_id": conversation_id,
            "source": session.get("type", "web"),
        }
        server.session_store.append_message(conversation_id, user_msg)
        try:
            server.socketio.emit("new_message", user_msg, room=conversation_id)
        except Exception:
            pass

        # 3) 触发 AI，携带分支元数据
        try:
            trigger(
                conversation_id,
                choice_text,
                "web_user",
                [],
                user_msg["id"],
                metadata={
                    "plot_branch_from_node_id": node_id,
                    "plot_branch_choice_id": choice_id,
                },
            )
        except Exception as exc:
            _log.error("[PlotRoutes] branch trigger failed: %s", exc, exc_info=True)
            return jsonify({"error": "failed to trigger AI response"}), 500

        _log.info(
            "[PlotRoutes] branch created conversation=%s from node=%s choice=%s",
            conversation_id, node_id, choice_id,
        )
        return jsonify({
            "success": True,
            "node_id": node_id,
            "choice_id": choice_id,
            "prompt_message_id": user_msg["id"],
        })
