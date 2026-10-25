"""Public API schemas.

These are deliberately backend-agnostic: a client should not need to know whether the
job ran on 2.0 or 2.1. Backend-specific knobs go in `extra`.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class RemoveBackground(str, Enum):
    """How the input image is cut out before shape generation."""

    auto = "auto"      # cut out unless the image already carries real transparency
    always = "always"  # cut out regardless
    never = "never"    # use the image exactly as given


class GenerateParams(BaseModel):
    texture: bool = True
    remove_background: RemoveBackground = RemoveBackground.auto
    target_face_num: int = Field(10000, ge=0, le=1_000_000)
    steps: int = Field(30, ge=1, le=200)
    guidance_scale: float = 5.0
    octree_resolution: int = Field(256, ge=16, le=512)
    seed: int = 1234
    extra: Dict[str, Any] = Field(default_factory=dict)


class JobRequest(GenerateParams):
    # "auto" picks the best backend that fits the GPU; or name one explicitly.
    backend: str = "auto"
    # Ask for PBR maps; with backend="auto" this restricts selection to capable backends.
    require_pbr: bool = False
    # Text to 3D: the backend generates an image from this first, then meshes it.
    # Only backends advertising the "text" capability can serve it.
    prompt: Optional[str] = None

    @property
    def is_text_job(self) -> bool:
        return bool(self.prompt and self.prompt.strip())


class Job(BaseModel):
    id: str
    status: JobStatus
    backend: Optional[str] = None
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    result_path: Optional[str] = None
    stats: Dict[str, Any] = Field(default_factory=dict)
    queue_position: Optional[int] = None

    @property
    def result_url(self) -> Optional[str]:
        return f"/v1/jobs/{self.id}/result" if self.status is JobStatus.succeeded else None


class BackendInfo(BaseModel):
    name: str
    label: str
    capabilities: List[str]
    vram_required_gib: float
    quality: int
    loaded: bool
    healthy: bool
