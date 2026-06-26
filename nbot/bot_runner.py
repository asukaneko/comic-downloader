"""Bot 启动协调 —— 检测可用后端并创建实例

阶段 1: 根据环境变量选择 ncatbot / qqbot 后端。
"""
from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)


def detect_backend() -> str | None:
    """根据环境变量决定使用哪个后端。优先级: ncatbot > qqbot > None

    Returns:
        "ncatbot" | "qqbot" | None
    """
    bot_uin = os.getenv("BOT_UIN", "").strip()
    ws_uri = os.getenv("WS_URI", "").strip()
    qqbot_app_id = os.getenv("QQBOT_APP_ID", "").strip()
    qqbot_app_secret = os.getenv("QQBOT_APP_SECRET", "").strip()

    has_ncatbot = bool(bot_uin and ws_uri)
    has_qqbot = bool(qqbot_app_id and qqbot_app_secret)

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
    if backend_name == "ncatbot":
        from nbot.backends.ncatbot_backend import NcatbotBackend
        # ncatbot 配置注入在 bot.py 启动时已执行(_apply_runtime_ncatbot_config)
        # 这里直接创建 backend 即可
        return NcatbotBackend()
    if backend_name == "qqbot":
        from nbot.backends.qqbot_backend import QQBotBackend
        return QQBotBackend(
            app_id=os.getenv("QQBOT_APP_ID", ""),
            app_secret=os.getenv("QQBOT_APP_SECRET", ""),
            sandbox=os.getenv("QQBOT_SANDBOX", "").lower() == "true",
            api_base=os.getenv("QQBOT_API_BASE", ""),
        )
    raise ValueError(f"Unknown backend: {backend_name}")
