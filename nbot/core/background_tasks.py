"""Small shared executor for non-critical post-response work."""

from __future__ import annotations

import atexit
import logging
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Optional

_log = logging.getLogger(__name__)


def _worker_count() -> int:
    try:
        return max(1, int(os.getenv("NBOT_BACKGROUND_TASK_WORKERS", "4")))
    except (TypeError, ValueError):
        return 4


_EXECUTOR = ThreadPoolExecutor(
    max_workers=_worker_count(),
    thread_name_prefix="nbot-bg",
)
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
_IN_FLIGHT: set[str] = set()
_IN_FLIGHT_GUARD = threading.Lock()


def _get_lock(key: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


def submit_background_task(
    name: str,
    func: Callable[..., Any],
    *args: Any,
    serial_key: str = "",
    unique_key: str = "",
    **kwargs: Any,
) -> Optional[Future]:
    """Submit a best-effort background task.

    serial_key keeps related tasks ordered without blocking the caller.
    unique_key drops duplicate in-flight work, useful for session rename jobs.
    """
    task_name = name or getattr(func, "__name__", "background_task")

    if unique_key:
        with _IN_FLIGHT_GUARD:
            if unique_key in _IN_FLIGHT:
                _log.debug(
                    "[BackgroundTask] skipped duplicate task=%s key=%s",
                    task_name,
                    unique_key,
                )
                return None
            _IN_FLIGHT.add(unique_key)

    def runner() -> Any:
        try:
            if serial_key:
                with _get_lock(serial_key):
                    return func(*args, **kwargs)
            return func(*args, **kwargs)
        finally:
            if unique_key:
                with _IN_FLIGHT_GUARD:
                    _IN_FLIGHT.discard(unique_key)

    future = _EXECUTOR.submit(runner)

    def log_failure(done: Future) -> None:
        try:
            done.result()
        except Exception as exc:
            _log.warning("[BackgroundTask] %s failed: %s", task_name, exc, exc_info=True)

    future.add_done_callback(log_failure)
    return future


@atexit.register
def _shutdown_executor() -> None:
    _EXECUTOR.shutdown(wait=False, cancel_futures=False)
