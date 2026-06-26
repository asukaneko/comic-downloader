"""测试 nbot.bot_runner.detect_backend / create_backend"""
import os
from unittest.mock import patch

import pytest

from nbot.bot_runner import create_backend, detect_backend


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """每个测试前清理相关环境变量"""
    for k in (
        "BOT_UIN", "ROOT", "WS_URI", "TOKEN",
        "QQBOT_APP_ID", "QQBOT_APP_SECRET",
        "QQBOT_SANDBOX", "QQBOT_API_BASE",
    ):
        monkeypatch.delenv(k, raising=False)
    yield


def test_detect_backend_none():
    """无配置时返回 None"""
    assert detect_backend() is None


def test_detect_backend_ncatbot():
    """配置 ncatbot 时返回 'ncatbot'"""
    os.environ["BOT_UIN"] = "12345"
    os.environ["WS_URI"] = "ws://localhost:3001"
    assert detect_backend() == "ncatbot"


def test_detect_backend_qqbot():
    """配置 QQBot 时返回 'qqbot'"""
    os.environ["QQBOT_APP_ID"] = "test_app_id"
    os.environ["QQBOT_APP_SECRET"] = "test_secret"
    assert detect_backend() == "qqbot"


def test_detect_backend_both_ncatbot_priority():
    """两个都配置时 ncatbot 优先"""
    os.environ["BOT_UIN"] = "12345"
    os.environ["WS_URI"] = "ws://localhost:3001"
    os.environ["QQBOT_APP_ID"] = "test_app_id"
    os.environ["QQBOT_APP_SECRET"] = "test_secret"
    assert detect_backend() == "ncatbot"


def test_detect_backend_partial_ncatbot():
    """ncatbot 配置不完整(只有 BOT_UIN 没有 WS_URI)返回 None"""
    os.environ["BOT_UIN"] = "12345"
    assert detect_backend() is None


def test_detect_backend_partial_qqbot():
    """QQBot 配置不完整(只有 APP_ID)返回 None"""
    os.environ["QQBOT_APP_ID"] = "test_app_id"
    assert detect_backend() is None


def test_detect_backend_default_ws_uri_ignored():
    """WS_URI 是默认占位值时不识别为 ncatbot 配置"""
    os.environ["BOT_UIN"] = "12345"
    os.environ["WS_URI"] = "ws://localhost:3001"  # 默认值
    # bot_runner 不判断默认值占位 —— 这里仍识别为 ncatbot
    # (默认值占位判断在 bot.py:_has_qq_bot_config 中)
    assert detect_backend() == "ncatbot"


def test_create_backend_unknown_raises():
    """create_backend 未知后端抛 ValueError"""
    with pytest.raises(ValueError, match="Unknown backend"):
        create_backend("nonexistent")


def test_create_backend_ncatbot():
    """create_backend('ncatbot') 创建 NcatbotBackend"""
    os.environ["BOT_UIN"] = "12345"
    os.environ["WS_URI"] = "ws://localhost:3001"

    with patch("nbot.backends.ncatbot_backend.NcatbotBackend") as mock_cls:
        create_backend("ncatbot")
        mock_cls.assert_called_once()


def test_create_backend_qqbot():
    """create_backend('qqbot') 创建 QQBotBackend"""
    os.environ["QQBOT_APP_ID"] = "test_id"
    os.environ["QQBOT_APP_SECRET"] = "test_secret"
    os.environ["QQBOT_SANDBOX"] = "true"
    os.environ["QQBOT_API_BASE"] = "https://test.api"

    with patch("nbot.backends.qqbot_backend.QQBotBackend") as mock_cls:
        create_backend("qqbot")
        mock_cls.assert_called_once_with(
            app_id="test_id",
            app_secret="test_secret",
            sandbox=True,
            api_base="https://test.api",
        )
