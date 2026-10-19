"""Backend process supervision.

Each backend is an external checkout with its own virtualenv. The router never imports
backend code; it launches a small worker script with that venv's interpreter and speaks
HTTP to it. That is the only way to use two releases whose dependency pins conflict.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import threading
import time
from typing import Any, Dict, Optional

import httpx

from .config import BackendConfig

logger = logging.getLogger(__name__)


class BackendError(RuntimeError):
    """A backend failed to start, died, or returned an error."""


class BackendProcess:
    """Owns one worker subprocess and its HTTP client."""

    _RECENT_LINES = 200

    def __init__(self, config: BackendConfig):
        self.config = config
        self._process: Optional[subprocess.Popen] = None
        self._client = httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{config.port}",
            timeout=httpx.Timeout(30.0, read=3600.0),  # generation can take minutes
        )
        self.last_used = 0.0
        self._recent: list[str] = []
        self._drain: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    async def start(self) -> None:
        if self.running:
            return
        for path, label in ((self.config.python, "interpreter"), (self.config.worker, "worker")):
            if not path.exists():
                raise BackendError(f"{self.config.name}: {label} not found at {path}")

        logger.info("starting backend %s on port %s", self.config.name, self.config.port)
        # A PYTHONPATH inherited from the parent shell (ROS setups export one) would leak
        # foreign site-packages into the backend's virtualenv and shadow its pinned deps.
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        self._process = subprocess.Popen(
            [str(self.config.python), str(self.config.worker),
             "--port", str(self.config.port), *self.config.args],
            cwd=str(self.config.repo_path),  # worker scripts rely on repo-relative paths
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        # Relay the worker's output as it arrives. Without this it sits unread in the pipe,
        # so a backend traceback is invisible and only the generic error reaches the client.
        self._drain = threading.Thread(target=self._relay_output, daemon=True)
        self._drain.start()
        try:
            await self._await_health(self.config.startup_timeout)
        except Exception:
            await self.stop()
            raise
        self.last_used = time.time()

    def _relay_output(self) -> None:
        """Forward worker stdout/stderr into the router's log, keeping the last lines."""
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            for line in process.stdout:
                line = line.rstrip()
                if not line:
                    continue
                self._recent.append(line)
                del self._recent[:-self._RECENT_LINES]
                logger.info("[%s] %s", self.config.name, line)
        except Exception:  # the pipe closes when the worker exits
            pass

    def recent_output(self, lines: int = 20) -> str:
        return "\n".join(self._recent[-lines:])

    async def _await_health(self, timeout: float) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.running:
                raise BackendError(
                    f"{self.config.name} exited during startup:\n{self.recent_output(40)}"
                )
            try:
                response = await self._client.get("/health", timeout=5.0)
                if response.status_code == 200:
                    logger.info("backend %s ready", self.config.name)
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1.0)
        raise BackendError(f"{self.config.name} did not become healthy within {timeout:.0f}s")

    async def healthy(self) -> bool:
        if not self.running:
            return False
        try:
            return (await self._client.get("/health", timeout=3.0)).status_code == 200
        except httpx.HTTPError:
            return False

    async def generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.running:
            raise BackendError(f"{self.config.name} is not running")
        self.last_used = time.time()
        response = await self._client.post("/generate", json=payload)
        self.last_used = time.time()
        if response.status_code != 200:
            raise BackendError(
                f"{self.config.name}: {response.text[:500]}\n"
                f"--- recent {self.config.name} output ---\n{self.recent_output(30)}"
            )
        return response.json()

    async def stop(self) -> None:
        """Terminate the worker. This is what actually frees VRAM."""
        process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        logger.info("stopping backend %s", self.config.name)
        process.terminate()
        for _ in range(100):  # 10s grace
            if process.poll() is not None:
                break
            await asyncio.sleep(0.1)
        else:
            process.kill()
            process.wait(timeout=10)

    async def aclose(self) -> None:
        await self.stop()
        await self._client.aclose()
