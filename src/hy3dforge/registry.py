"""Backend selection and the one-at-a-time GPU residency rule."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Optional

from .backend import BackendError, BackendProcess
from .config import Settings
from .models import BackendInfo

logger = logging.getLogger(__name__)


class BackendRegistry:
    """Keeps at most one backend resident, because the GPU fits one at a time."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._backends: Dict[str, BackendProcess] = {
            b.name: BackendProcess(b) for b in settings.backends
        }
        self._active: Optional[str] = None
        self._lock = asyncio.Lock()

    def select(self, requested: str, require_pbr: bool, require_text: bool = False) -> str:
        """Resolve a backend name, or pick the best one that fits the GPU."""
        if requested != "auto":
            config = self.settings.backend(requested)
            if config is None:
                raise BackendError(f"unknown backend '{requested}'")
            if require_pbr and not config.supports_pbr:
                raise BackendError(f"backend '{requested}' cannot produce PBR maps")
            if require_text and not config.supports_text:
                raise BackendError(f"backend '{requested}' cannot generate from a text prompt")
            return requested

        candidates = [
            b for b in self.settings.backends
            if b.vram_required_gib <= self.settings.gpu_total_gib
            and (not require_pbr or b.supports_pbr)
            and (not require_text or b.supports_text)
        ]
        if not candidates:
            wants = [w for w, on in (("PBR", require_pbr), ("text prompt", require_text)) if on]
            detail = f" supporting {' and '.join(wants)}" if wants else ""
            raise BackendError(
                f"no backend{detail} fits {self.settings.gpu_total_gib:.0f} GiB of VRAM"
            )
        # Best quality that fits; ties broken by the smaller footprint.
        return max(candidates, key=lambda b: (b.quality, -b.vram_required_gib)).name

    async def acquire(self, name: str) -> BackendProcess:
        """Make `name` the resident backend, stopping whatever else is loaded."""
        async with self._lock:
            backend = self._backends[name]
            if self._active == name and await backend.healthy():
                return backend
            if self._active is not None and self._active != name:
                await self._backends[self._active].stop()
                self._active = None
            await backend.start()
            self._active = name
            return backend

    async def reap_idle(self) -> None:
        """Stop the resident backend once it has been idle long enough."""
        timeout = self.settings.backend_idle_timeout
        if not timeout or self._active is None:
            return
        async with self._lock:
            name = self._active
            if name is None:
                return
            backend = self._backends[name]
            if backend.running and time.time() - backend.last_used > timeout:
                logger.info("backend %s idle for %.0fs, stopping", name, timeout)
                await backend.stop()
                self._active = None

    async def info(self) -> List[BackendInfo]:
        out = []
        for config in self.settings.backends:
            backend = self._backends[config.name]
            out.append(
                BackendInfo(
                    name=config.name,
                    label=config.label or config.name,
                    capabilities=config.capabilities,
                    vram_required_gib=config.vram_required_gib,
                    quality=config.quality,
                    loaded=backend.running,
                    healthy=await backend.healthy(),
                )
            )
        return out

    async def aclose(self) -> None:
        for backend in self._backends.values():
            await backend.aclose()
