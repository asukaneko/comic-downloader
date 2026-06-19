"""
WorldEngine — 群聊环境判定器

MVP 版本：基于规则的语境判断，无需调用大模型。
后续可替换为 LLM 版本。

输入：消息、近期消息、角色列表、关系矩阵、当前场景、激活剧情节点
输出：speaker_id、是否需要旁白前/后、旁白原因
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)

# 全局单例
_world_engine: Optional[WorldEngine] = None


@dataclass
class WorldEngineDecision:
    """WorldEngine 的判断结果"""
    speaker_id: str = ""
    reason: str = ""
    should_narrate_before: bool = False
    should_narrate_after: bool = False
    narrate_trigger: str = ""        # 触发旁白的原因描述
    confidence: float = 1.0          # 判断置信度（0-1）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "speaker_id": self.speaker_id,
            "reason": self.reason,
            "should_narrate_before": self.should_narrate_before,
            "should_narrate_after": self.should_narrate_after,
            "narrate_trigger": self.narrate_trigger,
            "confidence": self.confidence,
        }


class WorldEngine:
    """群聊世界引擎（规则版判定器）

    提供 world_engine 发言策略，综合考虑：
    1. 被 @ 提及的角色
    2. 与当前消息关联度最高的角色
    3. 剧情冲突相关角色
    4. 关系权重加成
    """

    def decide(
        self,
        message: str,
        character_ids: List[str],
        *,
        recent_messages: Optional[List[Dict[str, Any]]] = None,
        characters: Optional[Dict[str, Any]] = None,
        relations: Optional[List[Dict[str, Any]]] = None,
        scene: Optional[Dict[str, Any]] = None,
        active_plot_node: Optional[Dict[str, Any]] = None,
        last_speaker: str = "",
    ) -> WorldEngineDecision:
        """综合语境判断下一个发言角色。"""
        if not character_ids:
            return WorldEngineDecision(reason="无可用角色")

        decision = WorldEngineDecision()

        # 1. 优先：被明确 @ 的角色
        mentioned = self._find_mentioned(message, character_ids, characters or {})
        if mentioned:
            decision.speaker_id = mentioned
            decision.reason = f"角色被用户直接提及（@{mentioned}）"
            decision.confidence = 0.95
            decision.should_narrate_after = self._should_narrate_after_mention(
                message, active_plot_node
            )
            return decision

        # 2. 剧情冲突相关角色
        if active_plot_node:
            plot_speaker = self._find_plot_relevant(
                message, character_ids, active_plot_node, characters or {}
            )
            if plot_speaker:
                decision.speaker_id = plot_speaker
                decision.reason = "该角色与当前激活剧情节点直接相关"
                decision.confidence = 0.85
                decision.should_narrate_after = active_plot_node.get("level") in ("turning_point", "ending")
                return decision

        # 3. 关系权重最高的角色（排除上一个发言者，避免连续独白）
        if relations:
            rel_speaker = self._find_by_relation_weight(
                character_ids, relations, last_speaker=last_speaker
            )
            if rel_speaker:
                decision.speaker_id = rel_speaker
                decision.reason = "该角色与用户的关系权重最高"
                decision.confidence = 0.7
                return decision

        # 4. 关键词匹配（角色名出现在消息中）
        kw_speaker = self._find_by_keyword(message, character_ids, characters or {})
        if kw_speaker:
            decision.speaker_id = kw_speaker
            decision.reason = "消息内容关键词匹配到该角色"
            decision.confidence = 0.75
            return decision

        # 5. fallback：轮换（排除上一个发言者）
        candidates = [c for c in character_ids if c != last_speaker] or character_ids
        decision.speaker_id = candidates[0]
        decision.reason = "无明确匹配，按顺序轮换"
        decision.confidence = 0.5
        return decision

    def should_narrate(
        self,
        message: str,
        recent_messages: Optional[List[Dict[str, Any]]] = None,
        active_plot_node: Optional[Dict[str, Any]] = None,
        turn_count: int = 0,
        narrate_interval: int = 5,
    ) -> bool:
        """判断当前是否需要旁白。"""
        # 剧情转折点后必须有旁白
        if active_plot_node and active_plot_node.get("level") in ("turning_point", "ending"):
            return True
        # 周期触发
        if narrate_interval > 0 and turn_count > 0 and turn_count % narrate_interval == 0:
            return True
        # 场景切换关键词
        if re.search(r"换个地方|去.*吧|离开|到达|来到|我们走", message):
            return True
        return False

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _find_mentioned(
        self,
        message: str,
        character_ids: List[str],
        characters: Dict[str, Any],
    ) -> str:
        """查找被 @ 或被名字直接提及的角色。"""
        for cid in character_ids:
            name = characters.get(cid, {}).get("name", cid) if isinstance(
                characters.get(cid), dict
            ) else cid
            if f"@{name}" in message or f"@{cid}" in message:
                return cid
        return ""

    def _find_plot_relevant(
        self,
        message: str,
        character_ids: List[str],
        plot_node: Dict[str, Any],
        characters: Dict[str, Any],
    ) -> str:
        """找到与当前剧情节点最相关的角色。"""
        participants = plot_node.get("participants", [])
        for cid in participants:
            if cid in character_ids:
                return cid
        # 剧情摘要中出现角色名
        summary = (plot_node.get("summary") or "") + (plot_node.get("title") or "")
        for cid in character_ids:
            name = characters.get(cid, {}).get("name", cid) if isinstance(
                characters.get(cid), dict
            ) else cid
            if name in summary:
                return cid
        return ""

    def _find_by_relation_weight(
        self,
        character_ids: List[str],
        relations: List[Dict[str, Any]],
        *,
        last_speaker: str = "",
    ) -> str:
        """通过关系权重选择发言角色（排除上一发言者）。"""
        scores: Dict[str, float] = {cid: 0.0 for cid in character_ids}
        for rel in relations:
            cid = rel.get("character_id", "")
            if cid in scores:
                weight = (
                    rel.get("affection", 0) +
                    rel.get("trust", 0) * 0.8 +
                    rel.get("familiarity", 0) * 0.5
                )
                scores[cid] = weight

        candidates = [c for c in character_ids if c != last_speaker] or character_ids
        if not candidates:
            return ""
        return max(candidates, key=lambda c: scores.get(c, 0))

    def _find_by_keyword(
        self,
        message: str,
        character_ids: List[str],
        characters: Dict[str, Any],
    ) -> str:
        """通过名字关键词匹配角色。"""
        for cid in character_ids:
            name = characters.get(cid, {}).get("name", cid) if isinstance(
                characters.get(cid), dict
            ) else cid
            if name and name in message:
                return cid
        return ""

    def _should_narrate_after_mention(
        self, message: str, active_plot_node: Optional[Dict[str, Any]]
    ) -> bool:
        if not active_plot_node:
            return False
        return active_plot_node.get("level") in ("turning_point", "ending")


def get_world_engine() -> WorldEngine:
    global _world_engine
    if _world_engine is None:
        _world_engine = WorldEngine()
    return _world_engine
