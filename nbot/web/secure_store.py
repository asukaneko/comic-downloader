import json
import logging
import os
from typing import Any

from cryptography.fernet import Fernet

_log = logging.getLogger(__name__)

_ENVELOPE_VERSION = 1
_KEY_ENV = "NBOT_SECURE_STORE_KEY"


def _key_path(data_dir: str) -> str:
    return os.path.join(data_dir, "secrets", "secure_store.key")


def _load_or_create_key(data_dir: str) -> bytes:
    env_key = os.getenv(_KEY_ENV, "").strip()
    if env_key:
        return env_key.encode("utf-8")

    path = _key_path(data_dir)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read().strip()

    os.makedirs(os.path.dirname(path), exist_ok=True)
    key = Fernet.generate_key()
    with open(path, "wb") as f:
        f.write(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        _log.debug("Could not restrict secure store key permissions", exc_info=True)
    return key


def _fernet(data_dir: str) -> Fernet:
    return Fernet(_load_or_create_key(data_dir))


def _is_encrypted_envelope(data: Any) -> bool:
    return (
        isinstance(data, dict)
        and data.get("encrypted") is True
        and data.get("algorithm") == "fernet"
        and isinstance(data.get("payload"), str)
    )


def read_secure_json(file_path: str, data_dir: str, default: Any) -> tuple[Any, bool]:
    """Read encrypted JSON, returning (data, was_plaintext_legacy)."""
    if not os.path.exists(file_path):
        return default, False

    with open(file_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not _is_encrypted_envelope(raw):
        return raw, True

    plaintext = _fernet(data_dir).decrypt(raw["payload"].encode("utf-8"))
    return json.loads(plaintext.decode("utf-8")), False


def write_secure_json(file_path: str, data_dir: str, data: Any) -> None:
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    envelope = {
        "version": _ENVELOPE_VERSION,
        "encrypted": True,
        "algorithm": "fernet",
        "payload": _fernet(data_dir).encrypt(payload).decode("utf-8"),
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, ensure_ascii=False, indent=2)
