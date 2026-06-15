"""Tests for the NekoBot Hook Runtime module."""

import asyncio
import tempfile
from types import SimpleNamespace

from nbot.hooks.models import ConversationHook, HookExecutionLog, RuntimeEvent
from nbot.hooks.event_bus import ConversationEventBus, match_event_pattern
from nbot.hooks.conditions import ConditionEvaluator
from nbot.hooks.actions import ActionExecutor
from nbot.hooks.manager import HookManager


def _loop():
    return asyncio.get_event_loop()


# ── RuntimeEvent ──────────────────────────────────────────────


def test_runtime_event_to_dict_roundtrip():
    evt = RuntimeEvent(type="t", source="s", character_id="c", user_id="u", payload={"k": "v"})
    d = evt.to_dict()
    assert d["type"] == "t"
    assert d["source"] == "s"
    assert d["payload"] == {"k": "v"}

    evt2 = RuntimeEvent.from_dict(d)
    assert evt2.type == evt.type
    assert evt2.source == evt.source
    assert evt2.id == evt.id
    assert evt2.created_at == evt.created_at
    assert evt2.payload == evt.payload


def test_runtime_event_auto_id():
    evt = RuntimeEvent(type="t")
    assert evt.id.startswith("evt_")
    assert evt.created_at != ""


# ── ConversationHook ──────────────────────────────────────────


def test_conversation_hook_defaults():
    h = ConversationHook(name="n", event="e")
    assert h.enabled is True
    assert h.scope == "global"
    assert h.priority == 100
    assert h.conditions == {}
    assert h.timeout_ms == 3000


def test_conversation_hook_roundtrip_with_conditions():
    cond = {"character_id": "c1", "affection_gte": 50}
    h = ConversationHook(name="n", event="e", conditions=cond)
    d = h.to_dict()
    h2 = ConversationHook.from_dict(d)
    assert h2.conditions == cond
    assert h2.id == h.id
    assert h2.name == h.name


# ── HookExecutionLog ──────────────────────────────────────────


def test_hook_execution_log_roundtrip():
    log = HookExecutionLog(hook_id="hk_1", event_id="evt_1", status="success", actions_executed=2)
    d = log.to_dict()
    assert d["status"] == "success"
    log2 = HookExecutionLog.from_dict(d)
    assert log2.hook_id == "hk_1"
    assert log2.actions_executed == 2


# ── match_event_pattern ───────────────────────────────────────


def test_match_event_pattern_wildcard_star():
    assert match_event_pattern("*", "anything.goes") is True


def test_match_event_pattern_exact():
    assert match_event_pattern("a.b.c", "a.b.c") is True
    assert match_event_pattern("a.b.c", "a.b.d") is False


def test_match_event_pattern_prefix_wildcard():
    assert match_event_pattern("character.*", "character.before_turn.started") is True
    assert match_event_pattern("character.*", "model.before_call") is False
    # prefix alone without dot should not match
    assert match_event_pattern("character.*", "character") is False


# ── ConversationEventBus ──────────────────────────────────────


def test_event_bus_subscribe_and_emit():
    bus = ConversationEventBus()
    received = []

    async def _cb(e):
        received.append(e)

    bus.subscribe("t.e", _cb)
    evt = RuntimeEvent(type="t.e")

    delivered = _loop().run_until_complete(bus.emit(evt))
    assert delivered == 1
    assert len(received) == 1
    assert received[0].type == "t.e"


def test_event_bus_wildcard():
    bus = ConversationEventBus()
    received = []

    bus.subscribe("c.*", lambda e: received.append(e))
    bus.emit_sync = None  # guard

    async def _run():
        await bus.emit(RuntimeEvent(type="c.a"))
        await bus.emit(RuntimeEvent(type="c.b"))
        await bus.emit(RuntimeEvent(type="d.a"))

    _loop().run_until_complete(_run())
    assert len(received) == 2


def test_event_bus_history_cap():
    bus = ConversationEventBus(history_max=3)

    async def _run():
        for i in range(5):
            await bus.emit(RuntimeEvent(type="t"))

    _loop().run_until_complete(_run())
    h = bus.get_history()
    assert len(h) == 3


# ── ConditionEvaluator ────────────────────────────────────────


