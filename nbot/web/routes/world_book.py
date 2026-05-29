import json
import logging
import os
import re
from datetime import datetime

from flask import jsonify, request, send_file

from nbot.character.storage.world_book_store import WorldBookStore

_log = logging.getLogger(__name__)


def _get_store(server) -> WorldBookStore:
    base_dir = getattr(server, "base_dir", ".")
    return WorldBookStore(base_dir)


def register_world_book_routes(app, server):

    # ---- 世界书 CRUD ----

    @app.route("/api/world-books")
    def list_world_books():
        try:
            store = _get_store(server)
            books = store.list_all()
            result = []
            for book in books:
                d = book.to_dict()
                d["entry_count"] = len(book.entries)
                result.append(d)
            return jsonify(result)
        except Exception as e:
            _log.error("[WorldBook] list failed: %s", e)
            return jsonify([])

    @app.route("/api/world-books", methods=["POST"])
    def create_world_book():
        try:
            data = request.json or {}
            name = data.get("name", "").strip()
            if not name:
                return jsonify({"success": False, "error": "name is required"}), 400

            store = _get_store(server)
            book = store.create(
                name=name,
                description=data.get("description", ""),
                character_ids=data.get("character_ids", []),
            )

            try:
                server.record_operation(
                    module="world_book",
                    action="create",
                    description=f"创建世界书 -> {name}",
                    detail=f"世界书ID={book.id}",
                    metadata={"book_id": book.id, "name": name},
                )
            except Exception:
                pass

            return jsonify({"success": True, "world_book": book.to_dict()})
        except Exception as e:
            _log.error("[WorldBook] create failed: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/world-books/<book_id>")
    def get_world_book(book_id):
        try:
            store = _get_store(server)
            book = store.get(book_id)
            if not book:
                return jsonify({"error": "World book not found"}), 404
            return jsonify(book.to_dict())
        except Exception as e:
            _log.error("[WorldBook] get failed: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/world-books/<book_id>", methods=["PUT"])
    def update_world_book(book_id):
        try:
            data = request.json or {}
            store = _get_store(server)

            kwargs = {}
            for key in ("name", "description", "character_ids", "enabled"):
                if key in data:
                    kwargs[key] = data[key]

            if not kwargs:
                return jsonify({"success": False, "error": "No fields to update"}), 400

            book = store.update(book_id, **kwargs)
            if not book:
                return jsonify({"error": "World book not found"}), 404

            return jsonify({"success": True, "world_book": book.to_dict()})
        except Exception as e:
            _log.error("[WorldBook] update failed: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/world-books/<book_id>", methods=["DELETE"])
    def delete_world_book(book_id):
        try:
            store = _get_store(server)
            if store.delete(book_id):
                try:
                    server.record_operation(
                        module="world_book",
                        action="delete",
                        description=f"删除世界书 -> {book_id}",
                        detail=f"世界书ID={book_id}",
                        metadata={"book_id": book_id},
                    )
                except Exception:
                    pass
                return jsonify({"success": True})
            return jsonify({"success": False, "error": "World book not found"}), 404
        except Exception as e:
            _log.error("[WorldBook] delete failed: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    # ---- 条目 CRUD ----

    @app.route("/api/world-books/<book_id>/entries")
    def list_entries(book_id):
        try:
            store = _get_store(server)
            entries = store.list_entries(book_id)
            return jsonify([e.to_dict() for e in entries])
        except Exception as e:
            _log.error("[WorldBook] list entries failed: %s", e)
            return jsonify([])

    @app.route("/api/world-books/<book_id>/entries", methods=["POST"])
    def create_entry(book_id):
        try:
            data = request.json or {}
            if not data.get("content"):
                return jsonify({"success": False, "error": "content is required"}), 400

            store = _get_store(server)
            entry = store.add_entry(book_id, data)
            if not entry:
                return jsonify({"success": False, "error": "World book not found"}), 404

            return jsonify({"success": True, "entry": entry.to_dict()})
        except Exception as e:
            _log.error("[WorldBook] create entry failed: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/world-books/<book_id>/entries/<entry_id>", methods=["PUT"])
    def update_entry(book_id, entry_id):
        try:
            data = request.json or {}
            store = _get_store(server)

            kwargs = {}
            for key in ("name", "keywords", "content", "enabled", "priority", "case_sensitive", "match_mode"):
                if key in data:
                    kwargs[key] = data[key]

            if not kwargs:
                return jsonify({"success": False, "error": "No fields to update"}), 400

            entry = store.update_entry(book_id, entry_id, **kwargs)
            if not entry:
                return jsonify({"success": False, "error": "Entry not found"}), 404

            return jsonify({"success": True, "entry": entry.to_dict()})
        except Exception as e:
            _log.error("[WorldBook] update entry failed: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/world-books/<book_id>/entries/<entry_id>", methods=["DELETE"])
    def delete_entry(book_id, entry_id):
        try:
            store = _get_store(server)
            if store.delete_entry(book_id, entry_id):
                return jsonify({"success": True})
            return jsonify({"success": False, "error": "Entry not found"}), 404
        except Exception as e:
            _log.error("[WorldBook] delete entry failed: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/world-books/<book_id>/entries/batch", methods=["POST"])
    def batch_create_entries(book_id):
        try:
            data = request.json or {}
            entries_data = data.get("entries", [])
            if not entries_data:
                return jsonify({"success": False, "error": "No entries provided"}), 400

            store = _get_store(server)
            created = store.batch_add_entries(book_id, entries_data)
            return jsonify({
                "success": True,
                "count": len(created),
                "entries": [e.to_dict() for e in created],
            })
        except Exception as e:
            _log.error("[WorldBook] batch create failed: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    # ---- 导入/导出 ----

    @app.route("/api/world-books/export/<book_id>")
    def export_world_book(book_id):
        """导出单个世界书为 JSON 文件"""
        try:
            store = _get_store(server)
            book = store.get(book_id)
            if not book:
                return jsonify({"success": False, "error": "World book not found"}), 404

            data = book.to_dict()
            data["_export_version"] = 1
            data["_exported_at"] = datetime.now().isoformat()

            blob = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            filename = f"{book.name}_世界书.json"

            return send_file(
                __import__("io").BytesIO(blob),
                mimetype="application/json",
                as_attachment=True,
                download_name=filename,
            )
        except Exception as e:
            _log.error("[WorldBook] export failed: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/world-books/import", methods=["POST"])
    def import_world_book():
        """导入单个世界书（JSON 文件）"""
        try:
            file = request.files.get("file")
            if not file:
                return jsonify({"success": False, "error": "No file provided"}), 400

            raw = file.read().decode("utf-8")
            data = json.loads(raw)

            if not isinstance(data, dict) or not data.get("name"):
                return jsonify({"success": False, "error": "Invalid world book format"}), 400

            store = _get_store(server)

            # 创建世界书
            book = store.create(
                name=data.get("name", "导入的世界书"),
                description=data.get("description", ""),
                character_ids=data.get("character_ids", []),
            )

            # 导入条目
            entries_data = data.get("entries", [])
            if isinstance(entries_data, dict):
                entries_data = list(entries_data.values())
            if isinstance(entries_data, list) and entries_data:
                store.batch_add_entries(book.id, entries_data)

            # 更新 enabled 状态
            if "enabled" in data and not data["enabled"]:
                store.update(book.id, enabled=False)

            imported_book = store.get(book.id)

            try:
                server.record_operation(
                    module="world_book",
                    action="import",
                    description=f"导入世界书 -> {book.name}",
                    metadata={"book_id": book.id, "entry_count": len(entries_data)},
                )
            except Exception:
                pass

            return jsonify({
                "success": True,
                "world_book": imported_book.to_dict() if imported_book else book.to_dict(),
            })
        except json.JSONDecodeError:
            return jsonify({"success": False, "error": "Invalid JSON file"}), 400
        except Exception as e:
            _log.error("[WorldBook] import failed: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/world-books/export-all")
    def export_all_world_books():
        """导出所有世界书为 JSON 文件"""
        try:
            store = _get_store(server)
            books = store.list_all()

            data = {
                "_export_version": 1,
                "_exported_at": datetime.now().isoformat(),
                "_type": "world_books_bundle",
                "world_books": [b.to_dict() for b in books],
            }

            blob = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"全部世界书_{ts}.json"

            return send_file(
                __import__("io").BytesIO(blob),
                mimetype="application/json",
                as_attachment=True,
                download_name=filename,
            )
        except Exception as e:
            _log.error("[WorldBook] export-all failed: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/world-books/import-all", methods=["POST"])
    def import_all_world_books():
        """批量导入世界书（JSON 文件）"""
        try:
            file = request.files.get("file")
            if not file:
                return jsonify({"success": False, "error": "No file provided"}), 400

            raw = file.read().decode("utf-8")
            data = json.loads(raw)

            # 支持单个世界书和批量格式
            if isinstance(data, dict) and data.get("_type") == "world_books_bundle":
                books_data = data.get("world_books", [])
            elif isinstance(data, dict) and data.get("name"):
                books_data = [data]
            elif isinstance(data, list):
                books_data = data
            else:
                return jsonify({"success": False, "error": "Invalid format"}), 400

            store = _get_store(server)
            imported_count = 0
            failed_names = []

            for book_data in books_data:
                try:
                    if not isinstance(book_data, dict) or not book_data.get("name"):
                        continue

                    book = store.create(
                        name=book_data.get("name", "导入的世界书"),
                        description=book_data.get("description", ""),
                        character_ids=book_data.get("character_ids", []),
                    )

                    entries_data = book_data.get("entries", [])
                    if isinstance(entries_data, dict):
                        entries_data = list(entries_data.values())
                    if isinstance(entries_data, list) and entries_data:
                        store.batch_add_entries(book.id, entries_data)

                    if "enabled" in book_data and not book_data["enabled"]:
                        store.update(book.id, enabled=False)

                    imported_count += 1
                except Exception as e:
                    _log.warning("[WorldBook] import entry failed: %s", e)
                    failed_names.append(book_data.get("name", "unknown"))

            try:
                server.record_operation(
                    module="world_book",
                    action="import_all",
                    description=f"批量导入世界书 -> {imported_count} 本",
                    metadata={"imported": imported_count, "failed": len(failed_names)},
                )
            except Exception:
                pass

            return jsonify({
                "success": True,
                "imported_count": imported_count,
                "failed_count": len(failed_names),
                "failed_names": failed_names,
            })
        except json.JSONDecodeError:
            return jsonify({"success": False, "error": "Invalid JSON file"}), 400
        except Exception as e:
            _log.error("[WorldBook] import-all failed: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    # ---- AI 生成 ----

    @app.route("/api/world-books/<book_id>/ai-generate", methods=["POST"])
    def ai_generate_world_book_entries(book_id):
        """根据绑定的角色信息，AI 生成世界书条目"""
        try:
            data = request.json or {}
            topic = (data.get("topic") or "").strip()

            if not server.ai_client:
                return jsonify({"success": False, "error": "AI 客户端未初始化"}), 503

            store = _get_store(server)
            book = store.get(book_id)
            if not book:
                return jsonify({"success": False, "error": "World book not found"}), 404

            # 收集绑定角色的信息
            character_infos = []
            if book.character_ids:
                from nbot.character.repository import ProfileRepository
                base_dir = getattr(server, "base_dir", ".")
                profile_repo = ProfileRepository(base_dir)

                # 同时查找预设 UUID 对应的角色名
                presets = getattr(server, "custom_personality_presets", []) or []
                uuid_to_name = {p.get("id", ""): p.get("name", "") for p in presets if isinstance(p, dict)}

                for cid in book.character_ids:
                    # 尝试直接按名称查找
                    profile = profile_repo.get(cid)
                    if not profile:
                        # 尝试 UUID → 名称
                        resolved = uuid_to_name.get(cid, "")
                        if resolved:
                            profile = profile_repo.get(resolved)
                    if profile:
                        character_infos.append(
                            f"【{profile.name}】\n"
                            f"描述: {profile.description}\n"
                            f"基本信息: {profile.basic_info}\n"
                            f"性格: {profile.personality}\n"
                            f"背景设定: {profile.scenario}\n"
                            f"行为规则: {', '.join(profile.rules) if profile.rules else '无'}"
                        )

            # 构建 prompt
            char_section = ""
            if character_infos:
                char_section = "\n\n以下是已绑定的角色信息，请根据这些角色的世界观和设定来生成内容：\n\n" + "\n\n".join(character_infos)

            topic_section = ""
            if topic:
                topic_section = f"\n\n用户指定的主题/方向：{topic}"

            system_prompt = f"""你是一个世界观设定专家。请为一个世界书生成条目。

每个条目包含：
- name: 条目名称（简短有辨识度）
- keywords: 关键词列表（3-5个，用于在用户消息中匹配触发此条目）
- content: 注入内容（当关键词命中时，这段内容会被注入到 AI 的提示词中，帮助 AI 理解世界观）
- match_mode: "any"（任一关键词命中即触发）或 "all"（全部命中才触发）
- priority: 优先级数字（0-100，越高越优先注入）

请生成 5-10 个条目，覆盖该世界观的核心设定。
{char_section}{topic_section}

你必须严格按照以下JSON格式返回（不要包含任何额外的文字说明，只返回JSON）：

{{
    "entries": [
        {{
            "name": "条目名称",
            "keywords": ["关键词1", "关键词2", "关键词3"],
            "content": "当用户消息命中关键词时注入的内容...",
            "match_mode": "any",
            "priority": 50
        }}
    ]
}}

要求：
1. keywords 应该是用户聊天中可能出现的词语，不要太生僻
2. content 要具体、有信息量，帮助 AI 角色扮演时理解世界观
3. 优先级根据条目重要程度分配（核心设定 > 细节设定）
4. 如果有绑定角色，生成的设定要与角色背景契合
"""

            user_msg = f"请为世界书「{book.name}」生成世界观条目。"
            if book.description:
                user_msg += f"\n世界书描述：{book.description}"
            if topic:
                user_msg += f"\n主题方向：{topic}"
            if not character_infos and not topic:
                user_msg += "\n（未绑定角色也未指定主题，请根据世界书名称自由发挥）"

            response = server.ai_client.chat_completion(
                model=server.ai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                stream=False,
            )

            content = response.choices[0].message.content.strip()

            # 解析 JSON（处理 markdown 代码块）
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
            if json_match:
                content = json_match.group(1).strip()

            result = json.loads(content)
            entries_data = result.get("entries", [])

            if not isinstance(entries_data, list) or not entries_data:
                return jsonify({"success": False, "error": "AI 未生成有效条目"}), 500

            # 批量创建条目
            created = store.batch_add_entries(book_id, entries_data)

            try:
                server.record_operation(
                    module="world_book",
                    action="ai_generate",
                    description=f"AI 生成世界书条目 -> {book.name}",
                    metadata={"book_id": book_id, "entry_count": len(created)},
                )
            except Exception:
                pass

            return jsonify({
                "success": True,
                "count": len(created),
                "entries": [e.to_dict() for e in created],
            })
        except json.JSONDecodeError:
            _log.error("[WorldBook] AI generate: invalid JSON response")
            return jsonify({"success": False, "error": "AI 返回了无效的 JSON 格式"}), 500
        except Exception as e:
            _log.error("[WorldBook] AI generate failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    # ---- 测试匹配 ----

    @app.route("/api/world-books/test-match", methods=["POST"])
    def test_match():
        try:
            data = request.json or {}
            message = data.get("message", "")
            character_id = data.get("character_id", "")

            if not message:
                return jsonify({"success": False, "error": "message is required"}), 400

            store = _get_store(server)
            from nbot.character.world_book_matcher import test_match as _test_match

            world_books = store.list_all()
            matches = _test_match(message, world_books, character_id or None)

            return jsonify({"success": True, "matches": matches})
        except Exception as e:
            _log.error("[WorldBook] test match failed: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500
