"""TTL sweeper for Aegra threads using the LangGraph SDK."""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from langgraph_sdk import get_client

logger = logging.getLogger(__name__)


def load_ttl_config() -> dict | None:
    """Load TTL configuration from aegra.json or langgraph.json.

    Reads the ``checkpointer.ttl`` block from the first config file found.
    The config file path can be overridden via the ``AEGRA_CONFIG`` env var.

    Returns:
        A dict with TTL settings, or None if no valid config is found.

    Example config::

        {
          "checkpointer": {
            "ttl": {
              "strategy": "delete",
              "sweep_interval_minutes": 1,
              "default_ttl": 1
            }
          }
        }
    """
    config_path = os.environ.get("AEGRA_CONFIG", "")
    candidates = (
        [Path(config_path)]
        if config_path
        else [Path("aegra.json"), Path("langgraph.json")]
    )

    for path in candidates:
        if path.exists():
            try:
                data = json.loads(path.read_text())
                ttl = data.get("checkpointer", {}).get("ttl")
                if ttl:
                    logger.info("TTL config loaded from %s: %s", path, ttl)
                    return ttl
            except Exception:
                logger.exception("Failed to read config file: %s", path)

    return None


async def sweep_expired_threads(base_url: str, default_ttl_minutes: int) -> None:
    """Delete all threads older than default_ttl_minutes via the LangGraph SDK.

    Args:
        base_url: The Aegra server URL (e.g. ``http://localhost:8000``).
        default_ttl_minutes: Max thread age in minutes before deletion.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=default_ttl_minutes)
    client = get_client(url=base_url)
    deleted = 0
    offset = 0
    limit = 100

    while True:
        threads = await client.threads.search(limit=limit, offset=offset)
        if not threads:
            break

        for thread in threads:
            thread_id = thread.get("thread_id")
            raw_date = thread.get("created_at") or thread.get("updated_at")

            if not thread_id or not raw_date:
                continue

            try:
                created_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except ValueError:
                continue

            if created_at < cutoff:
                await client.threads.delete(thread_id)
                deleted += 1
                logger.info("Deleted thread %s (created %s)", thread_id, created_at)

        if len(threads) < limit:
            break
        offset += limit

    if deleted:
        logger.info("Sweep complete %d thread(s) deleted.", deleted)


async def run_sweeper(
    base_url: str,
    sweep_interval_minutes: int,
    default_ttl_minutes: int,
) -> None:
    """Run the TTL sweeper loop indefinitely as a background asyncio task.

    Waits 5 seconds on startup to let the server initialize, then sweeps
    expired threads every ``sweep_interval_minutes`` minutes.

    Args:
        base_url: The Aegra server URL.
        sweep_interval_minutes: How often to run a sweep.
        default_ttl_minutes: Max thread age in minutes before deletion.
    """
    logger.info(
        "TTL sweeper started ttl=%d min, interval=%d min, server=%s",
        default_ttl_minutes,
        sweep_interval_minutes,
        base_url,
    )
    await asyncio.sleep(5)  # Wait for the server to be ready

    while True:
        try:
            await sweep_expired_threads(base_url, default_ttl_minutes)
        except asyncio.CancelledError:
            logger.info("TTL sweeper stopped.")
            return
        except Exception:
            logger.exception("Unexpected error during sweep.")

        try:
            await asyncio.sleep(sweep_interval_minutes * 60)
        except asyncio.CancelledError:
            logger.info("TTL sweeper stopped.")
            return
