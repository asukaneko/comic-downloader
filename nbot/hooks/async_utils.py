"""Async helpers for hook emission from mixed sync/threaded contexts."""

import asyncio


def run_hook_coro(coro) -> None:
    """Run or schedule a hook coroutine from sync pipeline code."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return

    loop.create_task(coro)
