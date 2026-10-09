"""API contract checks that do not need a GPU or a real backend."""

from fastapi.testclient import TestClient

from hy3dforge.api import create_app
from hy3dforge.config import BackendConfig, Settings


def build_client(tmp_path):
    settings = Settings(
        artifacts_dir=tmp_path,
        gpu_total_gib=24.0,
        backends=[
            BackendConfig(name="small", repo_path=".", python="p", worker="w", port=1,
                          vram_required_gib=16.0, quality=1, capabilities=["albedo"]),
        ],
    )
    return TestClient(create_app(settings))


def test_healthz(tmp_path):
    with build_client(tmp_path) as client:
        assert client.get("/healthz").json() == {"status": "ok"}


def test_backends_listed(tmp_path):
    with build_client(tmp_path) as client:
        names = [b["name"] for b in client.get("/v1/backends").json()]
        assert names == ["small"]


def test_job_accepted_and_queued(tmp_path):
    with build_client(tmp_path) as client:
        response = client.post(
            "/v1/jobs",
            files={"image": ("a.png", b"\x89PNG fake bytes", "image/png")},
            data={"backend": "small"},
        )
        assert response.status_code == 202
        assert response.json()["status"] in {"queued", "running"}


def test_unsatisfiable_pbr_request_is_rejected(tmp_path):
    with build_client(tmp_path) as client:
        response = client.post(
            "/v1/jobs",
            files={"image": ("a.png", b"fake", "image/png")},
            data={"require_pbr": "true"},
        )
        assert response.status_code == 400
        assert "PBR" in response.json()["detail"]


def test_empty_upload_rejected(tmp_path):
    with build_client(tmp_path) as client:
        response = client.post("/v1/jobs", files={"image": ("a.png", b"", "image/png")})
        assert response.status_code == 400


def test_result_before_completion_is_conflict(tmp_path):
    with build_client(tmp_path) as client:
        job = client.post("/v1/jobs", files={"image": ("a.png", b"x", "image/png")}).json()
        assert client.get(f"/v1/jobs/{job['id']}/result").status_code in {409, 404}
