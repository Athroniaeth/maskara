"""Shared helpers for Haystack components."""

import asyncio
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")


def run_coroutine_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Execute ``coro`` from synchronous code.

    If no event loop is running, uses ``asyncio.run`` to drive the
    coroutine to completion. If a loop is already running (e.g. the
    caller is inside a Jupyter cell with autoreload, a FastAPI handler,
    or a Haystack ``AsyncPipeline``), raises a clear ``RuntimeError``
    telling the caller to switch to the async API.

    Args:
        coro: The awaitable to drive.

    Returns:
        The coroutine's result.

    Raises:
        RuntimeError: If called from inside a running event loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        "PIIGhost Haystack component's sync run() was called from inside a "
        "running event loop. Use Haystack's AsyncPipeline + run_async() instead."
    )
