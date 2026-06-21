"""
Review Pipeline

每轮对话后的结构化审查层。
当前实现：规则版（不调用大模型）。
后续可替换为 LLM Review。
"""

from __future__ import annotations

import logging

from nbot.review.models import ReviewInput, ReviewOutput
from nbot.review.rule_review import run_rule_review

_log = logging.getLogger(__name__)


class ReviewPipeline:
    """Review Pipeline 编排器

    使用方式：
        pipeline = ReviewPipeline()
        output = pipeline.run(ReviewInput(...))
    """

    def __init__(self, *, mode: str = "rule", event_bus=None):
        """
        mode: "rule" | "llm"（LLM 版本尚未实现）
        event_bus: 可选，发射 review.started / review.finished 事件
        """
        self._mode = mode
        self._event_bus = event_bus

    def set_event_bus(self, bus) -> None:
        self._event_bus = bus

    def run(self, inp: ReviewInput) -> ReviewOutput:
        """执行 Review，返回结构化输出。"""
        self._emit_event("review.started", inp)

        try:
            if self._mode == "rule":
                output = run_rule_review(inp)
            else:
                _log.warning("[ReviewPipeline] mode=%s not implemented, falling back to rule", self._mode)
                output = run_rule_review(inp)
        except Exception as exc:
            _log.error("[ReviewPipeline] review failed: %s", exc, exc_info=True)
            output = ReviewOutput(skipped=True, source="rule")

        self._emit_event("review.finished", inp, output)

        if not output.skipped:
            _log.debug(
                "[ReviewPipeline] review done conv=%s choice=%s "
                "should_write=%s rel_delta=%s scores=%s",
                inp.conversation_id,
                (inp.selected_choice or {}).get("level", ""),
                output.should_write_memory,
                output.relationship_delta,
                output.scores,
            )

        return output

    def _emit_event(self, event_type: str, inp: ReviewInput, output: ReviewOutput | None = None) -> None:
        if not self._event_bus:
            return
        try:
            from nbot.hooks.models import RuntimeEvent
            payload = {
                "conversation_id": inp.conversation_id,
                "character_id": inp.character_id,
            }
            if inp.real_time_context:
                payload["real_time"] = inp.real_time_context
            if output:
                payload["skipped"] = output.skipped
                payload["should_write_memory"] = output.should_write_memory
                # 完整 review 输出，供 UI 展示详情
                payload["review_output"] = output.to_dict()
            evt = RuntimeEvent(
                type=event_type,
                source="review_pipeline",
                conversation_id=inp.conversation_id,
                character_id=inp.character_id,
                user_id=inp.user_id,
                group_id=inp.group_id,
                payload=payload,
            )
            from nbot.hooks.async_utils import run_hook_coro
            run_hook_coro(self._event_bus.emit(evt))
        except Exception as exc:
            _log.debug("[ReviewPipeline] emit failed: %s", exc)


# 全局单例（懒初始化）
_review_pipeline: ReviewPipeline | None = None


def get_review_pipeline(event_bus=None) -> ReviewPipeline:
    global _review_pipeline
    if _review_pipeline is None:
        _review_pipeline = ReviewPipeline(event_bus=event_bus)
    elif event_bus and _review_pipeline._event_bus is not event_bus:
        _review_pipeline.set_event_bus(event_bus)
    return _review_pipeline
