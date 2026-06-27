"""Tests for nbot.backends.qqbot_backend.QQBotBackend."""

import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest

from nbot.backends.qqbot_backend import QQBotBackend
from nbot.commands_backend import BotBackend, Capability, IncomingMessage, Scene, reset_backend


@pytest.fixture(autouse=True)
def _reset():
    reset_backend()
    yield
    reset_backend()


def _make_backend_without_init(app_id="test_id"):
    backend = QQBotBackend.__new__(QQBotBackend)
    backend._creds = {
        "app_id": app_id,
        "app_secret": "test_secret",
        "sandbox": False,
        "api_base": "",
    }
    backend._ws_app = None
    backend._ws_thread = None
    backend._stop_event = threading.Event()
    backend._heartbeat_thread = None
    backend._dispatch_callback = None
    backend._token = None
    backend._api_base = "https://api.sgroup.qq.com"
    backend._loop = None
    backend._gateway_url = None
    backend.is_running = False
    return backend


def test_supports_only_text():
    backend = _make_backend_without_init()
    assert backend.supports(Capability.GROUP_TEXT) is True
    assert backend.supports(Capability.PRIVATE_TEXT) is True
    assert backend.supports(Capability.GROUP_IMAGE) is False
    assert backend.supports(Capability.GROUP_VOICE) is False
    assert backend.supports(Capability.SET_QQ_PROFILE) is False
    assert backend.supports(Capability.RAW_API) is False


def test_isinstance_botbackend():
    backend = _make_backend_without_init()
    assert isinstance(backend, BotBackend)


def test_set_dispatcher_stores_callback():
    backend = _make_backend_without_init()
    cb = MagicMock()
    backend.set_dispatcher(cb)
    assert backend._dispatch_callback is cb


def test_on_dispatch_safe_uses_run_coroutine_threadsafe():
    backend = _make_backend_without_init()
    mock_loop = MagicMock()
    mock_loop.is_closed.return_value = False
    backend._loop = mock_loop
    backend._dispatch_callback = MagicMock()

    incoming = IncomingMessage(scene=Scene.PRIVATE, user_id="u1", text="hello")
    with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
        with patch.object(backend, "_parse_to_incoming", return_value=incoming):
            backend._on_dispatch_safe({"t": "C2C_MESSAGE_CREATE", "d": {}})

    assert mock_rcts.called
    assert mock_rcts.call_args[0][1] is mock_loop


def test_on_dispatch_safe_skips_when_loop_not_ready():
    backend = _make_backend_without_init()
    backend._loop = None
    backend._dispatch_callback = MagicMock()

    with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
        backend._on_dispatch_safe({"t": "C2C_MESSAGE_CREATE", "d": {}})

    assert not mock_rcts.called


def test_on_dispatch_safe_skips_when_loop_closed():
    backend = _make_backend_without_init()
    backend._loop = MagicMock()
    backend._loop.is_closed.return_value = True
    backend._dispatch_callback = MagicMock()

    with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
        backend._on_dispatch_safe({"t": "C2C_MESSAGE_CREATE", "d": {}})

    assert not mock_rcts.called


def test_on_dispatch_safe_skips_when_callback_not_set():
    backend = _make_backend_without_init()
    backend._loop = MagicMock()
    backend._dispatch_callback = None

    with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
        backend._on_dispatch_safe({"t": "C2C_MESSAGE_CREATE", "d": {}})

    assert not mock_rcts.called


def test_on_dispatch_safe_handles_parse_error():
    backend = _make_backend_without_init()
    backend._loop = MagicMock()
    backend._loop.is_closed.return_value = False
    backend._dispatch_callback = MagicMock()

    with patch.object(backend, "_parse_to_incoming", side_effect=RuntimeError("parse fail")):
        backend._on_dispatch_safe({"t": "C2C_MESSAGE_CREATE", "d": {}})


