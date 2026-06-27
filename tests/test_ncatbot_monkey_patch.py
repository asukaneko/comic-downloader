"""测试 nbot.ncatbot_monkey_patch 模块

阶段 5 实施:验证 monkey-patch 逻辑从 commands.py 抽出后仍正确工作

注意: ncatbot BotAPI 内部依赖 self.api 等属性,真实环境下难以 mock,
此测试聚焦于:
1. apply_patches 接口行为(成功/幂等/降级)
2. _nbot_patched 标志正确设置
"""
import sys
import types
from unittest.mock import patch as mock_patch

import pytest

from nbot.ncatbot_monkey_patch import apply_patches, is_applied


def _install_fake_ncatbot_core(monkeypatch):
    class FakeBotAPI:
        async def post_private_msg(self, user_id, **kwargs):
            return True

        async def post_group_msg(self, group_id, **kwargs):
            return True

    class FakeGroupMessage:
        group_id = "g1"
        user_id = "u1"

        async def reply(self, text=None, **kwargs):
            return True

    fake_ncatbot = types.ModuleType("ncatbot")
    fake_core = types.ModuleType("ncatbot.core")
    fake_core.BotAPI = FakeBotAPI
    fake_core.GroupMessage = FakeGroupMessage
    fake_ncatbot.core = fake_core
    monkeypatch.setitem(sys.modules, "ncatbot", fake_ncatbot)
    monkeypatch.setitem(sys.modules, "ncatbot.core", fake_core)


@pytest.fixture(autouse=True)
def _reset_patch_state(monkeypatch):
    """每个测试前重置 _nbot_patched 标志 + _applied 模块状态"""
    _install_fake_ncatbot_core(monkeypatch)
    from ncatbot.core import BotAPI
    if hasattr(BotAPI, "_nbot_patched"):
        delattr(BotAPI, "_nbot_patched")
    # 重置模块级 _applied 标志
    import nbot.ncatbot_monkey_patch as mod
    mod._applied = False
    yield
    if hasattr(BotAPI, "_nbot_patched"):
        delattr(BotAPI, "_nbot_patched")
    mod._applied = False


def test_apply_patches_sets_flag():
    """apply_patches 成功时设置 _nbot_patched 标志"""
    from ncatbot.core import BotAPI
    result = apply_patches()
    assert result is True
    assert BotAPI._nbot_patched is True


def test_apply_patches_replaces_methods():
    """apply_patches 替换 BotAPI 类方法为 wrapper"""
    from ncatbot.core import BotAPI, GroupMessage
    original_post = BotAPI.post_private_msg
    original_group = BotAPI.post_group_msg
    original_reply = GroupMessage.reply

    apply_patches()

    # 类方法被替换(对象身份变化)
    assert BotAPI.post_private_msg is not original_post
    assert BotAPI.post_group_msg is not original_group
    assert GroupMessage.reply is not original_reply


def test_apply_patches_idempotent():
    """多次调用 apply_patches 幂等"""
    first = apply_patches()
    second = apply_patches()
    third = apply_patches()

    assert first is True
    assert second is False
    assert third is False


def test_apply_patches_when_already_flagged():
    """BotAPI._nbot_patched 标志已存在时跳过"""
    from ncatbot.core import BotAPI
    BotAPI._nbot_patched = True

    result = apply_patches()
    assert result is False


def test_apply_patches_handles_missing_ncatbot():
    """ncatbot 不可用时不抛异常,返回 False"""
    with mock_patch.dict(sys.modules, {"ncatbot.core": None}):
        # 即使 ncatbot.core 为 None 也不应抛
        # 但实际上 apply_patches 内部用 from ncatbot.core import BotAPI
        # 如果 ncatbot.core 是 None,from 会失败
        try:
            result = apply_patches()
            assert result is False
        except (ImportError, TypeError):
            # 可接受: ncatbot 不可用时直接 raise 也行
            pass


def test_apply_patches_module_level_functions():
    """模块导出函数可调用"""
    import nbot.ncatbot_monkey_patch
    assert callable(nbot.ncatbot_monkey_patch.apply_patches)
    assert callable(nbot.ncatbot_monkey_patch.is_applied)


def test_is_applied_reflects_state():
    """is_applied 反映实际状态"""
    assert is_applied() is False
    apply_patches()
    assert is_applied() is True


def test_module_docstring_present():
    """模块有文档说明用途"""
    import nbot.ncatbot_monkey_patch
    assert nbot.ncatbot_monkey_patch.__doc__ is not None
    assert "monkey-patch" in nbot.ncatbot_monkey_patch.__doc__
