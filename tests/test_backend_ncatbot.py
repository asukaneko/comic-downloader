"""测试 nbot.backends.ncatbot_backend.NcatbotBackend"""
import asyncio
from unittest.mock import MagicMock

import pytest

from nbot.backends.ncatbot_backend import NcatbotBackend
from nbot.commands_backend import (
    BotBackend,
    Capability,
    IncomingMessage,
    Scene,
    reset_backend,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_backend()
    yield
    reset_backend()


def _make_backend_without_init():
    """跳过 NcatbotBackend.__init__(避免实际创建 BotClient)"""
    backend = NcatbotBackend.__new__(NcatbotBackend)
    backend.bot = MagicMock()
    backend._real_api = backend.bot.api  # P0 修复: 保存真实 API 引用
    backend._dispatch_callback = None
    backend.is_running = False
    return backend


def _make_mock_msg(user_id="123", group_id="456", raw="hello", sender_nick="Alice"):
    """构造 mock ncatbot msg 对象"""
    msg = MagicMock()
    msg.user_id = user_id
    msg.group_id = group_id
    msg.raw_message = raw
    msg.message_id = "m_1"
    msg.self_id = "999"
    msg.sender.nickname = sender_nick
    msg.message = []
    return msg


def test_to_incoming_group_message():
    """_to_incoming 正确转换 group 消息"""
    backend = _make_backend_without_init()
    msg = _make_mock_msg()
    inc = backend._to_incoming(msg, Scene.GROUP)

    assert isinstance(inc, IncomingMessage)
    assert inc.scene == Scene.GROUP
    assert inc.user_id == "123"
    assert inc.group_id == "456"
    assert inc.text == "hello"
    assert inc.raw_message == "hello"
    assert inc.sender_name == "Alice"
    assert inc.message_id == "m_1"
    assert inc.backend_name == "ncatbot"
    assert inc.is_group is True
    assert inc._legacy_msg is msg


def test_to_incoming_private_message():
    """_to_incoming 正确转换 private 消息"""
    backend = _make_backend_without_init()
    msg = _make_mock_msg()
    inc = backend._to_incoming(msg, Scene.PRIVATE)

    assert inc.scene == Scene.PRIVATE
    assert inc.user_id == "123"
    assert inc.group_id == ""
    assert inc.is_group is False


def test_detect_mention_true():
    """_detect_mention 正确识别 @机器人"""
    backend = _make_backend_without_init()
    msg = _make_mock_msg()
    msg.message = [
        {"type": "at", "data": {"qq": "999"}},
        {"type": "text", "data": {"text": "hello"}},
    ]
    inc = backend._to_incoming(msg, Scene.GROUP)
    assert inc.is_mentioned is True


def test_detect_mention_false():
    """_detect_mention 正确识别未 @机器人"""
    backend = _make_backend_without_init()
    msg = _make_mock_msg()
    msg.message = [
        {"type": "at", "data": {"qq": "111"}},
        {"type": "text", "data": {"text": "hello"}},
    ]
    inc = backend._to_incoming(msg, Scene.GROUP)
    assert inc.is_mentioned is False


async def _async_test_send_private_text_calls_bot_api():
    """send_private_text 调 bot.api.post_private_msg"""
    backend = _make_backend_without_init()
    backend.bot.api.post_private_msg = MagicMock(
        return_value=asyncio.Future()
    )
    backend.bot.api.post_private_msg.return_value.set_result(True)

    result = await backend.send_private_text("u1", "hi")
    assert result is True
    backend.bot.api.post_private_msg.assert_called_once_with(
        user_id="u1", text="hi"
    )


async def _async_test_send_group_text_calls_bot_api():
    """send_group_text 调 bot.api.post_group_msg"""
    backend = _make_backend_without_init()
    backend.bot.api.post_group_msg = MagicMock(return_value=asyncio.Future())
    backend.bot.api.post_group_msg.return_value.set_result(True)

    result = await backend.send_group_text("g1", "hi")
    assert result is True
    backend.bot.api.post_group_msg.assert_called_once_with(
        group_id="g1", text="hi"
    )


def test_send_private_text_calls_bot_api():
    """同步包装:send_private_text"""
    asyncio.run(_async_test_send_private_text_calls_bot_api())


def test_send_group_text_calls_bot_api():
    """同步包装:send_group_text"""
    asyncio.run(_async_test_send_group_text_calls_bot_api())


def test_supports_returns_true_for_all():
    """NcatbotBackend.supports 对所有 capability 返回 True"""
    backend = _make_backend_without_init()
    assert backend.supports(Capability.GROUP_TEXT) is True
    assert backend.supports(Capability.GROUP_IMAGE) is True
    assert backend.supports(Capability.SET_QQ_PROFILE) is True
    assert backend.supports(Capability.RAW_API) is True


def test_isinstance_botbackend():
    """NcatbotBackend 是 BotBackend 协议"""
    backend = _make_backend_without_init()
    assert isinstance(backend, BotBackend)


def test_set_dispatcher_stores_callback():
    """set_dispatcher 存储回调"""
    backend = _make_backend_without_init()
    cb = MagicMock()
    backend.set_dispatcher(cb)
    assert backend._dispatch_callback is cb


# ====================== P0 回归测试: ncatbot 发送链路不递归 ======================

def test_start_wraps_api_but_backend_uses_real_api():
    """P0 回归: start() 包装 bot.api 为 BotApiAdapter,但 backend 内部方法调真实 API 不递归"""
    from unittest.mock import patch

    async def run_test():
        real_api = MagicMock()
        real_api.post_group_msg = MagicMock(return_value=asyncio.Future())
        real_api.post_group_msg.return_value.set_result(True)
        real_api.post_private_msg = MagicMock(return_value=asyncio.Future())
        real_api.post_private_msg.return_value.set_result(True)

        fake_bot = MagicMock()
        fake_bot.api = real_api

        fake_client_class = MagicMock(return_value=fake_bot)

        with patch("ncatbot.core.BotClient", fake_client_class):
            with patch("nbot.ncatbot_monkey_patch.apply_patches"):
                backend = NcatbotBackend()
                await backend.start()

        # start() 后 bot.api 被包装成 BotApiAdapter
        from nbot.bot_api_adapter import BotApiAdapter
        assert isinstance(fake_bot.api, BotApiAdapter)

        # 但 backend 内部仍引用真实 API
        assert backend._real_api is real_api

        # 调用 backend.send_group_text 应直接调 real_api.post_group_msg,不经过 adapter
        await backend.send_group_text("g1", "hi")
        real_api.post_group_msg.assert_called_once_with(group_id="g1", text="hi")

    asyncio.run(run_test())


def test_adapter_text_uses_backend_without_recursion_on_ncatbot():
    """P0 回归: adapter.post_group_msg(text=) 调 backend.send_group_text,
    backend 调真实 API,不会循环回 adapter"""
    from unittest.mock import patch

    from nbot.commands_backend import set_backend

    async def run_test():
        real_api = MagicMock()
        real_api.post_group_msg = MagicMock(return_value=asyncio.Future())
        real_api.post_group_msg.return_value.set_result(True)

        fake_bot = MagicMock()
        fake_bot.api = real_api

        with patch("ncatbot.core.BotClient", MagicMock(return_value=fake_bot)):
            with patch("nbot.ncatbot_monkey_patch.apply_patches"):
                backend = NcatbotBackend()
                await backend.start()
                set_backend(backend)

        adapter = fake_bot.api  # BotApiAdapter
        await adapter.post_group_msg("g1", text="hi")
        real_api.post_group_msg.assert_called_once_with(group_id="g1", text="hi")

    asyncio.run(run_test())


def test_ncatbot_backend_get_file_sync_is_sync():
    """P1 回归: get_file_sync 是同步方法,与 Protocol 一致"""
    backend = _make_backend_without_init()
    backend._real_api = MagicMock()
    backend._real_api.get_file_sync = MagicMock(return_value={"path": "/tmp/test.jpg"})

    # 直接调用,不应返回 coroutine
    result = backend.get_file_sync("file_123")
    assert isinstance(result, dict)
    assert result == {"path": "/tmp/test.jpg"}
    backend._real_api.get_file_sync.assert_called_once_with(file_id="file_123")


def test_ncatbot_backend_download_file_sync_is_sync():
    """P1 回归: download_file_sync 是同步方法,与 Protocol 一致"""
    backend = _make_backend_without_init()
    backend._real_api = MagicMock()
    backend._real_api.download_file_sync = MagicMock(return_value=b"fake_data")

    # 直接调用,不应返回 coroutine
    result = backend.download_file_sync(1, {}, "http://example.com/file.jpg")
    assert isinstance(result, bytes)
    assert result == b"fake_data"
    backend._real_api.download_file_sync.assert_called_once_with(
        thread_count=1, headers={}, url="http://example.com/file.jpg"
    )
