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
    # Where `hy3dforge setup` clones the backend from when repo_path is missing.
    # repo_ref pins it the way a submodule would: a branch, tag or commit.
    repo_url: str | None = None
    repo_ref: str = "main"
    install_script: str = "scripts/install_linux.sh"
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


class RetentionConfig(BaseModel):
    """How long generated artifacts are kept. Both limits apply; 0 disables one."""

    max_age_days: float = 7.0
    max_total_gib: float = 20.0
    sweep_interval: float = 600.0


class Settings(BaseModel):
    artifacts_dir: Path = Path("./artifacts")
    host: str = "127.0.0.1"
    port: int = 8070
    gpu_total_gib: float = 24.0
    backend_idle_timeout: float = 900.0
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    # Clients must send one of these as X-API-Key or "Authorization: Bearer ...".
    # Empty means no authentication, which is only allowed on a loopback bind.
    api_keys: List[str] = Field(default_factory=list)
    allow_insecure: bool = False
    backends: List[BackendConfig]

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_keys)

    def check_exposure(self) -> None:
        """Refuse to listen beyond loopback without authentication."""
        loopback = self.host in {"127.0.0.1", "localhost", "::1"}
        if not loopback and not self.auth_enabled and not self.allow_insecure:
            raise ValueError(
                f"host is {self.host} but no api_keys are configured. Anyone who can reach "
                "this port could spend your GPU. Set api_keys, bind 127.0.0.1, or set "
                "allow_insecure: true if that is genuinely what you want."
            )

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

    # HY3DFORGE_API_KEYS takes precedence, so deployments can keep keys out of the file.
    from_env = os.environ.get("HY3DFORGE_API_KEYS", "").strip()
    if from_env:
        settings.api_keys = [k.strip() for k in from_env.split(",") if k.strip()]

    base = path.parent
    settings.artifacts_dir = _resolve(settings.artifacts_dir, base)
    for backend in settings.backends:
        backend.repo_path = _resolve(backend.repo_path, base)
        backend.python = _resolve(backend.python, base)
        backend.worker = _resolve(backend.worker, base)
    return settings
