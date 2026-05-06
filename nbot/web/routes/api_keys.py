import os
import time

from flask import jsonify, request

from nbot.web.secure_store import read_secure_json, write_secure_json


def get_api_keys_file_path(server):
    return os.path.join(server.data_dir, "api_keys.json")


def load_api_keys(server):
    file_path = get_api_keys_file_path(server)
    try:
        api_keys, was_plaintext = read_secure_json(file_path, server.data_dir, [])
        if was_plaintext:
            save_api_keys(server, api_keys)
        return api_keys if isinstance(api_keys, list) else []
    except Exception:
        return []


def save_api_keys(server, api_keys):
    file_path = get_api_keys_file_path(server)
    try:
        write_secure_json(file_path, server.data_dir, api_keys)
        return True
    except Exception:
        return False


def register_api_key_routes(app, server):
    @app.route("/api/api-keys", methods=["GET"])
    def get_api_keys():
        try:
            api_keys = load_api_keys(server)
            safe_keys = [
                {"id": key.get("id"), "name": key.get("name", "未命名")}
                for key in api_keys
            ]
            return jsonify({"success": True, "keys": safe_keys})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/api-keys/<key_id>", methods=["GET"])
    def get_api_key(key_id):
        try:
            api_keys = load_api_keys(server)
            key = next((k for k in api_keys if k.get("id") == key_id), None)
            if key:
                return jsonify({"success": True, "key": key})
            return jsonify({"error": "API Key not found"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/api-keys", methods=["POST"])
    def create_api_key():
        try:
            data = request.json or {}
            name = data.get("name", "").strip()
            key_value = data.get("key", "").strip()

            if not name:
                return jsonify({"error": "Name is required"}), 400
            if not key_value:
                return jsonify({"error": "API Key is required"}), 400

            api_keys = load_api_keys(server)
            if any(k.get("name") == name for k in api_keys):
                return jsonify({"error": "API Key name already exists"}), 400

            new_key = {
                "id": f"key_{int(time.time() * 1000)}",
                "name": name,
                "key": key_value,
                "created_at": time.time(),
            }
            api_keys.append(new_key)

            if save_api_keys(server, api_keys):
                return jsonify(
                    {
                        "success": True,
                        "key": {"id": new_key["id"], "name": new_key["name"]},
                    }
                )
            return jsonify({"error": "Failed to save API Key"}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/api-keys/<key_id>", methods=["PUT"])
    def update_api_key(key_id):
        try:
            data = request.json or {}
            name = data.get("name", "").strip()
            key_value = data.get("key", "").strip()

            api_keys = load_api_keys(server)
            key_index = next(
                (i for i, k in enumerate(api_keys) if k.get("id") == key_id), None
            )
            if key_index is None:
                return jsonify({"error": "API Key not found"}), 404

            if name and any(
                k.get("name") == name and k.get("id") != key_id for k in api_keys
            ):
                return jsonify({"error": "API Key name already exists"}), 400

            if name:
                api_keys[key_index]["name"] = name
            if key_value:
                api_keys[key_index]["key"] = key_value
            api_keys[key_index]["updated_at"] = time.time()

            if save_api_keys(server, api_keys):
                return jsonify(
                    {
                        "success": True,
                        "key": {"id": key_id, "name": api_keys[key_index]["name"]},
                    }
                )
            return jsonify({"error": "Failed to save API Key"}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/api-keys/<key_id>", methods=["DELETE"])
    def delete_api_key(key_id):
        try:
            api_keys = load_api_keys(server)
            key_index = next(
                (i for i, k in enumerate(api_keys) if k.get("id") == key_id), None
            )
            if key_index is None:
                return jsonify({"error": "API Key not found"}), 404

            api_keys.pop(key_index)

            if save_api_keys(server, api_keys):
                return jsonify({"success": True})
            return jsonify({"error": "Failed to save API Keys"}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500
