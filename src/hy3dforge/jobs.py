"""Job queue.

Generation is serialised: one job holds the GPU at a time. Requests return a job id
immediately because a run takes one to three minutes, far past any sane HTTP timeout.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from .backend import BackendError
from .models import Job, JobRequest, JobStatus
from .registry import BackendRegistry

logger = logging.getLogger(__name__)


class JobQueue:
    def __init__(self, registry: BackendRegistry, artifacts_dir: Path):
        self.registry = registry
        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: Dict[str, Job] = {}
        self._requests: Dict[str, JobRequest] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())

    async def aclose(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass

    def job_dir(self, job_id: str) -> Path:
        return self.artifacts_dir / job_id

    def submit(self, request: JobRequest, image_bytes: bytes, filename: str) -> Job:
        job_id = uuid.uuid4().hex[:12]
        directory = self.job_dir(job_id)
        directory.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix.lower() or ".png"
        (directory / f"input{suffix}").write_bytes(image_bytes)

        job = Job(id=job_id, status=JobStatus.queued, created_at=time.time())
        self._jobs[job_id] = job
        self._requests[job_id] = request
        self._queue.put_nowait(job_id)
        self._refresh_queue_positions()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list(self, limit: int = 50) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]

    def _refresh_queue_positions(self) -> None:
        pending = [j for j in self._jobs.values() if j.status is JobStatus.queued]
        for position, job in enumerate(sorted(pending, key=lambda j: j.created_at), start=1):
            job.queue_position = position

    def delete(self, job_id: str) -> bool:
        """Forget a job and remove its files."""
        job = self._jobs.pop(job_id, None)
        self._requests.pop(job_id, None)
        if job is None:
            return False
        shutil.rmtree(self.job_dir(job_id), ignore_errors=True)
        return True

    def _sweepable(self) -> List[tuple]:
        """Every artifact directory that may be removed, as (timestamp, dir, job_id).

        Covers finished jobs and orphan directories left by a previous run - the job
        registry is in memory, so after a restart nothing on disk has a job record and
        those directories would otherwise be kept forever.
        """
        finished = {
            job.id: job for job in self._jobs.values()
            if job.status in (JobStatus.succeeded, JobStatus.failed)
        }
        live = {
            job.id for job in self._jobs.values()
            if job.status in (JobStatus.queued, JobStatus.running)
        }

        entries = []
        if self.artifacts_dir.exists():
            for directory in self.artifacts_dir.iterdir():
                if not directory.is_dir() or directory.name in live:
                    continue  # never touch work in flight
                job = finished.get(directory.name)
                if job is not None:
                    entries.append(((job.finished_at or job.created_at), directory, job.id))
                elif directory.name not in self._jobs:
                    entries.append((directory.stat().st_mtime, directory, None))
        return sorted(entries)

    def _remove(self, directory: Path, job_id: Optional[str]) -> None:
        if job_id is not None:
            self.delete(job_id)
        else:
            shutil.rmtree(directory, ignore_errors=True)

    def sweep(self, max_age_days: float, max_total_gib: float) -> int:
        """Apply the retention policy. Queued and running jobs are never removed."""
        entries = self._sweepable()
        removed = 0

        if max_age_days > 0:
            cutoff = time.time() - max_age_days * 86400
            remaining = []
            for timestamp, directory, job_id in entries:
                if timestamp < cutoff:
                    self._remove(directory, job_id)
                    removed += 1
                else:
                    remaining.append((timestamp, directory, job_id))
            entries = remaining

        if max_total_gib > 0:
            limit = max_total_gib * 2 ** 30
            total = self._artifacts_size()
            for timestamp, directory, job_id in entries:  # oldest first
                if total <= limit:
                    break
                total -= self._dir_size(directory)
                self._remove(directory, job_id)
                removed += 1

        if removed:
            logger.info("retention sweep removed %d artifact dir(s)", removed)
        return removed

    @staticmethod
    def _dir_size(path: Path) -> int:
        if not path.exists():
            return 0
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())

    def _artifacts_size(self) -> int:
        return self._dir_size(self.artifacts_dir)

    async def _run(self) -> None:
        while True:
            job_id = await self._queue.get()
            job, request = self._jobs.get(job_id), self._requests.get(job_id)
            if job is None or request is None:
                continue
            try:
                await self._execute(job, request)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # a bad job must not kill the worker loop
                logger.exception("job %s failed", job_id)
                job.status = JobStatus.failed
                job.error = str(error)[:1000]
                job.finished_at = time.time()
            finally:
                job.queue_position = None
                self._refresh_queue_positions()
                self._queue.task_done()

    async def _execute(self, job: Job, request: JobRequest) -> None:
        job.status = JobStatus.running
        job.started_at = time.time()

        name = self.registry.select(request.backend, request.require_pbr)
        job.backend = name
        backend = await self.registry.acquire(name)

        directory = self.job_dir(job.id)
        image = next(directory.glob("input.*"))
        payload = {
            "image_path": str(image),
            "output_dir": str(directory),
            "params": request.model_dump(exclude={"backend", "require_pbr"}),
        }
        result = await backend.generate(payload)

        output = result.get("output_path")
        if not output or not Path(output).exists():
            raise BackendError(f"{name} reported success but produced no file")
        job.result_path = output
        job.stats = result.get("stats", {})
        job.status = JobStatus.succeeded
        job.finished_at = time.time()
        logger.info("job %s done on %s in %.0fs", job.id, name, job.finished_at - job.started_at)
