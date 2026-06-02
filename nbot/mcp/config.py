"""MCP configuration loading helpers."""

import configparser
import copy
import os
from pathlib import Path
from typing import Any

_DEFAULT_CONFIG: dict[str, Any] = {
    "transport": "stdio",
    "server": {
        "host": "127.0.0.1",
        "port": 5001,
    },
    "permissions": {
        "default_scopes": [
            "gateway.read",
            "events.query",
            "queue.read",
            "node.read",
        ],
    },
    "tools": {
        "gateway_send_message": {
            "enabled": False,
            "require_confirmation": True,
        },
        "gateway_receive_message": {
            "enabled": True,
            "require_confirmation": False,
        },
        "gateway_retry_dead_letter": {
            "enabled": True,
            "require_confirmation": True,
        },
        "gateway_submit_internal_task": {
            "enabled": True,
            "require_confirmation": True,
        },
        "gateway_register_node": {
            "enabled": False,
            "require_confirmation": True,
        },
    },
    "audit": {
        "enabled": True,
        "log_args": True,
        "redact_fields": ["token", "secret", "password", "authorization"],
    },
    "gateway": {
        "storage": {"enabled": True},
    },
    "data_dir": os.path.join("data", "web"),
}


def project_root() -> Path:
    """Return the repository root for this installed source tree."""
    return Path(__file__).resolve().parents[2]


def default_mcp_config() -> dict[str, Any]:
    """Return a fresh default MCP config."""
    return copy.deepcopy(_DEFAULT_CONFIG)


def resolve_data_dir(data_dir: str, base_dir: str | os.PathLike[str] | None = None) -> str:
    """Resolve a data directory from the project root instead of process cwd."""
    root = Path(base_dir).resolve() if base_dir else project_root()
    path = Path(data_dir or os.path.join("data", "web")).expanduser()
    if not path.is_absolute():
        path = root / path
    return str(path.resolve())


def load_mcp_config(
    *,
    base_dir: str | os.PathLike[str] | None = None,
    config_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Load MCP config from config.ini with Web Gateway storage defaults."""
    root = Path(base_dir).resolve() if base_dir else project_root()
    path = Path(config_path).resolve() if config_path else root / "config.ini"
    config = default_mcp_config()
    config["base_dir"] = str(root)

    cp = configparser.ConfigParser()
    if path.exists():
        cp.read(path, encoding="utf-8")

        if cp.has_section("mcp"):
            send_enabled = cp.getboolean("mcp", "send_message_enabled", fallback=False)
            config["tools"]["gateway_send_message"]["enabled"] = send_enabled

            register_enabled = cp.getboolean("mcp", "register_node_enabled", fallback=False)
            config["tools"]["gateway_register_node"]["enabled"] = register_enabled

            submit_task_enabled = cp.getboolean("mcp", "submit_task_enabled", fallback=True)
            config["tools"]["gateway_submit_internal_task"]["enabled"] = submit_task_enabled

            retry_confirm = cp.getboolean("mcp", "retry_require_confirmation", fallback=True)
            config["tools"]["gateway_retry_dead_letter"]["require_confirmation"] = retry_confirm

            audit_enabled = cp.getboolean("mcp", "audit_enabled", fallback=True)
            config["audit"]["enabled"] = audit_enabled

            # 权限：admin = true 时授予全部权限（适用于本地 stdio 模式）
            admin_enabled = cp.getboolean("mcp", "admin", fallback=False)
            config["permissions"]["admin"] = admin_enabled

            # 传输模式：stdio (本地) | streamable-http (远程)
            transport = cp.get("mcp", "transport", fallback="stdio")
            config["transport"] = transport

            # 服务端配置
            host = cp.get("mcp", "host", fallback="127.0.0.1")
            config["server"]["host"] = host
            port = cp.getint("mcp", "port", fallback=5001)
            config["server"]["port"] = port

            # 远程连接 URL (--mcp-connect 使用)
            connect_url = cp.get("mcp", "connect_url", fallback="")
            if connect_url:
                config["connect_url"] = connect_url

        if cp.has_section("gateway"):
            storage_enabled = cp.getboolean("gateway", "storage_enabled", fallback=True)
            config["gateway"]["storage"]["enabled"] = storage_enabled
            config["data_dir"] = cp.get(
                "gateway",
                "data_dir",
                fallback=config.get("data_dir", os.path.join("data", "web")),
            )

    config["data_dir"] = resolve_data_dir(str(config.get("data_dir", "")), root)
    return config
