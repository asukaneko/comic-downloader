import logging

from flask import jsonify, request

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
