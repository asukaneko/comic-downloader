"""Plot enhanced tests for 3.3."""

from __future__ import annotations

import os, sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nbot.plot.models import PlotChoice
from nbot.plot.memory_bridge import PlotMemoryBridge
from nbot.plot.world_book_bridge import PlotWorldBookBridge
from nbot.group.scheduler import SpeakerScheduler
from nbot.group.models import GroupConversation, InterCharacterRelation


class TestPlotMemoryBridge:
    def test_singleton(self):
        assert PlotMemoryBridge.instance() is PlotMemoryBridge.instance()

    def test_normal_skips(self):
        c = PlotChoice(node_id="n1", text="wait", level="normal")
        svc = type("M", (), {"save": lambda s, **kw: True})()
        assert PlotMemoryBridge.instance().on_choice_selected(c, "c1", "ch1", "u1", svc) is False

    def test_important_writes(self):
        saved = {}
        class M:
            def save(self, **kw): saved.update(kw); return True
        c = PlotChoice(node_id="n1", text="confess", level="important", intent="bond")
        assert PlotMemoryBridge.instance().on_choice_selected(c, "c1", "ch1", "u1", M()) is True
        assert saved.get("mem_type") == "relationship"

    def test_turning_point_writes(self):
        saved = {}
        class M:
            def save(self, **kw): saved.update(kw); return True
        c = PlotChoice(node_id="n1", text="reveal", level="turning_point")
        assert PlotMemoryBridge.instance().on_choice_selected(c, "c1", "ch1", "u1", M()) is True
        assert saved.get("mem_type") == "event"

    def test_ending_writes(self):
        saved = {}
        class M:
            def save(self, **kw): saved.update(kw); return True
        c = PlotChoice(node_id="n1", text="bye", level="ending")
        assert PlotMemoryBridge.instance().on_choice_selected(c, "c1", "ch1", "u1", M()) is True
        assert saved.get("mem_type") == "long"

    def test_no_service(self):
        c = PlotChoice(node_id="n1", text="t", level="important")
        assert PlotMemoryBridge.instance().on_choice_selected(c, "c1", "ch1") is False


class TestPlotWorldBookBridge:
    def test_singleton(self):
        assert PlotWorldBookBridge.instance() is PlotWorldBookBridge.instance()

    def test_non_turning_skips(self):
        c = PlotChoice(node_id="n1", text="t", level="normal")
        assert PlotWorldBookBridge.instance().on_turning_point(c, "c1", "ch1", "b1") is False

    def test_no_book_skips(self):
        c = PlotChoice(node_id="n1", text="t", level="turning_point")
        assert PlotWorldBookBridge.instance().on_turning_point(c, "c1", "ch1", "") is False

    def test_turning_point_writes(self):
        added = {}
        class S:
            def add_entry(self, bid, data): added.update(data); added["bid"] = bid; return type("E", (), {"name": "ok"})()
        c = PlotChoice(node_id="n1", text="reveal truth", level="turning_point", intent="change")
        r = PlotWorldBookBridge.instance().on_turning_point(c, "c1", "ch1", "b1", S())
        assert r is True
        assert added.get("entry_type") == "event"
        assert added.get("bid") == "b1"

    def test_extract_keywords(self):
        kws = PlotWorldBookBridge._extract_keywords("reveal the truth about everything", "change the path forward")
        assert isinstance(kws, list)


class TestSchedulerEnhancements:
    def test_narrator_driven(self):
        s = SpeakerScheduler()
        c = GroupConversation(name="t", character_ids=["narrator", "alice"], narrator_id="narrator")
        c.config.speaker_strategy = "narrator_driven"
        assert s.decide_next_speaker(c, "", ["narrator", "alice"]) == "narrator"

    def test_narrator_driven_not_in_list(self):
        s = SpeakerScheduler()
        c = GroupConversation(name="t", character_ids=["alice", "bob"], narrator_id="narrator")
        c.config.speaker_strategy = "narrator_driven"
        r = s.decide_next_speaker(c, "", ["alice", "bob"])
        assert r in ["alice", "bob"]

    def test_relevance_with_relations(self):
        s = SpeakerScheduler()
        c = GroupConversation(name="t", character_ids=["alice", "bob"])
        c.config.speaker_strategy = "relevance"
        rel = InterCharacterRelation(char_a="alice", char_b="bob", affection=90)
        c.set_relation(rel)
        r = s.decide_next_speaker(c, "hello", ["alice", "bob"])
        assert r in ["alice", "bob"]


class TestWorldBookAction:
    def test_registered(self):
        from nbot.hooks.actions import ActionExecutor
        ex = ActionExecutor()
        assert "world_book_add" in ex._handlers
