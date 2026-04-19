"""Auto-spawn, stale detection, and clean shutdown for the piighost daemon."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import portalocker
import psutil

from piighost.daemon.handshake import DaemonHandshake, read_handshake


def _is_alive(hs: DaemonHandshake) -> bool:
    if not psutil.pid_exists(hs.pid):
        return False
    try:
        resp = httpx.get(
            f"http://127.0.0.1:{hs.port}/health",
            headers={"Authorization": f"Bearer {hs.token}"},
            timeout=1.5,
        )
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def _is_alive_with_retry(hs: DaemonHandshake, *, retries: int = 3, delay: float = 0.4) -> bool:
    """Like _is_alive but retries on transient HTTP failures before declaring stale.

    Prevents a second lock-holder from killing a live daemon whose port is
    momentarily slow to respond (common on Windows under concurrent load).
    """
    for _ in range(retries):
        if _is_alive(hs):
            return True
        time.sleep(delay)
    return False


def ensure_daemon(vault_dir: Path, *, timeout_sec: float = 15.0) -> DaemonHandshake:
    """Return a running daemon handshake, spawning if necessary.

    A cross-platform advisory lock (``daemon.lock``) serializes concurrent
    callers so only the first one spawns; others wait, then read the
    handshake the first wrote.
    """

    vault_dir.mkdir(parents=True, exist_ok=True)
    lock_path = vault_dir / "daemon.lock"
    with portalocker.Lock(str(lock_path), timeout=timeout_sec):
        hs = read_handshake(vault_dir)
        if hs and _is_alive_with_retry(hs):
            return hs
        if hs:
            _cleanup_stale(vault_dir, hs)
        return _spawn(vault_dir, timeout_sec=timeout_sec)


def _cleanup_stale(vault_dir: Path, hs: DaemonHandshake) -> None:
    if psutil.pid_exists(hs.pid):
        try:
            psutil.Process(hs.pid).terminate()
        except psutil.Error:
            pass
    try:
        (vault_dir / "daemon.json").unlink(missing_ok=True)
    except OSError:
        pass


def _spawn(vault_dir: Path, *, timeout_sec: float) -> DaemonHandshake:
    creationflags = 0
    start_new_session = False
    if sys.platform == "win32":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    else:
        start_new_session = True

    log_path = vault_dir / "daemon.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "ab")
    try:
        subprocess.Popen(
            [sys.executable, "-m", "piighost.daemon", "--vault", str(vault_dir)],
            stdout=log_fh,
            stderr=log_fh,
            stdin=subprocess.DEVNULL,
            start_new_session=start_new_session,
            creationflags=creationflags,
            env=os.environ.copy(),
            close_fds=True,
        )
    finally:
        # The child has already inherited the fd; close our handle.
        log_fh.close()

    deadline = time.monotonic() + timeout_sec
    delay = 0.05
    while time.monotonic() < deadline:
        hs = read_handshake(vault_dir)
        if hs and _is_alive(hs):
            return hs
        time.sleep(delay)
        delay = min(delay * 1.6, 0.8)
    raise TimeoutError(
        f"daemon did not become healthy within {timeout_sec}s; "
        f"see {log_path}"
    )


def stop_daemon(vault_dir: Path) -> bool:
    """Stop the running daemon (if any). Returns ``True`` if one was found."""

    hs = read_handshake(vault_dir)
    if hs is None:
        return False
    try:
        httpx.post(
            f"http://127.0.0.1:{hs.port}/shutdown",
            headers={"Authorization": f"Bearer {hs.token}"},
            timeout=3.0,
        )
    except httpx.HTTPError:
        pass
    # Give the server a beat, then force-kill if still alive.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not psutil.pid_exists(hs.pid):
            break
        time.sleep(0.1)
    else:
        try:
            psutil.Process(hs.pid).kill()
        except psutil.Error:
            pass
    (vault_dir / "daemon.json").unlink(missing_ok=True)
    return True


def status(vault_dir: Path) -> DaemonHandshake | None:
    """Return the handshake if a live daemon is reachable, else ``None``."""

    hs = read_handshake(vault_dir)
    if hs is None:
        return None
    return hs if _is_alive(hs) else None
