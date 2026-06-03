"""
Model failover queue manager.

Tracks per-model health state and provides automatic failover
when models encounter recoverable HTTP errors (429, 500, 502, 503).
Uses exponential backoff cooldown to avoid hammering failing providers.

This module is in nbot/core/ and must NOT import from nbot/web/ or
nbot/channels/. Model configs are received as plain dicts from callers.
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)


# ============================================================================
# Error classification
# ============================================================================


def classify_http_error(status_code: int) -> str:
    """Classify an HTTP status code for failover decisions.

    Returns:
        "failover"  -- try next model (40x, 429, 5xx)
        "config"    -- do not failover (reserved for future use)
        "transient" -- try next model after short cooldown
    """
    if 400 <= status_code < 500:
        return "failover"
    if 500 <= status_code < 600:
        return "failover"
    # Connection errors (-1), timeouts (-2), unknown (0)
    if status_code < 0:
        return "transient"
    return "transient"


def _extract_status_code(error: Exception) -> int:
    """Extract HTTP status code from an exception, or sentinel value.

    Returns:
        >0: HTTP status code
        -1: connection error
        -2: timeout
         0: unknown
    """
    import requests

    resp = getattr(error, "response", None)
    if resp is not None:
        return getattr(resp, "status_code", 0)
    if isinstance(error, requests.ConnectionError):
        return -1
    if isinstance(error, requests.Timeout):
        return -2
    return 0


# ============================================================================
# Cooldown parameters per error category
# ============================================================================

_COOLDOWN_PARAMS = {
    "rate_limit": (60.0, 300.0),   # (base, max) seconds
    "server":     (30.0, 120.0),
    "bad_request": (30.0, 120.0),  # 400: context-length, format issues
    "transient":  (15.0, 60.0),
    "config":     (0.0, 0.0),       # no cooldown for config errors
}


def _cooldown_category(status_code: int) -> str:
    """Map status code to cooldown category."""
    if status_code == 429:
        return "rate_limit"
    if 400 <= status_code < 500:
        return "bad_request"
    if 500 <= status_code < 600:
        return "server"
    return "transient"


def _compute_cooldown(consecutive_failures: int, status_code: int) -> float:
    """Compute cooldown seconds with exponential backoff."""
    category = _cooldown_category(status_code)
    base, max_val = _COOLDOWN_PARAMS[category]
    if base <= 0:
        return 0.0
    cooldown = base * (2 ** max(consecutive_failures - 1, 0))
    return min(cooldown, max_val)


# ============================================================================
# Health tracking
# ============================================================================


@dataclass
class ModelHealth:
    """Tracks health status of a single model."""

    model_id: str
    consecutive_failures: int = 0      # 内部用：连续失败（用于 cooldown 计算）
    last_failure_at: float = 0.0
    last_failure_code: int = 0
    cooldown_until: float = 0.0
    daily_failures: int = 0            # 当日累计失败次数
    daily_failures_date: str = ""      # 记录日期 (YYYY-MM-DD)


class FailoverState:
    """Thread-safe, per-purpose failover queue manager.

    Health state is persisted to disk (failover_health.json) and
    restored on process restart. Daily failure counts auto-reset
    when the date changes.
    """

    def __init__(self, data_dir: Optional[str] = None):
        self._lock = threading.Lock()
        self._health: Dict[str, ModelHealth] = {}
        self._data_dir = data_dir
        self._save_path: Optional[str] = None
        if data_dir:
            self._save_path = os.path.join(data_dir, "failover_health.json")
            self._load()

    def select_model(
        self,
        model_configs: List[Dict[str, Any]],
        exclude_ids: Optional[set] = None,
    ) -> Optional[Dict[str, Any]]:
        """Pick the best available model from the ordered list.

        Skips models in cooldown or over token limit.
        Returns the first available model, or the first model as a last resort.
        """
        now = time.monotonic()
        exclude = exclude_ids or set()
        fallback = None

        with self._lock:
            for config in model_configs:
                model_id = config.get("model_id", "")
                if model_id in exclude:
                    continue
                if fallback is None:
                    fallback = config
                # Token limit check
                if self._is_token_limited(config):
                    continue
                health = self._health.get(model_id)
                if health is None or now >= health.cooldown_until:
                    return config

        # All unavailable -- return first as last resort
        return fallback

    def _is_token_limited(self, config: Dict[str, Any]) -> bool:
        """Check if model has exceeded its token limit."""
        daily_limit = config.get("token_limit_daily", 0) or 0
        weekly_limit = config.get("token_limit_weekly", 0) or 0
        if not daily_limit and not weekly_limit:
            return False
        model_name = config.get("model", "")
        if not model_name:
            return False
        try:
            from nbot.core.token_stats import get_token_stats_manager
            usage = get_token_stats_manager().get_model_usage(model_name)
        except Exception:
            return False
        if daily_limit and usage.get("today_total", 0) >= daily_limit:
            return True
        if weekly_limit and usage.get("weekly_total", 0) >= weekly_limit:
            return True
        return False

    def record_success(self, model_id: str) -> None:
        """Reset consecutive failure counter on success (daily_failures preserved)."""
        with self._lock:
            health = self._health.get(model_id)
            if health:
                health.consecutive_failures = 0
                health.cooldown_until = 0.0
        self._save()

    def record_failure(
        self,
        model_id: str,
        status_code: int = 0,
    ) -> float:
        """Record a failure and compute cooldown duration.

        Returns the cooldown seconds for logging.
        """
        now = time.monotonic()
        today_str = date.today().isoformat()

        with self._lock:
            health = self._health.get(model_id)
            if health is None:
                health = ModelHealth(model_id=model_id)
                self._health[model_id] = health

            health.consecutive_failures += 1
            health.last_failure_at = now
            health.last_failure_code = status_code

            # 累计当日失败（跨天自动重置）
            if health.daily_failures_date != today_str:
                health.daily_failures = 0
                health.daily_failures_date = today_str
            health.daily_failures += 1

            cooldown = _compute_cooldown(
                health.consecutive_failures, status_code
            )
            health.cooldown_until = now + cooldown if cooldown > 0 else 0.0

        self._save()

        _log.warning(
            "[Failover] model=%s status=%d consecutive=%d daily=%d cooldown=%.0fs",
            model_id,
            status_code,
            health.consecutive_failures,
            health.daily_failures,
            cooldown,
        )
        return cooldown

    def is_available(self, model_id: str) -> bool:
        """Check if model's cooldown has expired."""
        now = time.monotonic()
        with self._lock:
            health = self._health.get(model_id)
            if health is None:
                return True
            return now >= health.cooldown_until

    def get_all_health_summary(self) -> Dict[str, Any]:
        """Return a snapshot of all model health states."""
        now = time.monotonic()
        today_str = date.today().isoformat()
        summary = {}
        with self._lock:
            for model_id, health in self._health.items():
                # 跨天自动重置当日失败数
                daily = health.daily_failures
                if health.daily_failures_date != today_str:
                    daily = 0
                remaining = max(0.0, health.cooldown_until - now)
                summary[model_id] = {
                    "daily_failures": daily,
                    "last_failure_code": health.last_failure_code,
                    "cooldown_remaining": round(remaining, 1),
                    "available": now >= health.cooldown_until,
                }
        return summary

    def reset(self, model_id: Optional[str] = None) -> None:
        """Reset health state for one or all models."""
        with self._lock:
            if model_id:
                self._health.pop(model_id, None)
            else:
                self._health.clear()
        self._save()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        """Persist health state to disk (best-effort)."""
        if not self._save_path:
            return
        try:
            now_wall = time.time()
            now_mono = time.monotonic()
            data = {}
            with self._lock:
                for mid, h in self._health.items():
                    # 将 monotonic 时间转为 wall-clock 时间以便持久化
                    wall_last = now_wall - (now_mono - h.last_failure_at) if h.last_failure_at else 0.0
                    wall_cooldown = now_wall - (now_mono - h.cooldown_until) if h.cooldown_until > now_mono else 0.0
                    data[mid] = {
                        "daily_failures": h.daily_failures,
                        "daily_failures_date": h.daily_failures_date,
                        "consecutive_failures": h.consecutive_failures,
                        "last_failure_code": h.last_failure_code,
                        "last_failure_at": wall_last,
                        "cooldown_until": wall_cooldown,
                    }
            tmp = self._save_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._save_path)
        except Exception as e:
            _log.warning("[Failover] Failed to save health state: %s", e)

    def _load(self) -> None:
        """Load health state from disk."""
        if not self._save_path or not os.path.exists(self._save_path):
            return
        try:
            with open(self._save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            now_wall = time.time()
            now_mono = time.monotonic()
            with self._lock:
                for mid, d in data.items():
                    h = ModelHealth(model_id=mid)
                    h.daily_failures = d.get("daily_failures", 0)
                    h.daily_failures_date = d.get("daily_failures_date", "")
                    h.consecutive_failures = d.get("consecutive_failures", 0)
                    h.last_failure_code = d.get("last_failure_code", 0)
                    # wall-clock 转回 monotonic
                    wall_last = d.get("last_failure_at", 0.0)
                    wall_cooldown = d.get("cooldown_until", 0.0)
                    if wall_last:
                        h.last_failure_at = now_mono - (now_wall - wall_last)
                    if wall_cooldown and wall_cooldown > now_wall:
                        h.cooldown_until = now_mono + (wall_cooldown - now_wall)
                    else:
                        h.cooldown_until = 0.0
                    self._health[mid] = h
            _log.info("[Failover] Loaded health state for %d models", len(data))
        except Exception as e:
            _log.warning("[Failover] Failed to load health state: %s", e)


# ============================================================================
# Singleton
# ============================================================================

_failover_state = FailoverState()


def get_failover_state() -> FailoverState:
    """Get the module-level FailoverState singleton."""
    return _failover_state


def init_failover_state(data_dir: str) -> FailoverState:
    """Initialize (or reinitialize) the singleton with persistence support."""
    global _failover_state
    _failover_state = FailoverState(data_dir=data_dir)
    return _failover_state
