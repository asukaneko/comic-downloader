"""测试 nbot.commands_backend 核心抽象层"""
import asyncio

import pytest

from nbot.commands_backend import (
    BotBackend,
    Capability,
    IncomingMessage,
    MediaBackend,
    NcatbotAdminBackend,
    RawApiBackend,
    Scene,
    get_backend,
    reset_backend,
    set_backend,
)


class FakeBackend:
    """最小 BotBackend 实现,用于测试"""
    name = "fake"
    is_running = True

    def __init__(self):
        self.sent = []
        self.started = False
        self.stopped = False
        self.run_called = False

    async def start(self):
        self.started = True

    def run_forever(self):
        self.run_called = True

    async def stop(self):
        self.stopped = True

    async def send_private_text(self, user_id, text):
        self.sent.append(("private", user_id, text))
        return True

    async def send_group_text(self, group_id, text):
        self.sent.append(("group", group_id, text))
        return True

    def supports(self, capability):
        return capability in (Capability.GROUP_TEXT, Capability.PRIVATE_TEXT)


@pytest.fixture(autouse=True)
def _reset():
    """每个测试前重置全局后端"""
    reset_backend()
    yield
    reset_backend()


def test_incoming_message_basic_fields():
    """验证 IncomingMessage 基本字段"""
    inc = IncomingMessage(
        scene=Scene.GROUP,
        user_id="user_1",
        group_id="group_1",
        text="hello",
        sender_name="Alice",
    )
    assert inc.scene == Scene.GROUP
    assert inc.user_id == "user_1"
    assert inc.group_id == "group_1"
    assert inc.text == "hello"
    assert inc.sender_name == "Alice"
    assert inc.is_group is True
    assert inc.backend_name == "unknown"


def test_incoming_message_private_scene():
    """验证 PRIVATE 场景"""
    inc = IncomingMessage(scene=Scene.PRIVATE, user_id="u1", text="hi")
    assert inc.is_group is False
    assert inc.group_id == ""


def test_incoming_message_legacy_compat():
    """验证 __getattr__ 兼容层 fallback 到 _legacy_msg"""
    legacy = type("L", (), {
        "message": ["seg1", "seg2"],
        "self_id": "999",
        "sender": type("S", (), {"nickname": "Bob"})(),
    })()
    inc = IncomingMessage(
        scene=Scene.GROUP, user_id="u1", text="hi", _legacy_msg=legacy
    )
    assert inc.message == ["seg1", "seg2"]
    assert inc.self_id == "999"
    assert inc.sender.nickname == "Bob"


def test_incoming_message_legacy_compat_missing_attr():
    """验证不存在的属性抛 AttributeError"""
    inc = IncomingMessage(scene=Scene.GROUP, user_id="u1", text="hi")
    with pytest.raises(AttributeError):
        _ = inc.nonexistent_attr


def test_get_backend_before_set_raises():
    """未设置后端时调用 get_backend 抛 RuntimeError"""
    with pytest.raises(RuntimeError, match="not initialized"):
        get_backend()


def test_set_and_get_backend():
    """设置后能正确取出"""
    fb = FakeBackend()
    set_backend(fb)
    assert get_backend() is fb
    assert get_backend().name == "fake"


def test_incoming_reply_uses_backend():
    """IncomingMessage.reply 走 backend.send_*_text"""
    async def run():
        fb = FakeBackend()
        set_backend(fb)
        inc = IncomingMessage(
            scene=Scene.GROUP, user_id="u1", group_id="g1", text="hi"
        )
        result = await inc.reply("hello")
        assert result is True
        assert fb.sent == [("group", "g1", "hello")]

        inc_priv = IncomingMessage(scene=Scene.PRIVATE, user_id="u1", text="hi")
        await inc_priv.reply("private hello")
        assert ("private", "u1", "private hello") in fb.sent
    asyncio.run(run())


def test_incoming_reply_none_text_returns_false():
    """reply(text=None) 返回 False"""
    async def run():
        fb = FakeBackend()
        set_backend(fb)
        inc = IncomingMessage(scene=Scene.GROUP, user_id="u1", group_id="g1", text="hi")
        result = await inc.reply(None)
        assert result is False
        assert fb.sent == []
    asyncio.run(run())


def test_fake_backend_isinstance_botbackend():
    """FakeBackend 是 BotBackend 协议的运行时实例"""
    fb = FakeBackend()
    assert isinstance(fb, BotBackend)


def test_fake_backend_not_media():
    """FakeBackend 不实现 MediaBackend(没定义 send_group_image 等)"""
    fb = FakeBackend()
    assert not isinstance(fb, MediaBackend)
    assert not isinstance(fb, NcatbotAdminBackend)
    assert not isinstance(fb, RawApiBackend)


def test_supports_returns_capability():
    """FakeBackend.supports 返回正确的 capability"""
    fb = FakeBackend()
    assert fb.supports(Capability.GROUP_TEXT) is True
    assert fb.supports(Capability.PRIVATE_TEXT) is True
    assert fb.supports(Capability.GROUP_IMAGE) is False


def test_capability_constants():
    """Capability 常量值"""
    assert Capability.GROUP_TEXT == "group_text"
    assert Capability.PRIVATE_TEXT == "private_text"
    assert Capability.GROUP_IMAGE == "group_image"
    assert Capability.GROUP_VOICE == "group_voice"
    assert Capability.SET_QQ_PROFILE == "set_qq_profile"
    assert Capability.RAW_API == "raw_api"
