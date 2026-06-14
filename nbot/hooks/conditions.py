"""
Hook 条件引擎

评估 Hook 的触发条件，决定是否执行 Hook 动作。
"""

import logging
from datetime import datetime
from typing import Any, Dict

from nbot.hooks.models import RuntimeEvent

_log = logging.getLogger(__name__)


class ConditionEvaluator:
    """条件求值器

    支持的条件键：
    - character_id: str — 精确匹配角色 ID
    - user_id: str — 精确匹配用户 ID
    - channel: str — 匹配频道（qq / web / telegram 等）
    - mood_is: str — 心情匹配
    - mood_is_not: str — 心情不匹配
    - affection_gte / affection_lte: int — 好感度阈值
    - trust_gte / trust_lte: int — 信任度阈值
    - familiarity_gte / familiarity_lte: int — 熟悉度阈值
    - dependency_gte / dependency_lte: int — 依赖度阈值
    - security_gte / security_lte: int — 安全感阈值
    - jealousy_gte / jealousy_lte: int — 嫉妒度阈值
    - energy_gte / energy_lte: int — 精力阈值
    - time_range: [str, str] — 时间范围（HH:MM 格式）
    - event_source: str — 事件来源模块匹配
    """

    def evaluate(
        self,
        conditions: Dict[str, Any],
        event: RuntimeEvent,
        context: Dict[str, Any],
    ) -> bool:
        """评估所有条件，全部满足返回 True

        Args:
            conditions: 条件字典
            event: 当前事件
            context: 额外上下文（如角色状态、关系数据）
        """
        if not conditions:
            return True

        for key, expected in conditions.items():
            if not self._evaluate_one(key, expected, event, context):
                _log.debug(
                    "[HookCondition] 条件不满足 key=%s expected=%s", key, expected
                )
                return False
        return True

    def _evaluate_one(
        self,
        key: str,
        expected: Any,
        event: RuntimeEvent,
        ctx: Dict[str, Any],
    ) -> bool:
        # 精确匹配
        if key == "character_id":
            return event.character_id == expected
        if key == "user_id":
            return event.user_id == expected
        if key == "channel":
            return event.metadata.get("channel", "") == expected
        if key == "event_source":
            return event.source == expected

        # 心情匹配
        if key == "mood_is":
            return ctx.get("mood", "") == expected
        if key == "mood_is_not":
            return ctx.get("mood", "") != expected

        # 关系阈值
        if key.endswith("_gte") or key.endswith("_lte"):
            return self._evaluate_threshold(key, expected, ctx)

        # 时间范围
        if key == "time_range":
            return self._evaluate_time_range(expected)

        # 未知条件键默认通过
        _log.warning("[HookCondition] 未知条件键: %s", key)
        return True

    def _evaluate_threshold(self, key: str, expected: Any, ctx: Dict[str, Any]) -> bool:
        """评估阈值条件（如 affection_gte: 80）"""
        if key.endswith("_gte"):
            field = key[:-4]
            actual = ctx.get(field, 0)
            return _to_number(actual) >= _to_number(expected)
        if key.endswith("_lte"):
            field = key[:-4]
            actual = ctx.get(field, 0)
            return _to_number(actual) <= _to_number(expected)
        return True

    @staticmethod
    def _evaluate_time_range(time_range: Any) -> bool:
        """评估时间范围条件，如 ["21:00", "23:59"]"""
        if not isinstance(time_range, list) or len(time_range) != 2:
            return True
        try:
            now = datetime.now()
            current_minutes = now.hour * 60 + now.minute
            start_parts = time_range[0].split(":")
            end_parts = time_range[1].split(":")
            start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])
            end_minutes = int(end_parts[0]) * 60 + int(end_parts[1])
            if start_minutes <= end_minutes:
                return start_minutes <= current_minutes <= end_minutes
            # 跨午夜（如 23:00 - 02:00）
            return current_minutes >= start_minutes or current_minutes <= end_minutes
        except (ValueError, IndexError):
            _log.warning("[HookCondition] 时间范围格式错误: %s", time_range)
            return True


def _to_number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