def test_parse_to_incoming_returns_none_for_unmatched():
    backend = _make_backend_without_init()
    assert backend._parse_to_incoming({"t": "UNKNOWN_EVENT", "d": {}}) is None


def test_parse_to_incoming_private():
    backend = _make_backend_without_init(app_id="appid")
    raw_event = {
        "t": "C2C_MESSAGE_CREATE",
        "d": {
            "id": "msg_1",
            "content": "hello",
            "author": {"user_openid": "u_openid_1"},
        },
    }
    inc = backend._parse_to_incoming(raw_event)
    assert inc is not None
    assert inc.scene == Scene.PRIVATE
    assert inc.user_id == "u_openid_1"
    assert inc.text == "hello"


def test_parse_to_incoming_group():
    backend = _make_backend_without_init(app_id="appid")
    raw_event = {
        "t": "GROUP_AT_MESSAGE_CREATE",
        "d": {
            "id": "msg_2",
            "content": "@bot hello",
            "author": {"user_openid": "u_openid_2"},
            "group_id": "g_openid_1",
            "group_openid": "g_openid_1",
        },
    }
    inc = backend._parse_to_incoming(raw_event)
    assert inc is not None
    assert inc.scene == Scene.GROUP
    assert inc.user_id == "u_openid_2"
    assert "g_openid_1" in (inc.group_id or "")


async def _async_send_private_text_calls_send_qqbot_message():
    backend = _make_backend_without_init()
    backend._token = "test_token"

    with patch("nbot.services.qqbot_service.send_qqbot_message") as mock_send:
        mock_send.return_value = {"ok": True}
        result = await backend.send_private_text("u1", "hi")

    assert result is True
    args, _ = mock_send.call_args
    assert args[0] == "test_token"
    assert args[1] == "https://api.sgroup.qq.com"
    assert args[3] == "hi"
    assert args[2]["user_id"] == "u1"
    assert args[2]["metadata"]["qqbot_scene"] == "private"
    assert args[2]["metadata"]["qqbot_user_openid"] == "u1"


def test_send_private_text_returns_false_when_token_missing():
    async def run():
        backend = _make_backend_without_init()
        assert await backend.send_private_text("u1", "hi") is False

    asyncio.run(run())


def test_send_private_text_calls_send_qqbot_message():
    asyncio.run(_async_send_private_text_calls_send_qqbot_message())


def test_send_group_text_calls_send_qqbot_message():
    async def run():
        backend = _make_backend_without_init()
        backend._token = "test_token"

        with patch("nbot.services.qqbot_service.send_qqbot_message") as mock_send:
            mock_send.return_value = {"ok": True}
            result = await backend.send_group_text("g1", "hi")

        assert result is True
        args, _ = mock_send.call_args
        assert args[2]["metadata"]["qqbot_scene"] == "group"
        assert args[2]["metadata"]["qqbot_group_openid"] == "g1"
        assert args[3] == "hi"

    asyncio.run(run())


def test_start_saves_gateway_url():
    async def run():
        backend = _make_backend_without_init()
        backend._creds["app_id"] = "test"
        backend._creds["app_secret"] = "test"

        with patch("nbot.services.qqbot_service.get_app_access_token", return_value="token"):
            with patch("nbot.services.qqbot_service.get_gateway", return_value="wss://test"):
                await backend.start()

        assert backend._token == "token"
        assert backend._gateway_url == "wss://test"
        assert backend.is_running is True
        assert backend._loop is None
        assert backend._ws_thread is None

    asyncio.run(run())


def test_ws_run_loop_stops_event_loop_when_websocket_returns():
    backend = _make_backend_without_init()
    loop = asyncio.new_event_loop()
    backend._loop = loop

    class FakeWebSocketApp:
        def __init__(self, *args, **kwargs):
            pass

        def run_forever(self):
            return None

    with patch("nbot.backends.qqbot_backend.websocket.WebSocketApp", FakeWebSocketApp):
        backend._ws_run_loop("wss://test")

    try:
        assert loop._ready
    finally:
        loop.close()