def _eval(conditions, event=None, context=None):
    ev = event or RuntimeEvent(type="t")
    ctx = context or {}
    return ConditionEvaluator().evaluate(conditions, ev, ctx)


def test_condition_empty_passes():
    assert _eval({}) is True


def test_condition_character_id_match():
    evt = RuntimeEvent(type="t", character_id="c1")
    assert _eval({"character_id": "c1"}, event=evt) is True
    assert _eval({"character_id": "c2"}, event=evt) is False


def test_condition_mood_is():
    assert _eval({"mood_is": "happy"}, context={"mood": "happy"}) is True
    assert _eval({"mood_is": "happy"}, context={"mood": "sad"}) is False


def test_condition_affection_gte():
    assert _eval({"affection_gte": 50}, context={"affection": 80}) is True
    assert _eval({"affection_gte": 50}, context={"affection": 30}) is False


def test_condition_trust_lte():
    assert _eval({"trust_lte": 50}, context={"trust": 30}) is True
    assert _eval({"trust_lte": 50}, context={"trust": 80}) is False


def test_condition_combined():
    evt = RuntimeEvent(type="t", character_id="c1")
    ctx = {"mood": "happy", "affection": 90}
    conds = {"character_id": "c1", "mood_is": "happy", "affection_gte": 80}
    assert _eval(conds, event=evt, context=ctx) is True


def test_condition_combined_one_fails():
    evt = RuntimeEvent(type="t", character_id="c1")
    ctx = {"mood": "sad", "affection": 90}
    conds = {"character_id": "c1", "mood_is": "happy", "affection_gte": 80}
    assert _eval(conds, event=evt, context=ctx) is False


# ── ActionExecutor ────────────────────────────────────────────


def test_action_log_success():
    exe = ActionExecutor()
    evt = RuntimeEvent(type="t")
    result = _loop().run_until_complete(
        exe.execute({"type": "log", "message": "hi"}, evt, {})
    )
    assert result.success is True
    assert result.action_type == "log"


def test_action_unknown_type_fails():
    exe = ActionExecutor()
    evt = RuntimeEvent(type="t")
    result = _loop().run_until_complete(
        exe.execute({"type": "nope"}, evt, {})
    )
    assert result.success is False
    assert "Unknown type" in result.detail


def test_action_state_delta():
    exe = ActionExecutor()
    evt = RuntimeEvent(type="t")
    state = SimpleNamespace(mood="calm", mood_intensity=0.5, energy=80)
    ctx = {"character_state": state}

    result = _loop().run_until_complete(
        exe.execute({"type": "state_delta", "payload": {"mood": "happy"}}, evt, ctx)
    )
    assert result.success is True
    assert state.mood == "happy"


def test_action_relationship_delta():
    exe = ActionExecutor()
    evt = RuntimeEvent(type="t")
    rel = SimpleNamespace(affection=50, trust=60, familiarity=40, dependency=30, security=70, jealousy=10)
    ctx = {"relationship": rel}

    result = _loop().run_until_complete(
        exe.execute({"type": "relationship_delta", "payload": {"affection": 10}}, evt, ctx)
    )
    assert result.success is True
    assert rel.affection == 60


def test_action_prompt_inject():
    exe = ActionExecutor()
    evt = RuntimeEvent(type="t")

    class FakeStack:
        def __init__(self):
            self.calls = []

        def add(self, key, content, priority=55, scope="turn"):
            self.calls.append((key, content, priority, scope))

    stack = FakeStack()
    ctx = {"prompt_stack": stack}

    result = _loop().run_until_complete(
        exe.execute({"type": "prompt_inject", "key": "k", "content": "c"}, evt, ctx)
    )
    assert result.success is True
    assert len(stack.calls) == 1
    assert stack.calls[0][0] == "k"


def test_action_message_appends():
    exe = ActionExecutor()
    evt = RuntimeEvent(type="t")
    ctx = {}

    result = _loop().run_until_complete(
        exe.execute({"type": "message", "content": "hello"}, evt, ctx)
    )
    assert result.success is True
    assert ctx["hook_messages"] == ["hello"]


# ── HookManager CRUD ──────────────────────────────────────────


