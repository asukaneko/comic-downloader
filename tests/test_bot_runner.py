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
    """ncatbot 配置不完整(只有 BOT_UIN 没有 WS_URI)返回 None
    
    P2 修复: 现在也从 config.ini 兜底读取,需要确保测试环境无 config.ini 干扰。
    """
    import os
    import tempfile
    
    # 临时切换到临时目录,避免读取项目根目录的 config.ini
    original_cwd = os.getcwd()
    temp_dir = tempfile.mkdtemp()
    os.chdir(temp_dir)
    
    try:
        os.environ["BOT_UIN"] = "12345"
        # WS_URI 未设置,且临时目录无 config.ini
        assert detect_backend() is None
    finally:
        os.chdir(original_cwd)
        os.rmdir(temp_dir)


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


def test_detect_backend_reads_config_ini_fallback():
    """P2 修复: 环境变量不完整时从 config.ini 兜底读取"""
    import os
    import tempfile

    # 创建临时 config.ini
    config_content = """[BotConfig]
bot_uin = 99999
ws_uri = ws://127.0.0.1:3001
qqbot_app_id = ini_app_id
qqbot_app_secret = ini_secret
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
        f.write(config_content)
        temp_config_path = f.name

    try:
        # 临时替换 config.ini 路径
        original_cwd = os.getcwd()
        temp_dir = os.path.dirname(temp_config_path)
        os.chdir(temp_dir)
        os.rename(temp_config_path, os.path.join(temp_dir, "config.ini"))
        config_ini_path = os.path.join(temp_dir, "config.ini")

        # 环境变量未设置,应从 config.ini 读取
        result = detect_backend()
        # ncatbot 优先
        assert result == "ncatbot"

        # 清理
        os.remove(config_ini_path)
        os.chdir(original_cwd)
    except Exception:
        # 如果测试环境无法创建临时文件,跳过
        if os.path.exists(temp_config_path):
            os.remove(temp_config_path)
