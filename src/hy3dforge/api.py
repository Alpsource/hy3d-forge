"""HTTP API.

Versioned under /v1 so the contract can evolve without breaking the Unity client.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .backend import BackendError
from .config import Settings, load_settings
from .jobs import JobQueue
from .models import BackendInfo, Job, JobRequest, JobStatus
from .registry import BackendRegistry

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 32 * 1024 * 1024


def _make_auth_dependency(settings: Settings):
    """Require a configured API key, unless none are configured at all."""

    async def require_api_key(
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
        authorization: Optional[str] = Header(default=None),
    ) -> None:
        if not settings.auth_enabled:
            return
        presented = x_api_key
        if not presented and authorization and authorization.lower().startswith("bearer "):
            presented = authorization[7:].strip()
        if not presented:
            raise HTTPException(401, "missing API key")
        # compare_digest against every key: constant time, no early exit on prefix
        if not any(secrets.compare_digest(presented, key) for key in settings.api_keys):
            raise HTTPException(403, "invalid API key")

    return require_api_key


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or load_settings()
    settings.check_exposure()
    auth = Depends(_make_auth_dependency(settings))
    registry = BackendRegistry(settings)
    queue = JobQueue(registry, settings.artifacts_dir)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        queue.start()
        reaper = asyncio.create_task(_reap_idle_backends(registry))
        sweeper = asyncio.create_task(_sweep_artifacts(queue, settings))
        try:
            yield
        finally:
            reaper.cancel()
            sweeper.cancel()
            await queue.aclose()
            await registry.aclose()

    app = FastAPI(title="hy3dforge", version="1", lifespan=lifespan)
    app.state.settings = settings
    app.state.registry = registry
    app.state.queue = queue

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/v1/backends", response_model=List[BackendInfo], dependencies=[auth])
    async def backends():
        return await registry.info()

    @app.post("/v1/jobs", response_model=Job, status_code=202, dependencies=[auth])
    async def create_job(
        image: UploadFile = File(...),
        request: JobRequest = Depends(_job_request_form),
    ):
        data = await image.read()
        if not data:
            raise HTTPException(400, "empty image upload")
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"image exceeds {MAX_UPLOAD_BYTES // 1024 // 1024} MB")
        try:
            registry.select(request.backend, request.require_pbr)  # fail fast on bad input
        except BackendError as error:
            raise HTTPException(400, str(error)) from error
        return queue.submit(request, data, image.filename or "input.png")

    @app.get("/v1/jobs", response_model=List[Job], dependencies=[auth])
    async def list_jobs(limit: int = 50):
        return queue.list(limit)

    @app.get("/v1/jobs/{job_id}", response_model=Job, dependencies=[auth])
    async def get_job(job_id: str):
        job = queue.get(job_id)
        if job is None:
            raise HTTPException(404, "no such job")
        return job

    @app.get("/v1/jobs/{job_id}/result", dependencies=[auth])
    async def get_result(job_id: str):
        job = queue.get(job_id)
        if job is None:
            raise HTTPException(404, "no such job")
        if job.result_path is None:
            raise HTTPException(409, f"job is {job.status.value}")
        path = Path(job.result_path)
        if not path.exists():
            raise HTTPException(410, "result file is gone")
        return FileResponse(path, media_type="model/gltf-binary", filename=path.name)

    @app.delete("/v1/jobs/{job_id}", status_code=204, dependencies=[auth])
    async def delete_job(job_id: str):
        job = queue.get(job_id)
        if job is None:
            raise HTTPException(404, "no such job")
        if job.status in (JobStatus.queued, JobStatus.running):
            raise HTTPException(409, f"job is {job.status.value}; wait for it to finish")
        queue.delete(job_id)

    return app


def _job_request_form(
    backend: str = Form("auto"),
    require_pbr: bool = Form(False),
    texture: bool = Form(True),
    target_face_num: int = Form(10000),
    steps: int = Form(30),
    guidance_scale: float = Form(5.0),
    octree_resolution: int = Form(256),
    seed: int = Form(1234),
) -> JobRequest:
    """Accept the job options as multipart form fields alongside the image."""
    return JobRequest(
        backend=backend,
        require_pbr=require_pbr,
        texture=texture,
        target_face_num=target_face_num,
        steps=steps,
        guidance_scale=guidance_scale,
        octree_resolution=octree_resolution,
        seed=seed,
    )


async def _sweep_artifacts(queue: JobQueue, settings: Settings) -> None:
    """Apply the retention policy on a timer so artifacts cannot grow without bound."""
    policy = settings.retention
    while True:
        await asyncio.sleep(policy.sweep_interval)
        try:
            queue.sweep(policy.max_age_days, policy.max_total_gib)
        except Exception:
            logger.exception("retention sweep failed")


async def _reap_idle_backends(registry: BackendRegistry) -> None:
    while True:
        await asyncio.sleep(30)
        try:
            await registry.reap_idle()
        except Exception:
            logger.exception("idle reaper failed")