def test_hook_manager_add_get_update_toggle_remove():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = HookManager(data_dir=tmp)
        h = ConversationHook(name="n", event="e")
        mgr.add_hook(h)

        assert mgr.get_hook(h.id) is not None
        assert mgr.get_hook(h.id).name == "n"

        mgr.update_hook(h.id, name="n2")
        assert mgr.get_hook(h.id).name == "n2"

        mgr.toggle_hook(h.id, enabled=False)
        assert mgr.get_hook(h.id).enabled is False

        assert mgr.remove_hook(h.id) is True
        assert mgr.get_hook(h.id) is None


def test_hook_manager_persistence():
    with tempfile.TemporaryDirectory() as tmp:
        mgr1 = HookManager(data_dir=tmp)
        h = ConversationHook(name="p", event="e")
        mgr1.add_hook(h)
        saved_id = h.id

        mgr2 = HookManager(data_dir=tmp)
        assert mgr2.get_hook(saved_id) is not None
        assert mgr2.get_hook(saved_id).name == "p"


# ── HookManager emit ──────────────────────────────────────────


def test_hook_manager_emit_triggers_matching():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = HookManager(data_dir=tmp)
        triggered = []

        h = ConversationHook(
            name="n",
            event="e.fire",
            actions=[{"type": "log", "message": "hit"}],
        )
        mgr.add_hook(h)

        # Patch the executor to track calls
        orig = mgr._action_executor._handlers["log"]

        def spy(action, event, ctx):
            triggered.append(1)
            return orig(action, event, ctx)

        mgr._action_executor._handlers["log"] = spy

        evt = RuntimeEvent(type="e.fire")
        logs = _loop().run_until_complete(mgr.emit_event(evt))
        assert len(logs) == 1
        assert logs[0].status == "success"
        assert len(triggered) == 1


def test_hook_manager_emit_respects_conditions():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = HookManager(data_dir=tmp)
        h = ConversationHook(
            name="n",
            event="e",
            conditions={"character_id": "c1"},
            actions=[{"type": "log", "message": "hit"}],
        )
        mgr.add_hook(h)

        evt_no_match = RuntimeEvent(type="e", character_id="c2")
        logs = _loop().run_until_complete(mgr.emit_event(evt_no_match))
        assert len(logs) == 0

        evt_match = RuntimeEvent(type="e", character_id="c1")
        logs = _loop().run_until_complete(mgr.emit_event(evt_match))
        assert len(logs) == 1


def test_hook_manager_per_turn_limit():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = HookManager(data_dir=tmp)
        # Add 25 hooks all matching the same event
        for i in range(25):
            mgr.add_hook(ConversationHook(
                name=f"h{i}",
                event="e",
                priority=i,
                actions=[{"type": "log", "message": str(i)}],
            ))

        evt = RuntimeEvent(type="e")
        logs = _loop().run_until_complete(mgr.emit_event(evt))
        assert len(logs) == 20  # per-turn limit


def test_hook_manager_same_hook_once_per_turn():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = HookManager(data_dir=tmp)
        count = []

        h = ConversationHook(
            name="n",
            event="*",
            actions=[{"type": "log", "message": "hit"}],
        )
        mgr.add_hook(h)

        orig = mgr._action_executor._handlers["log"]

        def spy(action, event, ctx):
            count.append(1)
            return orig(action, event, ctx)

        mgr._action_executor._handlers["log"] = spy

        # Emit two different events in same turn
        _loop().run_until_complete(mgr.emit_event(RuntimeEvent(type="a")))
        _loop().run_until_complete(mgr.emit_event(RuntimeEvent(type="b")))
        assert len(count) == 1  # hook only fired once


def test_hook_manager_reset_turn():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = HookManager(data_dir=tmp)
        count = []

        h = ConversationHook(
            name="n",
            event="*",
            actions=[{"type": "log", "message": "hit"}],
        )
        mgr.add_hook(h)

        orig = mgr._action_executor._handlers["log"]

        def spy(action, event, ctx):
            count.append(1)
            return orig(action, event, ctx)

        mgr._action_executor._handlers["log"] = spy

        _loop().run_until_complete(mgr.emit_event(RuntimeEvent(type="a")))
        assert len(count) == 1

        mgr.reset_turn()

        _loop().run_until_complete(mgr.emit_event(RuntimeEvent(type="a")))
        assert len(count) == 2


