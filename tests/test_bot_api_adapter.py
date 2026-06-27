"""测试 nbot.bot_api_adapter.BotApiAdapter

阶段 2 实施:验证 BotApiAdapter 包装 ncatbot BotAPI 后,
所有调用内部走 get_backend() 抽象。
"""
import asyncio
from unittest.mock import MagicMock

import pytest

from nbot.bot_api_adapter import BotApiAdapter
from nbot.commands_backend import (
    reset_backend,
    set_backend,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_backend()
    yield
    reset_backend()


class FakeBotApi:
    """Fake ncatbot BotAPI 实例"""
    def __init__(self):
        self.calls = []

    async def post_private_msg(self, user_id, **kwargs):
        self.calls.append(("post_private_msg", user_id, kwargs))
        return True

    async def post_group_msg(self, group_id, **kwargs):
        self.calls.append(("post_group_msg", group_id, kwargs))
        return True

    async def post_group_file(self, group_id, **kwargs):
        self.calls.append(("post_group_file", group_id, kwargs))
        return True

    async def upload_private_file(self, user_id, file, name=None, **kwargs):
        self.calls.append(("upload_private_file", user_id, file, name))
        return True

    async def set_qq_profile(self, **kwargs):
        self.calls.append(("set_qq_profile", kwargs))
        return True

    async def set_online_status(self, status):
        self.calls.append(("set_online_status", status))
        return True

    async def set_qq_avatar(self, url):
        self.calls.append(("set_qq_avatar", url))
        return True

    async def send_like(self, user_id, times=1):
        self.calls.append(("send_like", user_id, times))
        return True

    async def set_group_admin(self, group_id, user_id, enable):
        self.calls.append(("set_group_admin", group_id, user_id, enable))
        return True

    async def set_friend_add_request(self, flag, approve, remark=""):
        self.calls.append(("set_friend_add_request", flag, approve, remark))
        return True

    async def get_group_msg_history(self, group_id, message_seq=0, count=20, reverse_order=True):
        self.calls.append(("get_group_msg_history", group_id, message_seq, count, reverse_order))
        return [{"msg": "fake"}]

    async def get_friend_list(self):
        return []

    async def get_msg(self, message_id):
        return {}

    async def get_recent_contact(self):
        return []


class FakeBackend:
    """Fake backend 实现 BotBackend + NcatbotAdminBackend"""
    name = "fake"
    is_running = True

    def __init__(self):
        self.calls = []

    async def start(self): pass
    def run_forever(self): pass
    async def stop(self): pass

    async def send_private_text(self, user_id, text):
        self.calls.append(("send_private_text", user_id, text))
        return True

    async def send_group_text(self, group_id, text):
        self.calls.append(("send_group_text", group_id, text))
        return True

    def supports(self, cap): return True

    async def set_qq_profile(self, **kwargs):
        self.calls.append(("set_qq_profile", kwargs))
        return True

    async def set_online_status(self, status):
        self.calls.append(("set_online_status", status))
        return True

    async def set_qq_avatar(self, url):
        self.calls.append(("set_qq_avatar", url))
        return True

    async def send_like(self, user_id, times=1):
        self.calls.append(("send_like", user_id, times))
        return True

    async def set_group_admin(self, group_id, user_id, enable):
        self.calls.append(("set_group_admin", group_id, user_id, enable))
        return True

    async def set_friend_add_request(self, flag, approve, remark=""):
        self.calls.append(("set_friend_add_request", flag, approve, remark))
        return True

    async def get_group_msg_history(self, group_id, count=20, **kwargs):
        self.calls.append(("get_group_msg_history", group_id, count, kwargs))
        return [{"msg": "fake"}]

    async def get_friend_list(self):
        return []

    async def get_msg(self, message_id):
        return {}

    async def get_recent_contact(self):
        return []

    async def get_file_sync(self, file_id):
        return {}

    async def download_file_sync(self, thread_count, headers, url):
        return b""


def _async_run(coro):
    return asyncio.run(coro)


# ====================== 文本消息走 backend ======================

def test_post_private_msg_text_uses_backend():
    """post_private_msg(user_id, text=...) 走 backend.send_private_text"""
    fb = FakeBackend()
    set_backend(fb)
    real = FakeBotApi()
    adapter = BotApiAdapter(real)

    _async_run(adapter.post_private_msg("u1", text="hello"))

    assert fb.calls == [("send_private_text", "u1", "hello")]
    # 真实 bot.api 不应该被调用
    assert real.calls == []


def test_post_group_msg_text_uses_backend():
    """post_group_msg(group_id, text=...) 走 backend.send_group_text"""
    fb = FakeBackend()
    set_backend(fb)
    real = FakeBotApi()
    adapter = BotApiAdapter(real)

    _async_run(adapter.post_group_msg("g1", text="hi"))

    assert fb.calls == [("send_group_text", "g1", "hi")]
    assert real.calls == []


# ====================== 富媒体走 ncatbot 原生(阶段 3 改造) ======================

def test_post_private_msg_rtf_uses_real():
    """post_private_msg(user_id, rtf=...) 走 ncatbot 原生(阶段 3 改造)"""
    fb = FakeBackend()
    set_backend(fb)
    real = FakeBotApi()
    adapter = BotApiAdapter(real)

    rtf_obj = MagicMock()
    _async_run(adapter.post_private_msg("u1", rtf=rtf_obj))

    # 真实 bot.api 被调用
    assert len(real.calls) == 1
    assert real.calls[0][0] == "post_private_msg"
    assert real.calls[0][1] == "u1"
    assert real.calls[0][2] == {"rtf": rtf_obj}
    # backend 不应该被调用
    assert fb.calls == []


def test_post_group_msg_rtf_uses_real():
    """post_group_msg(group_id, rtf=...) 走 ncatbot 原生"""
    fb = FakeBackend()
    set_backend(fb)
    real = FakeBotApi()
    adapter = BotApiAdapter(real)

    rtf_obj = MagicMock()
    _async_run(adapter.post_group_msg("g1", rtf=rtf_obj))

    assert len(real.calls) == 1
    assert real.calls[0][0] == "post_group_msg"
    assert real.calls[0][2] == {"rtf": rtf_obj}


def test_post_group_file_uses_real():
    """post_group_file 阶段 3 改造:暂走 ncatbot 原生"""
    fb = FakeBackend()
    set_backend(fb)
    real = FakeBotApi()
    adapter = BotApiAdapter(real)

    _async_run(adapter.post_group_file("g1", file="/tmp/file.zip"))

    assert len(real.calls) == 1
    assert real.calls[0][0] == "post_group_file"


def test_upload_private_file_uses_real():
    """upload_private_file 阶段 3 改造:暂走 ncatbot 原生"""
    fb = FakeBackend()
    set_backend(fb)
    real = FakeBotApi()
    adapter = BotApiAdapter(real)

    _async_run(adapter.upload_private_file("u1", "/tmp/file.zip", "doc.txt"))

    assert len(real.calls) == 1
    assert real.calls[0][0] == "upload_private_file"


# ====================== 管理类 API 走 backend(NcatbotAdminBackend) ======================

def test_set_qq_profile_uses_backend():
    """set_qq_profile 走 backend"""
    fb = FakeBackend()
    set_backend(fb)
    real = FakeBotApi()
    adapter = BotApiAdapter(real)

    _async_run(adapter.set_qq_profile(nickname="newnick"))

    assert fb.calls == [("set_qq_profile", {"nickname": "newnick"})]
    assert real.calls == []


def test_set_online_status_uses_backend():
    fb = FakeBackend()
    set_backend(fb)
    real = FakeBotApi()
    adapter = BotApiAdapter(real)

    _async_run(adapter.set_online_status(10))

    assert fb.calls == [("set_online_status", 10)]


def test_set_qq_avatar_uses_backend():
    fb = FakeBackend()
    set_backend(fb)
    real = FakeBotApi()
    adapter = BotApiAdapter(real)

    _async_run(adapter.set_qq_avatar("http://example.com/avatar.png"))

    assert fb.calls == [("set_qq_avatar", "http://example.com/avatar.png")]


def test_send_like_uses_backend():
    fb = FakeBackend()
    set_backend(fb)
    real = FakeBotApi()
    adapter = BotApiAdapter(real)

    _async_run(adapter.send_like("u1", times=5))

    assert fb.calls == [("send_like", "u1", 5)]


def test_set_group_admin_uses_backend():
    fb = FakeBackend()
    set_backend(fb)
    real = FakeBotApi()
    adapter = BotApiAdapter(real)

    _async_run(adapter.set_group_admin("g1", "u1", True))

    assert fb.calls == [("set_group_admin", "g1", "u1", True)]


def test_set_friend_add_request_uses_backend():
    fb = FakeBackend()
    set_backend(fb)
    real = FakeBotApi()
    adapter = BotApiAdapter(real)

    _async_run(adapter.set_friend_add_request("flag_1", True, "hi"))

    assert fb.calls == [("set_friend_add_request", "flag_1", True, "hi")]


# ====================== 查询类 API 走 backend ======================

def test_get_group_msg_history_uses_backend():
    """get_group_msg_history 走 backend,接受 ncatbot 风格参数"""
    fb = FakeBackend()
    set_backend(fb)
    real = FakeBotApi()
    adapter = BotApiAdapter(real)

    result = _async_run(
        adapter.get_group_msg_history("g1", message_seq=0, count=10, reverse_order=True)
    )

    assert isinstance(result, list)
    assert len(fb.calls) == 1
    assert fb.calls[0][0] == "get_group_msg_history"
    assert fb.calls[0][1] == "g1"
    assert fb.calls[0][2] == 10
    assert fb.calls[0][3] == {"message_seq": 0, "reverse_order": True}


# ====================== QQBot 路径降级 ======================

def test_admin_api_falls_back_when_backend_not_ncatbot():
    """QQBot 后端不支持管理类 API 时返回 False,不抛异常"""

    class QQBotOnlyBackend:
        name = "qqbot"
        is_running = True

        async def start(self): pass
        def run_forever(self): pass
        async def stop(self): pass
        async def send_private_text(self, u, t): return True
        async def send_group_text(self, g, t): return True
        def supports(self, cap): return False

    set_backend(QQBotOnlyBackend())
    real = FakeBotApi()
    adapter = BotApiAdapter(real)

    # 都不应该抛异常
    result1 = _async_run(adapter.set_qq_profile(nickname="x"))
    result2 = _async_run(adapter.set_online_status(10))
    result3 = _async_run(adapter.set_qq_avatar("url"))
    result4 = _async_run(adapter.send_like("u1"))
    result5 = _async_run(adapter.set_group_admin("g", "u", True))
    result6 = _async_run(adapter.set_friend_add_request("f", True))

    assert result1 is False
    assert result2 is False
    assert result3 is False
    assert result4 is False
    assert result5 is False
    assert result6 is False


def test_get_group_msg_history_falls_back_to_empty_list():
    """QQBot 不支持 get_group_msg_history 时返回空列表"""

    class QQBotOnlyBackend:
        name = "qqbot"
        is_running = True
        async def start(self): pass
        def run_forever(self): pass
        async def stop(self): pass
        async def send_private_text(self, u, t): return True
        async def send_group_text(self, g, t): return True
        def supports(self, cap): return False

    set_backend(QQBotOnlyBackend())
    adapter = BotApiAdapter(FakeBotApi())
    result = _async_run(adapter.get_group_msg_history("g1"))
    assert result == []
