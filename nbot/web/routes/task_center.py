import uuid
from copy import deepcopy
from datetime import datetime

from flask import jsonify, request


def _normalize_task_payload(data):
    config = data.get("config") or {}
    return {
        "name": (data.get("name") or "新任务").strip() or "新任务",
        "description": (data.get("description") or "").strip(),
        "enabled": bool(data.get("enabled", True)),
        "trigger": data.get("trigger", "interval"),
        "config": {
            "interval_minutes": int(config.get("interval_minutes", 60) or 60),
            "cron": (config.get("cron") or "0 8 * * *").strip() or "0 8 * * *",
            "run_at": config.get("run_at") or "",
        },
        "target_session_id": (data.get("target_session_id") or "").strip(),
        "prompt": (data.get("prompt") or "").strip(),
    }


def register_task_center_routes(app, server):
    def _payload():
        return request.get_json(silent=True) or {}

    def _start_background_or_run(handler):
        socketio = getattr(server, "socketio", None)
        if socketio and hasattr(socketio, "start_background_task"):
            socketio.start_background_task(handler)
            return "background"
        handler()
        return "sync"

    @app.route("/api/task-center")
    def get_task_center():
        return jsonify({"items": server.get_task_center_items()})

    @app.route("/api/task-center", methods=["POST"])
    def create_task_center_task():
        payload = _normalize_task_payload(_payload())
        task = {
            "id": str(uuid.uuid4()),
            "kind": "custom",
            "created_at": datetime.now().isoformat(),
            "last_run": None,
            "next_run": None,
            **payload,
        }
        try:
            server._validate_custom_task(task)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        server.scheduled_tasks.append(task)

        if task.get("enabled"):
            server._schedule_custom_task(task)

        server._save_data("scheduled_tasks")
        return jsonify({"success": True, "task": task})

    @app.route("/api/task-center/<task_id>", methods=["PUT"])
    def update_task_center_task(task_id):
        task = server._get_custom_task(task_id)
        if not task:
            return jsonify({"error": "Task not found"}), 404

        payload = _normalize_task_payload(_payload())
        candidate = {**task, **payload}
        try:
            server._validate_custom_task(candidate)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        task.update(payload)
        server._unschedule_custom_task(task_id)
        if task.get("enabled"):
            server._schedule_custom_task(task)

        server._save_data("scheduled_tasks")
        return jsonify({"success": True, "task": task})

    @app.route("/api/task-center/<task_id>", methods=["DELETE"])
    def delete_task_center_task(task_id):
        task = server._get_custom_task(task_id)
        if not task:
            return jsonify({"error": "Task not found"}), 404

        server._unschedule_custom_task(task_id)
        server.scheduled_tasks = [item for item in server.scheduled_tasks if item.get("id") != task_id]
        server._save_data("scheduled_tasks")
        return jsonify({"success": True})

    @app.route("/api/task-center/<task_id>/toggle", methods=["POST"])
    def toggle_task_center_item(task_id):
        if task_id == "heartbeat":
            manager = getattr(server, "session_heartbeat_manager", None)
            if manager:
                # 按 session_id 索引（而非 target_session_id），避免 life_sim 等
                # 后缀 config 查不到对应记录而误新建一个 enabled config。
                enabled_configs = manager.list_enabled_configs()
                if enabled_configs:
                    # 当前存在已启用的心跳：一次性全部关闭，符合 UI 总开关直觉
                    for cfg in enabled_configs:
                        manager.set_config(cfg["session_id"], {"enabled": False})
                else:
                    # 没有任何已启用的心跳：按 target_session_id 启用，否则回退到首个 web 会话
                    target_session_id = str(
                        server.heartbeat_config.get("target_session_id") or ""
                    ).strip()
                    sid = target_session_id
                    if not sid:
                        for session_id, s in getattr(server, "sessions", {}).items():
                            if s.get("type") == "web":
                                sid = session_id
                                break
                    if sid:
                        manager.set_config(sid, {"enabled": True})

                server._refresh_heartbeat_summary_config()
                if manager.any_enabled():
                    server._start_heartbeat_job(server.heartbeat_config.get("interval_minutes", 60))
                else:
                    server._stop_heartbeat_job()
            else:
                server.heartbeat_config["enabled"] = not server.heartbeat_config.get("enabled", False)
                if server.heartbeat_config["enabled"]:
                    server._start_heartbeat_job(server.heartbeat_config.get("interval_minutes", 60))
                else:
                    server._stop_heartbeat_job()
            server._save_data("heartbeat")
            return jsonify({"success": True, "item": deepcopy(server.heartbeat_config)})

        workflow = next((item for item in server.workflows if item.get("id") == task_id), None)
        if workflow:
            workflow["enabled"] = not workflow.get("enabled", True)
            if workflow.get("trigger") == "cron":
                if workflow["enabled"]:
                    server._schedule_workflow(workflow)
                else:
                    server._unschedule_workflow(task_id)
            server._save_data("workflows")
            return jsonify({"success": True, "item": workflow})

        task = server._get_custom_task(task_id)
        if not task:
            return jsonify({"error": "Task not found"}), 404

        task["enabled"] = not task.get("enabled", True)
        if task["enabled"]:
            try:
                server._validate_custom_task(task)
            except ValueError as exc:
                task["enabled"] = False
                return jsonify({"error": str(exc)}), 400
            server._schedule_custom_task(task)
        else:
            server._unschedule_custom_task(task_id)
        server._save_data("scheduled_tasks")
        return jsonify({"success": True, "item": task})

    @app.route("/api/task-center/<task_id>/run", methods=["POST"])
    def run_task_center_item(task_id):
        if task_id == "heartbeat":
            import asyncio

            def _safe_run_async(coro_fn):
                """安全执行异步函数，兼容已有事件循环的情况"""
                try:
                    asyncio.get_running_loop()
                    # 已有事件循环，在新线程中运行
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        return pool.submit(asyncio.run, coro_fn()).result(timeout=300)
                except RuntimeError:
                    return asyncio.run(coro_fn())

            manager = getattr(server, "session_heartbeat_manager", None)
            if manager and hasattr(server, "_refresh_heartbeat_summary_config"):
                server._refresh_heartbeat_summary_config()

            target_session_id = str(server.heartbeat_config.get("target_session_id") or "").strip()
            if not target_session_id and manager:
                enabled = manager.list_enabled_configs()
                if enabled:
                    target_session_id = str(
                        enabled[0].get("target_session_id") or enabled[0].get("session_id") or ""
                    ).strip()

            if manager and target_session_id:
                _start_background_or_run(
                    lambda: _safe_run_async(
                        lambda: manager.execute_session(
                            target_session_id,
                            force=True,
                            trigger_source="task-center",
                        )
                    )
                )
                return jsonify({"success": True, "message": "Heartbeat 执行已触发"})

            _start_background_or_run(
                lambda: _safe_run_async(lambda: server._execute_heartbeat(force=True))
            )
            return jsonify({"success": True, "message": "Heartbeat 执行已触发"})

        workflow = next((item for item in server.workflows if item.get("id") == task_id), None)
        if workflow:
            trigger_data = {
                "source": "task-center",
                "content": _payload().get("content", ""),
                "time": datetime.now().isoformat(),
            }
            server._execute_workflow(task_id, trigger_data)
            return jsonify({"success": True})

        task = server._get_custom_task(task_id)
        if not task:
            return jsonify({"error": "Task not found"}), 404

        server.socketio.start_background_task(
            server._execute_custom_task,
            task_id,
            "task-center",
        )
        return jsonify({"success": True, "message": "Task execution started"})
