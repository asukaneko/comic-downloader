"""Bot 启动协调 —— 检测可用后端并创建实例

阶段 1: 根据环境变量选择 ncatbot / qqbot 后端。
修复 P2: detect_backend / create_backend 统一从环境变量 + config.ini 读取,
与 bot.py _has_qq_bot_config() 保持一致。
"""
from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)


def _read_bot_config() -> dict:
    """读取 bot 相关配置,环境变量优先,config.ini 兜底

    Returns:
        {"bot_uin": ..., "ws_uri": ..., "qqbot_app_id": ...,
         "qqbot_app_secret": ..., "qqbot_sandbox": ..., "qqbot_api_base": ...}
    """
    bot_uin = os.getenv("BOT_UIN", "").strip()
    ws_uri = os.getenv("WS_URI", "").strip()
    qqbot_app_id = os.getenv("QQBOT_APP_ID", "").strip()
    qqbot_app_secret = os.getenv("QQBOT_APP_SECRET", "").strip()
    qqbot_sandbox = os.getenv("QQBOT_SANDBOX", "").strip().lower() == "true"
    qqbot_api_base = os.getenv("QQBOT_API_BASE", "").strip()

    # 环境变量不完整时,从 config.ini 兜底
    if not (bot_uin and ws_uri and qqbot_app_id and qqbot_app_secret):
        try:
            import configparser
            cp = configparser.ConfigParser()
            cp.read("config.ini", encoding="utf-8")
            if not bot_uin:
                bot_uin = cp.get(
                    "BotConfig", "bot_uin", fallback=""
                ).strip()
            if not ws_uri:
                ws_uri = cp.get(
                    "BotConfig", "ws_uri", fallback=""
                ).strip()
            if not qqbot_app_id:
                qqbot_app_id = cp.get(
                    "BotConfig", "qqbot_app_id", fallback=""
                ).strip()
            if not qqbot_app_secret:
                qqbot_app_secret = cp.get(
                    "BotConfig", "qqbot_app_secret", fallback=""
                ).strip()
            if not os.getenv("QQBOT_SANDBOX", "").strip():
                sandbox_raw = cp.get(
                    "BotConfig", "qqbot_sandbox", fallback="false"
                ).strip().lower()
                qqbot_sandbox = sandbox_raw in ("true", "1", "yes", "on")
            if not qqbot_api_base:
                qqbot_api_base = cp.get(
                    "BotConfig", "qqbot_api_base", fallback=""
                ).strip()
        except Exception:
            pass

    return {
        "bot_uin": bot_uin,
        "ws_uri": ws_uri,
        "qqbot_app_id": qqbot_app_id,
        "qqbot_app_secret": qqbot_app_secret,
        "qqbot_sandbox": qqbot_sandbox,
        "qqbot_api_base": qqbot_api_base,
    }


def detect_backend() -> str | None:
    """根据环境变量 / config.ini 决定使用哪个后端。优先级: ncatbot > qqbot > None

    Returns:
        "ncatbot" | "qqbot" | None
    """
    cfg = _read_bot_config()

    has_ncatbot = bool(
        cfg["bot_uin"]
        and cfg["ws_uri"]
        and cfg["bot_uin"] not in ["", "0"]
        and cfg["ws_uri"] not in ["", "ws://", "ws://localhost"]
    )
    has_qqbot = bool(
        cfg["qqbot_app_id"] and cfg["qqbot_app_secret"]
    )

    if has_ncatbot and has_qqbot:
        _log.warning(
            "Both ncatbot and qqbot configured; ncatbot takes precedence"
        )
    if has_ncatbot:
        return "ncatbot"
    if has_qqbot:
        return "qqbot"
    return None


def create_backend(backend_name: str):
    """根据后端名称创建 BotBackend 实例

    Args:
        backend_name: "ncatbot" | "qqbot"
    """
    cfg = _read_bot_config()
    if backend_name == "ncatbot":
        from nbot.backends.ncatbot_backend import NcatbotBackend
        # ncatbot 配置注入在 bot.py 启动时已执行(_apply_runtime_ncatbot_config)
        # 这里直接创建 backend 即可
        return NcatbotBackend()
    if backend_name == "qqbot":
        from nbot.backends.qqbot_backend import QQBotBackend
        return QQBotBackend(
            app_id=cfg["qqbot_app_id"],
            app_secret=cfg["qqbot_app_secret"],
            sandbox=cfg["qqbot_sandbox"],
            api_base=cfg["qqbot_api_base"],
        )
    raise ValueError(f"Unknown backend: {backend_name}")
