"""Multimedia bridge for plot events."""

from __future__ import annotations

import logging
import time
from typing import Any

_log = logging.getLogger(__name__)

_LEVEL_STICKER_INTENSITY = {
    "normal": 0.3,
    "important": 0.6,
    "turning_point": 0.9,
    "ending": 1.0,
}
_TTS_TRIGGER_LEVELS = {"turning_point", "ending"}


class MultimediaBridge:
    _instance: "MultimediaBridge | None" = None

    @classmethod
    def instance(cls) -> "MultimediaBridge":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def on_plot_choice(self, choice: Any, ctx: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        ctx = ctx or {}
        level = getattr(choice, "level", "normal")
        text = getattr(choice, "text", "")
        actions: list[dict[str, Any]] = []
        intensity = _LEVEL_STICKER_INTENSITY.get(level, 0.3)
        mood = ctx.get("mood", "calm")
        actions.append({"type": "sticker", "mood": mood, "intensity": intensity})
        if level in _TTS_TRIGGER_LEVELS:
            reply_text = ctx.get("reply_text", text)
            if reply_text:
                actions.append({"type": "tts", "text": reply_text})
        if level == "turning_point":
            desc = self._build_scene_desc(choice, ctx)
            if desc:
                actions.append({"type": "scene_description", "description": desc})
        if level == "ending":
            recap = self._build_recap(ctx)
            if recap:
                actions.append({"type": "recap", "recap": recap})
        return actions

    def _build_scene_desc(self, choice: Any, ctx: dict[str, Any]) -> str:
        text = getattr(choice, "text", "")
        mood = ctx.get("mood", "")
        location = ctx.get("location", "")
        parts = []
        if location:
            parts.append("Scene: " + location)
        if mood:
            parts.append("Mood: " + mood)
        parts.append("Event: " + text)
        return " | ".join(parts)

    def _build_recap(self, ctx: dict[str, Any]) -> str:
        nodes = ctx.get("plot_nodes", [])
        if not nodes:
            return ""
        lines = ["# Story Recap"]
        for i, node in enumerate(nodes, 1):
            title = node.get("title", "Node " + str(i))
            level = node.get("level", "normal")
            marker = "* " if level == "turning_point" else "- "
            lines.append(marker + title)
        return chr(10).join(lines)

    def build_status_card(self, cid: str, ctx: dict[str, Any]) -> dict[str, Any]:
        return {
            "character_id": cid,
            "name": ctx.get("name", cid),
            "mood": ctx.get("mood", "calm"),
            "energy": ctx.get("energy", 100),
            "scene": ctx.get("scene", {}),
            "relationship": ctx.get("relationship", {}),
            "updated_at": time.time(),
        }

    def build_group_layout(self, gid: str, ctx: dict[str, Any]) -> dict[str, Any]:
        characters = ctx.get("characters", [])
        relations = ctx.get("relations", [])
        speaker = ctx.get("active_speaker", "")
        narrator = ctx.get("narrator", "")
        nodes = []
        for ch in characters:
            cid = ch.get("id", "")
            nodes.append({
                "id": cid,
                "name": ch.get("name", cid),
                "mood": ch.get("mood", "calm"),
                "is_speaking": cid == speaker,
                "is_narrator": cid == narrator,
            })
        edges = []
        for r in relations:
            edges.append({
                "from": r.get("char_a", ""),
                "to": r.get("char_b", ""),
                "affection": r.get("affection", 0),
            })
        return {"group_id": gid, "nodes": nodes, "edges": edges}
