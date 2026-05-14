import base64
import json
import os
import platform
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Iterable

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from nbot.web.secure_store import read_secure_json, write_secure_json


BUNDLE_VERSION = 1
KDF_ITERATIONS = 390000
KDF_SALT_BYTES = 16
CONFIG_KEYS = (
    "settings",
    "sessions",
    "ai_config",
    "ai_models",
    "api_keys",
    "active_model_id",
    "active_models_by_purpose",
    "skills",
    "tools",
    "channels",
    "heartbeat",
    "scheduled_tasks",
    "workflows",
    "memories",
    "personality",
    "custom_personality_presets",
)
SAVE_TYPES = (
    "settings",
    "sessions",
    "ai_config",
    "ai_models",
    "skills",
    "tools",
    "channels",
    "heartbeat",
    "scheduled_tasks",
    "workflows",
    "memories",
    "custom_personality_presets",
)


class ConfigTransferError(ValueError):
    pass


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def _fernet_from_password(password: str, salt: bytes) -> Fernet:
    if not password or not password.strip():
        raise ConfigTransferError("导出/导入密码不能为空")
    return Fernet(_derive_key(password.strip(), salt))


def _clean_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _read_personality(server) -> Dict[str, Any]:
    path = os.path.join(server.base_dir, "resources", "prompts", "personality.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return deepcopy(getattr(server, "personality", {}) or {})


def _read_api_keys(server) -> Any:
    path = os.path.join(server.data_dir, "api_keys.json")
    try:
        data, _ = read_secure_json(path, server.data_dir, [])
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_api_keys(server, api_keys: Any) -> None:
    path = os.path.join(server.data_dir, "api_keys.json")
    write_secure_json(path, server.data_dir, api_keys if isinstance(api_keys, list) else [])


def _write_personality(server, personality: Dict[str, Any]) -> None:
    path = os.path.join(server.base_dir, "resources", "prompts", "personality.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(personality or {}, f, ensure_ascii=False, indent=2)
    server.personality = personality or {}


def build_plain_bundle(server) -> Dict[str, Any]:
    ai_models = getattr(server, "ai_models", []) or []
    return {
        "version": BUNDLE_VERSION,
        "type": "nbot_config_bundle",
        "exported_at": datetime.now().isoformat(),
        "source": {
            "hostname": platform.node(),
            "platform": platform.platform(),
        },
        "configs": {
            "settings": deepcopy(getattr(server, "settings", {}) or {}),
            "sessions": deepcopy(getattr(server, "sessions", {}) or {}),
            "ai_config": deepcopy(getattr(server, "ai_config", {}) or {}),
            "ai_models": deepcopy(ai_models),
            "api_keys": _read_api_keys(server),
            "active_model_id": getattr(server, "active_model_id", None),
            "active_models_by_purpose": deepcopy(
                getattr(server, "active_models_by_purpose", {}) or {}
            ),
            "skills": deepcopy(getattr(server, "skills_config", []) or []),
            "tools": deepcopy(getattr(server, "tools_config", []) or []),
            "channels": deepcopy(getattr(server, "channels_config", []) or []),
            "heartbeat": deepcopy(getattr(server, "heartbeat_config", {}) or {}),
            "scheduled_tasks": deepcopy(getattr(server, "scheduled_tasks", []) or []),
            "workflows": deepcopy(getattr(server, "workflows", []) or []),
            "memories": deepcopy(getattr(server, "memories", []) or []),
            "personality": _read_personality(server),
            "custom_personality_presets": deepcopy(
                getattr(server, "custom_personality_presets", []) or []
            ),
        },
    }


def encrypt_bundle(server, password: str) -> Dict[str, Any]:
    salt = os.urandom(KDF_SALT_BYTES)
    plaintext = json.dumps(
        build_plain_bundle(server),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    token = _fernet_from_password(password, salt).encrypt(plaintext)
    return {
        "version": BUNDLE_VERSION,
        "type": "nbot_config_bundle",
        "encrypted": True,
        "algorithm": "fernet",
        "kdf": "pbkdf2_hmac_sha256",
        "iterations": KDF_ITERATIONS,
        "salt": base64.urlsafe_b64encode(salt).decode("ascii"),
        "exported_at": datetime.now().isoformat(),
        "payload": token.decode("ascii"),
    }


def decrypt_bundle(bundle: Dict[str, Any], password: str) -> Dict[str, Any]:
    if not isinstance(bundle, dict):
        raise ConfigTransferError("配置包格式无效")
    if bundle.get("type") != "nbot_config_bundle":
        raise ConfigTransferError("不是有效的 NekoBot 配置包")
    if not bundle.get("encrypted"):
        if isinstance(bundle.get("configs"), dict):
            return bundle
        raise ConfigTransferError("配置包未加密且缺少配置内容")

    try:
        salt = base64.urlsafe_b64decode(str(bundle.get("salt", "")).encode("ascii"))
        payload = str(bundle.get("payload", "")).encode("ascii")
        plaintext = _fernet_from_password(password, salt).decrypt(payload)
        data = json.loads(plaintext.decode("utf-8"))
    except InvalidToken as exc:
        raise ConfigTransferError("密码错误或配置包已损坏") from exc
    except Exception as exc:
        raise ConfigTransferError(f"无法解密配置包: {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("configs"), dict):
        raise ConfigTransferError("配置包内容无效")
    return data


def _save_imported_configs(server, touched: Iterable[str]) -> None:
    for data_type in touched:
        if data_type in SAVE_TYPES:
            server._save_data(data_type)


def apply_bundle(server, bundle: Dict[str, Any], *, overwrite: bool = True) -> Dict[str, Any]:
    configs = bundle.get("configs") or {}
    if not isinstance(configs, dict):
        raise ConfigTransferError("配置包缺少 configs")

    imported = []
    skipped = []
    touched = set()

    def assign(config_key: str, attr: str, default: Any, save_type: str = None):
        if config_key not in configs:
            skipped.append(config_key)
            return
        value = configs.get(config_key)
        if value is None:
            value = default
        if not overwrite:
            current = getattr(server, attr, None)
            if current:
                skipped.append(config_key)
                return
        clean_value = _clean_json(value)
        if attr == "sessions" and isinstance(getattr(server, "sessions", None), dict):
            server.sessions.clear()
            server.sessions.update(clean_value if isinstance(clean_value, dict) else {})
            if getattr(server, "PROGRESS_CARD_AVAILABLE", False) and getattr(
                server, "progress_card_manager", None
            ):
                server.progress_card_manager.set_sessions(server.sessions)
            if getattr(server, "TODO_CARD_AVAILABLE", False) and getattr(
                server, "todo_card_manager", None
            ):
                server.todo_card_manager.set_sessions(server.sessions)
        else:
            setattr(server, attr, clean_value)
        imported.append(config_key)
        if save_type:
            touched.add(save_type)

    assign("settings", "settings", {}, "settings")
    assign("sessions", "sessions", {}, "sessions")
    assign("ai_config", "ai_config", {}, "ai_config")
    assign("ai_models", "ai_models", [], "ai_models")
    assign("active_model_id", "active_model_id", None, "ai_models")
    assign("active_models_by_purpose", "active_models_by_purpose", {}, "ai_models")
    assign("skills", "skills_config", [], "skills")
    assign("tools", "tools_config", [], "tools")
    assign("channels", "channels_config", [], "channels")
    assign("heartbeat", "heartbeat_config", {}, "heartbeat")
    assign("scheduled_tasks", "scheduled_tasks", [], "scheduled_tasks")
    assign("workflows", "workflows", [], "workflows")
    assign("memories", "memories", [], "memories")
    assign(
        "custom_personality_presets",
        "custom_personality_presets",
        [],
        "custom_personality_presets",
    )

    if "personality" in configs:
        personality = configs.get("personality") if isinstance(configs.get("personality"), dict) else {}
        if overwrite or not getattr(server, "personality", None):
            _write_personality(server, _clean_json(personality))
            imported.append("personality")
        else:
            skipped.append("personality")

    if "api_keys" in configs:
        api_keys = configs.get("api_keys")
        if overwrite or not _read_api_keys(server):
            _write_api_keys(server, _clean_json(api_keys if isinstance(api_keys, list) else []))
            imported.append("api_keys")
        else:
            skipped.append("api_keys")

    _save_imported_configs(server, touched)

    active_chat_model = getattr(server, "active_model_id", None)
    if active_chat_model:
        try:
            server._apply_ai_model(active_chat_model, purpose="chat")
        except Exception:
            pass
    try:
        from nbot.services.ai import refresh_runtime_ai_config

        refresh_runtime_ai_config()
    except Exception:
        pass

    return {
        "imported": imported,
        "skipped": skipped,
        "exported_at": bundle.get("exported_at"),
        "source": bundle.get("source") or {},
    }
