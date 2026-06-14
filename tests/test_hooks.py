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
