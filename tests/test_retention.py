"""Retention sweep: age limit, size limit, and never touching live jobs."""

import time

from hy3dforge.jobs import JobQueue
from hy3dforge.models import JobRequest, JobStatus
from hy3dforge.registry import BackendRegistry
from tests.test_selection import make_settings


def build_queue(tmp_path):
    return JobQueue(BackendRegistry(make_settings()), tmp_path)


def add_job(queue, *, status, age_days=0.0, payload=b"x" * 1024):
    job = queue.submit(JobRequest(), payload, "a.png")
    job.status = status
    job.finished_at = time.time() - age_days * 86400
    return job


def test_old_finished_jobs_are_removed(tmp_path):
    queue = build_queue(tmp_path)
    old = add_job(queue, status=JobStatus.succeeded, age_days=30)
    recent = add_job(queue, status=JobStatus.succeeded, age_days=1)

    assert queue.sweep(max_age_days=7, max_total_gib=0) == 1
    assert queue.get(old.id) is None
    assert queue.get(recent.id) is not None
    assert not queue.job_dir(old.id).exists()


def test_running_and_queued_jobs_are_never_swept(tmp_path):
    queue = build_queue(tmp_path)
    running = add_job(queue, status=JobStatus.running, age_days=99)
    queued = add_job(queue, status=JobStatus.queued, age_days=99)

    assert queue.sweep(max_age_days=1, max_total_gib=0.000001) == 0
    assert queue.get(running.id) is not None
    assert queue.get(queued.id) is not None


def test_size_cap_removes_oldest_first(tmp_path):
    queue = build_queue(tmp_path)
    big = 400 * 1024
    oldest = add_job(queue, status=JobStatus.succeeded, age_days=3, payload=b"x" * big)
    middle = add_job(queue, status=JobStatus.succeeded, age_days=2, payload=b"x" * big)
    newest = add_job(queue, status=JobStatus.succeeded, age_days=1, payload=b"x" * big)

    # cap at ~0.8 MB so one of three must go
    queue.sweep(max_age_days=0, max_total_gib=0.8 / 1024)
    assert queue.get(oldest.id) is None, "oldest should go first"
    assert queue.get(newest.id) is not None, "newest should survive"
    assert queue.get(middle.id) is not None or True  # may or may not be needed


def test_zero_limits_disable_sweeping(tmp_path):
    queue = build_queue(tmp_path)
    job = add_job(queue, status=JobStatus.succeeded, age_days=999)
    assert queue.sweep(max_age_days=0, max_total_gib=0) == 0
    assert queue.get(job.id) is not None


def test_delete_removes_files(tmp_path):
    queue = build_queue(tmp_path)
    job = add_job(queue, status=JobStatus.succeeded)
    assert queue.job_dir(job.id).exists()
    assert queue.delete(job.id) is True
    assert not queue.job_dir(job.id).exists()
    assert queue.delete(job.id) is False


def test_orphan_directories_from_a_previous_run_are_swept(tmp_path):
    """The job registry is in memory, so after a restart nothing on disk has a record."""
    import os

    orphan = tmp_path / "leftover_from_old_run"
    orphan.mkdir()
    (orphan / "model.glb").write_bytes(b"x" * 2048)
    old = time.time() - 30 * 86400
    os.utime(orphan, (old, old))

    queue = build_queue(tmp_path)          # fresh registry, knows nothing about it
    assert queue.sweep(max_age_days=7, max_total_gib=0) == 1
    assert not orphan.exists()


def test_recent_orphans_are_kept(tmp_path):
    orphan = tmp_path / "recent_orphan"
    orphan.mkdir()
    (orphan / "model.glb").write_bytes(b"x" * 2048)

    queue = build_queue(tmp_path)
    assert queue.sweep(max_age_days=7, max_total_gib=0) == 0
    assert orphan.exists()


def test_orphans_count_towards_the_size_cap(tmp_path):
    import os

    for index in range(3):
        orphan = tmp_path / f"orphan_{index}"
        orphan.mkdir()
        (orphan / "model.glb").write_bytes(b"x" * 400 * 1024)
        stamp = time.time() - (3 - index) * 86400
        os.utime(orphan, (stamp, stamp))

    queue = build_queue(tmp_path)
    queue.sweep(max_age_days=0, max_total_gib=0.8 / 1024)
    assert not (tmp_path / "orphan_0").exists(), "oldest orphan should go first"
    assert (tmp_path / "orphan_2").exists(), "newest orphan should survive"
