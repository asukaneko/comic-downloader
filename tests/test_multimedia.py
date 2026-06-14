"""Multimedia bridge tests."""

from __future__ import annotations

import os, sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nbot.plot.multimedia_bridge import MultimediaBridge
from nbot.plot.models import PlotChoice


class TestMultimediaBridge:
    def test_singleton(self):
        assert MultimediaBridge.instance() is MultimediaBridge.instance()

    def test_normal_choice_no_tts(self):
        c = PlotChoice(node_id="n1", text="wait", level="normal")
        actions = MultimediaBridge.instance().on_plot_choice(c)
        types = [a["type"] for a in actions]
        assert "sticker" in types
        assert "tts" not in types

    def test_turning_point_has_all(self):
        c = PlotChoice(node_id="n1", text="reveal", level="turning_point")
        ctx = {"mood": "tense", "reply_text": "truth", "location": "lib"}
        actions = MultimediaBridge.instance().on_plot_choice(c, ctx)
        types = [a["type"] for a in actions]
        assert "sticker" in types
        assert "tts" in types
        assert "scene_description" in types

    def test_ending_has_recap(self):
        c = PlotChoice(node_id="n1", text="bye", level="ending")
        ctx = {"reply_text": "farewell", "plot_nodes": [{"title": "Start", "level": "normal"}]}
        actions = MultimediaBridge.instance().on_plot_choice(c, ctx)
        types = [a["type"] for a in actions]
        assert "recap" in types

    def test_sticker_intensity(self):
        c = PlotChoice(node_id="n1", text="t", level="important")
        actions = MultimediaBridge.instance().on_plot_choice(c)
        sticker = [a for a in actions if a["type"] == "sticker"][0]
        assert sticker["intensity"] == 0.6


class TestStatusCard:
    def test_build(self):
        ctx = {"name": "Alice", "mood": "happy", "energy": 80}
        card = MultimediaBridge.instance().build_status_card("alice", ctx)
        assert card["character_id"] == "alice"
        assert card["mood"] == "happy"
        assert card["energy"] == 80
        assert "updated_at" in card


class TestGroupLayout:
    def test_build(self):
        ctx = {
            "characters": [{"id": "a", "name": "Alice", "mood": "calm"}],
            "relations": [{"char_a": "a", "char_b": "b", "affection": 50}],
            "active_speaker": "a", "narrator": "n",
        }
        layout = MultimediaBridge.instance().build_group_layout("g1", ctx)
        assert layout["group_id"] == "g1"
        assert len(layout["nodes"]) == 1
        assert layout["nodes"][0]["is_speaking"] is True
        assert len(layout["edges"]) == 1


class TestLevelRank:
    def test_rank(self):
        from nbot.core.ai_pipeline import _level_rank
        assert _level_rank("normal") < _level_rank("important")
        assert _level_rank("important") < _level_rank("turning_point")
        assert _level_rank("turning_point") < _level_rank("ending")
