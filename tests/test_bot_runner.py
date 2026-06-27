"""Tests for nbot.bot_runner backend detection and creation."""

import os
from unittest.mock import patch

import pytest

from nbot.bot_runner import create_backend, detect_backend


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in (
        "BOT_UIN",
        "ROOT",
        "WS_URI",
        "TOKEN",
        "QQBOT_APP_ID",
        "QQBOT_APP_SECRET",
        "QQBOT_SANDBOX",
        "QQBOT_API_BASE",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


def test_detect_backend_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert detect_backend() is None


def test_detect_backend_ncatbot():
    os.environ["BOT_UIN"] = "12345"
    os.environ["WS_URI"] = "ws://localhost:3001"
    assert detect_backend() == "ncatbot"


def test_detect_backend_qqbot():
    os.environ["QQBOT_APP_ID"] = "test_app_id"
    os.environ["QQBOT_APP_SECRET"] = "test_secret"
    assert detect_backend() == "qqbot"


def test_detect_backend_both_ncatbot_priority():
    os.environ["BOT_UIN"] = "12345"
    os.environ["WS_URI"] = "ws://localhost:3001"
    os.environ["QQBOT_APP_ID"] = "test_app_id"
    os.environ["QQBOT_APP_SECRET"] = "test_secret"
    assert detect_backend() == "ncatbot"


def test_detect_backend_partial_ncatbot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.environ["BOT_UIN"] = "12345"
    assert detect_backend() is None


def test_detect_backend_partial_qqbot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.environ["QQBOT_APP_ID"] = "test_app_id"
    assert detect_backend() is None


def test_detect_backend_default_ws_uri_ignored():
    os.environ["BOT_UIN"] = "12345"
    os.environ["WS_URI"] = "ws://localhost:3001"
    assert detect_backend() == "ncatbot"


def test_create_backend_unknown_raises():
    with pytest.raises(ValueError, match="Unknown backend"):
        create_backend("nonexistent")


def test_create_backend_ncatbot():
    os.environ["BOT_UIN"] = "12345"
    os.environ["WS_URI"] = "ws://localhost:3001"

    with patch("nbot.backends.ncatbot_backend.NcatbotBackend") as mock_cls:
        create_backend("ncatbot")

    mock_cls.assert_called_once()


def test_create_backend_qqbot():
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


def test_detect_backend_reads_config_ini_fallback(tmp_path, monkeypatch):
    config_content = """[BotConfig]
bot_uin = 99999
ws_uri = ws://127.0.0.1:3001
qqbot_app_id = ini_app_id
qqbot_app_secret = ini_secret
"""
    monkeypatch.chdir(tmp_path)
    with open("config.ini", "w", encoding="utf-8") as file_obj:
        file_obj.write(config_content)

    assert detect_backend() == "ncatbot"


def test_create_backend_qqbot_reads_config_ini_fallback(tmp_path, monkeypatch):
    config_content = """[BotConfig]
qqbot_app_id = ini_app_id
qqbot_app_secret = ini_secret
qqbot_sandbox = true
qqbot_api_base = https://ini.api
"""
    monkeypatch.chdir(tmp_path)
    with open("config.ini", "w", encoding="utf-8") as file_obj:
        file_obj.write(config_content)

    with patch("nbot.backends.qqbot_backend.QQBotBackend") as mock_cls:
        create_backend("qqbot")

    mock_cls.assert_called_once_with(
        app_id="ini_app_id",
        app_secret="ini_secret",
        sandbox=True,
        api_base="https://ini.api",
    )