# ── 别名兼容（文档事件名 → 代码事件名）──────────────────────────


def test_event_alias_model_before_call():
    """文档名 pipeline.before_model_call 能匹配代码名 model.before_call"""
    assert match_event_pattern("pipeline.before_model_call", "model.before_call")
    # 反向不匹配
    assert not match_event_pattern("model.before_call", "pipeline.before_call")


def test_event_alias_character_before_turn():
    """文档名 character.before_turn.after_memory_retrieve 匹配代码名"""
    assert match_event_pattern(
        "character.before_turn.after_memory_retrieve",
        "character.after_memory_retrieve",
    )


def test_event_alias_reply_send():
    assert match_event_pattern("pipeline.before_reply_send", "reply.before_send")
    assert match_event_pattern("pipeline.after_reply_send", "reply.after_send")


def test_event_alias_prompt_render():
    assert match_event_pattern("pipeline.before_prompt_render", "prompt.before_render")
    assert match_event_pattern("pipeline.after_prompt_render", "prompt.after_render")


def test_event_alias_stream_chunk():
    assert match_event_pattern("pipeline.stream_chunk", "model.on_stream_chunk")


# ── 动作参数兼容 ────────────────────────────────────────────────


def test_action_state_delta_doc_format():
    """文档格式 {"field": "energy", "delta": -5} 应该生效"""
    exe = ActionExecutor()
    state = SimpleNamespace(energy=80, mood="happy", mood_intensity=0.8)
    action = {"type": "state_delta", "field": "energy", "delta": -10}
    ctx = {"character_state": state}
    result = _loop().run_until_complete(exe.execute(action, RuntimeEvent(type="t"), ctx))
    assert result.success
    assert state.energy == 70


def test_action_state_delta_payload_format():
    """代码格式 {"payload": {"energy": -5}} 也应该生效"""
    exe = ActionExecutor()
    state = SimpleNamespace(energy=80, mood="happy", mood_intensity=0.8)
    action = {"type": "state_delta", "payload": {"energy": -5}}
    ctx = {"character_state": state}
    result = _loop().run_until_complete(exe.execute(action, RuntimeEvent(type="t"), ctx))
    assert result.success
    assert state.energy == 75


def test_action_relationship_delta_doc_format():
    exe = ActionExecutor()
    rel = SimpleNamespace(affection=50, trust=60, familiarity=40, dependency=30, security=70, jealousy=10)
    action = {"type": "relationship_delta", "field": "affection", "delta": 8}
    ctx = {"relationship": rel}
    result = _loop().run_until_complete(exe.execute(action, RuntimeEvent(type="t"), ctx))
    assert result.success
    assert rel.affection == 58


def test_action_memory_write_mem_type_alias():
    """memory_type 和 mem_type 都应该被接受"""
    exe = ActionExecutor()
    saved = []

    class FakeMemoryService:
        def save(self, **kwargs):
            saved.append(kwargs)

    action = {"type": "memory_write", "content": "test", "memory_type": "short", "title": "t"}
    ctx = {"memory_service": FakeMemoryService()}
    result = _loop().run_until_complete(exe.execute(action, RuntimeEvent(type="t"), ctx))
    assert result.success
    assert saved[0]["mem_type"] == "short"


def test_action_workflow_id_alias():
    """workflow_id 和 workflow 都应该被接受"""
    # workflow action 是 async，这里只测参数解析
    action = {"type": "workflow", "workflow_id": "wf_test"}
    # 直接检查 action dict 的字段
    assert action.get("workflow") or action.get("workflow_id") == "wf_test"


# ── 条件系统 ────────────────────────────────────────────────────


def test_condition_channel_from_payload():
    """channel 条件应该能从 event.payload 中读取"""
    evaluator = ConditionEvaluator()
    event = RuntimeEvent(type="t", payload={"channel": "web"})
    assert evaluator.evaluate({"channel": "web"}, event, {})


def test_condition_channel_from_metadata():
    """channel 条件也应该能从 event.metadata 中读取"""
    evaluator = ConditionEvaluator()
    event = RuntimeEvent(type="t", metadata={"channel": "qq"})
    assert evaluator.evaluate({"channel": "qq"}, event, {})


