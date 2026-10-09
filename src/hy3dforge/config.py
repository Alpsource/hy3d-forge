"""Configuration loading.

Paths in the YAML are resolved relative to the config file, so a checkout can be moved
without editing it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel, Field


class BackendConfig(BaseModel):
    name: str
    label: str = ""
    repo_path: Path
    python: Path
    worker: Path
    port: int
    vram_required_gib: float = 0.0
    quality: int = 0
    capabilities: List[str] = Field(default_factory=list)
    startup_timeout: float = 600.0
    # Extra CLI flags handed to the worker script, e.g. ["--texgen-subfolder", "..."]
    args: List[str] = Field(default_factory=list)

    @property
    def supports_pbr(self) -> bool:
        return "pbr" in self.capabilities


class Settings(BaseModel):
    artifacts_dir: Path = Path("./artifacts")
    host: str = "127.0.0.1"
    port: int = 8070
    gpu_total_gib: float = 24.0
    backend_idle_timeout: float = 900.0
    backends: List[BackendConfig]

    def backend(self, name: str) -> BackendConfig | None:
        return next((b for b in self.backends if b.name == name), None)


def _resolve(path: Path, base: Path) -> Path:
    return path if path.is_absolute() else (base / path).resolve()


def load_settings(config_path: str | os.PathLike | None = None) -> Settings:
    """Read config.yaml (or $HY3DFORGE_CONFIG) and resolve every path against it."""
    path = Path(config_path or os.environ.get("HY3DFORGE_CONFIG", "config.yaml")).resolve()
    if not path.exists():
        raise FileNotFoundError(
            f"No config at {path}. Copy config.example.yaml to config.yaml and edit the paths."
        )
    data = yaml.safe_load(path.read_text()) or {}
    settings = Settings(**data)

    base = path.parent
    settings.artifacts_dir = _resolve(settings.artifacts_dir, base)
    for backend in settings.backends:
        backend.repo_path = _resolve(backend.repo_path, base)
        backend.python = _resolve(backend.python, base)
        backend.worker = _resolve(backend.worker, base)
    return settings
