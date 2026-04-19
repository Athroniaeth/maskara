"""Tests for the sync/async bridge used by Haystack components."""

import asyncio

import pytest

from piighost.integrations.haystack._base import run_coroutine_sync


class TestRunCoroutineSync:
    """``run_coroutine_sync`` runs an awaitable from sync code, or fails loudly."""

    def test_runs_coroutine_outside_loop(self) -> None:
        async def coro() -> int:
            return 42

        assert run_coroutine_sync(coro()) == 42

    def test_raises_inside_running_loop(self) -> None:
        async def coro() -> int:
            return 42

        async def outer() -> None:
            with pytest.raises(RuntimeError, match="AsyncPipeline"):
                run_coroutine_sync(coro())

        asyncio.run(outer())

    def test_propagates_coroutine_exception(self) -> None:
        async def coro() -> None:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            run_coroutine_sync(coro())