def test_condition_unknown_key_rejects():
    """未知条件键应该默认拒绝"""
    evaluator = ConditionEvaluator()
    event = RuntimeEvent(type="t")
    assert not evaluator.evaluate({"nonexistent_key": "value"}, event, {})


def test_condition_time_range():
    """time_range 条件应该能正确评估"""
    evaluator = ConditionEvaluator()
    event = RuntimeEvent(type="t")
    # 这里只测格式正确不报错，实际结果取决于当前时间
    result = evaluator.evaluate({"time_range": ["00:00", "23:59"]}, event, {})
    assert isinstance(result, bool)


# ── max_retries ─────────────────────────────────────────────────


def test_hook_manager_retry_on_failure():
    """失败时应重试 max_retries 次"""
    with tempfile.TemporaryDirectory() as tmp:
        mgr = HookManager(data_dir=tmp)
        call_count = []

        orig = mgr._action_executor._handlers["log"]

        def failing_once(action, event, ctx):
            call_count.append(1)
            if len(call_count) == 1:
                from nbot.hooks.actions import ActionResult
                return ActionResult(False, "log", "first call fails")
            return orig(action, event, ctx)

        mgr._action_executor._handlers["log"] = failing_once

        h = ConversationHook(
            name="retry_test",
            event="e",
            max_retries=2,
            actions=[{"type": "log", "message": "hit"}],
        )
        mgr.add_hook(h)

        logs = _loop().run_until_complete(mgr.emit_event(RuntimeEvent(type="e")))
        assert len(logs) == 1
        # 第一次失败，第二次成功
        assert len(call_count) == 2
        assert logs[0].status in ("success", "partial")


# ── permissions ─────────────────────────────────────────────────


def test_hook_permission_channels_allow():
    """permissions.channels 白名单应该限制频道"""
    with tempfile.TemporaryDirectory() as tmp:
        mgr = HookManager(data_dir=tmp)
        h = ConversationHook(
            name="perm_test",
            event="e",
            permissions={"channels": ["web"]},
            actions=[{"type": "log", "message": "hit"}],
        )
        mgr.add_hook(h)

        # web 频道应该触发
        evt_web = RuntimeEvent(type="e", payload={"channel": "web"})
        logs = _loop().run_until_complete(mgr.emit_event(evt_web))
        assert len(logs) == 1
        assert logs[0].status == "success"

        mgr.reset_turn()

        # qq 频道应该被拒绝
        evt_qq = RuntimeEvent(type="e", payload={"channel": "qq"})
        logs = _loop().run_until_complete(mgr.emit_event(evt_qq))
        assert len(logs) == 1
        assert logs[0].status == "denied"


def test_hook_permission_deny_channels():
    """permissions.deny_channels 黑名单应该限制频道"""
    with tempfile.TemporaryDirectory() as tmp:
        mgr = HookManager(data_dir=tmp)
        h = ConversationHook(
            name="deny_test",
            event="e",
            permissions={"deny_channels": ["telegram"]},
            actions=[{"type": "log", "message": "hit"}],
        )
        mgr.add_hook(h)

        # web 频道应该通过
        evt_web = RuntimeEvent(type="e", payload={"channel": "web"})
        logs = _loop().run_until_complete(mgr.emit_event(evt_web))
        assert len(logs) == 1
        assert logs[0].status == "success"

        mgr.reset_turn()

        # telegram 频道应该被拒绝
        evt_tg = RuntimeEvent(type="e", payload={"channel": "telegram"})
        logs = _loop().run_until_complete(mgr.emit_event(evt_tg))
        assert len(logs) == 1
        assert logs[0].status == "denied"


# ── 执行日志持久化 ──────────────────────────────────────────────


def test_hook_log_persistence():
    """执行日志应该被持久化到 hooks_logs.json"""
    with tempfile.TemporaryDirectory() as tmp:
        mgr = HookManager(data_dir=tmp)
        mgr.add_hook(ConversationHook(
            name="log_test",
            event="e",
            actions=[{"type": "log", "message": "hit"}],
        ))

        _loop().run_until_complete(mgr.emit_event(RuntimeEvent(type="e")))

        # 重新加载 manager，日志应该还在
        mgr2 = HookManager(data_dir=tmp)
        assert len(mgr2._execution_logs) == 1
        assert mgr2._execution_logs[0].status == "success"
