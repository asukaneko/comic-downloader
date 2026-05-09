from datetime import datetime

from flask import jsonify, request


def register_memory_routes(app, server):
    @app.route("/api/memory")
    def get_memory():
        mem_type = request.args.get("type", "all")
        target_id = request.args.get("target_id", "")
        character_name = request.args.get("character_name", "")

        if getattr(server, "PROMPT_MANAGER_AVAILABLE", False) and getattr(
            server, "prompt_manager", None
        ):
            try:
                memories = server.prompt_manager.get_memories(
                    target_id, mem_type if mem_type != "all" else None,
                    character_name if character_name else None
                )
                # 同步 server.memories 缓存（清理后可能变少）
                server.memories = server.prompt_manager.get_memories()
            except Exception:
                memories = server.memories
        else:
            memories = server.memories

        if mem_type != "all":
            memories = [m for m in memories if m.get("type", "long") == mem_type]
        if target_id:
            memories = [m for m in memories if m.get("target_id", "") == target_id]
        if character_name:
            memories = [m for m in memories if m.get("character_name", "") == character_name]

        # 处理 type 字段，确保只有 "long" 或 "short" 两种值
        long_term = []
        short_term = []
        for m in memories:
            mem_type = m.get("type", "long")
            # 如果 type 不是 "long" 或 "short"，默认为 "long"
            if mem_type not in ("long", "short"):
                mem_type = "long"
            if mem_type == "long":
                long_term.append(m)
            else:
                short_term.append(m)

        return jsonify(
            {"memories": memories, "long_term": long_term, "short_term": short_term}
        )

    @app.route("/api/memory", methods=["POST"])
    def add_memory():
        data = request.json or {}
        target_id = data.get("target_id", "")
        title = data.get("title", "")
        content = data.get("content", "")
        summary = data.get("summary")
        mem_type = data.get("type", "long")
        expire_days = data.get("expire_days", 7)
        character_name = data.get("character_name", "")

        if not title or not content:
            return jsonify({"success": False, "error": "title and content are required"}), 400

        prompt_manager = getattr(server, "prompt_manager", None)
        if not prompt_manager:
            return jsonify({"success": False, "error": "Prompt manager not available"}), 503

        success = prompt_manager.add_memory(
            title, content, target_id, summary, mem_type, expire_days,
            character_name if character_name else None
        )
        if success:
            server.memories = prompt_manager.get_memories()
            server._save_data("memories")
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Failed to add memory"}), 500

    @app.route("/api/memory/<memory_id>", methods=["PUT"])
    def update_memory(memory_id):
        data = request.json or {}

        prompt_manager = getattr(server, "prompt_manager", None)
        if prompt_manager:
            updates = {}
            if "title" in data:
                updates["title"] = data["title"]
            elif "key" in data:
                updates["title"] = data["key"]
            if "content" in data:
                updates["content"] = data["content"]
            elif "value" in data:
                updates["content"] = data["value"]
            if "summary" in data:
                updates["summary"] = data["summary"]
            if "type" in data:
                updates["type"] = data["type"]
            if "priority" in data:
                updates["priority"] = data["priority"]
            if "expire_days" in data:
                updates["expire_days"] = data["expire_days"]
            if "target_id" in data:
                updates["target_id"] = data["target_id"]
            if "character_name" in data:
                updates["character_name"] = data["character_name"]
            updates["updated_at"] = datetime.now().isoformat()

            success = prompt_manager.update_memory(memory_id, updates)
            if success:
                server.memories = prompt_manager.get_memories()
                server._save_data("memories")
                # 返回更新后的记忆
                for mem in server.memories:
                    if mem.get("id") == memory_id:
                        return jsonify({"success": True, "memory": mem})
                return jsonify({"success": True})
            return jsonify({"error": "Memory not found"}), 404

        # 回退：直接操作 server.memories
        for mem in server.memories:
            if mem.get("id") == memory_id:
                if "title" in data:
                    mem["title"] = data.get("title", mem.get("title", ""))
                elif "key" in data:
                    mem["title"] = data.get("key", mem.get("title", ""))
                if "content" in data:
                    mem["content"] = data.get("content", mem.get("content", ""))
                elif "value" in data:
                    mem["content"] = data.get("value", mem.get("content", ""))
                mem["summary"] = data.get("summary", mem.get("summary", ""))
                mem["type"] = data.get("type", mem.get("type", "long"))
                mem["priority"] = data.get("priority", mem.get("priority", "normal"))
                mem["expire_days"] = data.get("expire_days", mem.get("expire_days", 7))
                mem["target_id"] = data.get("target_id", mem.get("target_id", ""))
                mem["updated_at"] = datetime.now().isoformat()
                server._save_data("memories")
                return jsonify({"success": True, "memory": mem})
        return jsonify({"error": "Memory not found"}), 404

    @app.route("/api/memory/<memory_id>", methods=["DELETE"])
    def delete_memory(memory_id):
        prompt_manager = getattr(server, "prompt_manager", None)
        if not prompt_manager:
            return jsonify({"success": False, "error": "Prompt manager not available"}), 503

        success = prompt_manager.delete_memory(memory_id)
        if success:
            server.memories = [m for m in server.memories if m.get("id") != memory_id]
            server._save_data("memories")
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Failed to delete memory"}), 500

    @app.route("/api/memory", methods=["DELETE"])
    def clear_all_memory():
        target_id = request.args.get("target_id")
        prompt_manager = getattr(server, "prompt_manager", None)
        if not prompt_manager:
            return jsonify({"success": False, "error": "Prompt manager not available"}), 503

        success = prompt_manager.clear_memories(target_id)
        if success:
            if target_id:
                server.memories = [
                    m for m in server.memories if m.get("target_id") != target_id
                ]
            else:
                server.memories = []
            server._save_data("memories")
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Failed to clear memories"}), 500

    @app.route("/api/memory/export")
    def export_memory():
        return jsonify({"memories": server.memories})

    @app.route("/api/memory/batch-delete", methods=["POST"])
    def batch_delete_memory():
        data = request.json or {}
        ids = data.get("ids", [])
        if not ids or not isinstance(ids, list):
            return jsonify({"success": False, "error": "ids list is required"}), 400

        prompt_manager = getattr(server, "prompt_manager", None)
        if not prompt_manager:
            return jsonify({"success": False, "error": "Prompt manager not available"}), 503

        deleted = 0
        for mid in ids:
            if prompt_manager.delete_memory(mid):
                deleted += 1
                server.memories = [m for m in server.memories if m.get("id") != mid]

        if deleted > 0:
            server._save_data("memories")
        return jsonify({"success": True, "deleted": deleted})

    @app.route("/api/memory/import", methods=["POST"])
    def import_memory():
        data = request.json or {}
        items = data.get("memories", [])
        if not items or not isinstance(items, list):
            return jsonify({"success": False, "error": "memories list is required"}), 400

        prompt_manager = getattr(server, "prompt_manager", None)
        if not prompt_manager:
            return jsonify({"success": False, "error": "Prompt manager not available"}), 503

        imported = 0
        skipped = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("key") or "").strip()
            content = str(item.get("content") or item.get("value") or "").strip()
            if not title or not content:
                skipped += 1
                continue
            summary = str(item.get("summary") or "").strip() or None
            mem_type = str(item.get("type") or "long").strip().lower()
            if mem_type not in ("long", "short"):
                mem_type = "long"
            expire_days = int(item.get("expire_days", 7) or 7)
            target_id = str(item.get("target_id") or "").strip()
            character_name = str(item.get("character_name") or "").strip() or None
            if prompt_manager.add_memory(
                title, content, target_id, summary, mem_type, expire_days, character_name
            ):
                imported += 1
            else:
                skipped += 1

        server.memories = prompt_manager.get_memories()
        server._save_data("memories")
        return jsonify({"success": True, "imported": imported, "skipped": skipped})
