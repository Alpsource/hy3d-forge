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


def test_remove_background_defaults_to_auto(tmp_path):
    from hy3dforge.models import JobRequest, RemoveBackground

    assert JobRequest().remove_background is RemoveBackground.auto


def test_remove_background_accepts_each_mode(tmp_path):
    with build_client(tmp_path) as client:
        for mode in ("auto", "always", "never"):
            response = client.post(
                "/v1/jobs",
                files={"image": ("a.png", b"data", "image/png")},
                data={"backend": "small", "remove_background": mode},
            )
            assert response.status_code == 202, mode


def test_unknown_remove_background_mode_is_rejected(tmp_path):
    with build_client(tmp_path) as client:
        response = client.post(
            "/v1/jobs",
            files={"image": ("a.png", b"data", "image/png")},
            data={"backend": "small", "remove_background": "sometimes"},
        )
        assert response.status_code == 422


def build_text_client(tmp_path):
    """A client whose backend can serve text prompts."""
    from hy3dforge.api import create_app
    from hy3dforge.config import BackendConfig, Settings

    settings = Settings(
        artifacts_dir=tmp_path, gpu_total_gib=24.0,
        backends=[BackendConfig(name="small", repo_path=".", python="p", worker="w",
                                port=1, vram_required_gib=16.0, quality=1,
                                capabilities=["albedo", "text"])],
    )
    return TestClient(create_app(settings))


def test_prompt_without_image_is_accepted(tmp_path):
    with build_text_client(tmp_path) as client:
        response = client.post("/v1/jobs", data={"prompt": "a small stone statue"})
        assert response.status_code == 202


def test_neither_image_nor_prompt_is_rejected(tmp_path):
    with build_text_client(tmp_path) as client:
        response = client.post("/v1/jobs", data={})
        assert response.status_code == 400
        assert "image or a prompt" in response.json()["detail"]


def test_both_image_and_prompt_is_rejected(tmp_path):
    with build_text_client(tmp_path) as client:
        response = client.post(
            "/v1/jobs",
            files={"image": ("a.png", b"data", "image/png")},
            data={"prompt": "a cat"},
        )
        assert response.status_code == 400
        assert "not both" in response.json()["detail"]


def test_blank_prompt_counts_as_no_prompt(tmp_path):
    with build_text_client(tmp_path) as client:
        assert client.post("/v1/jobs", data={"prompt": "   "}).status_code == 400


def test_prompt_rejected_when_no_backend_supports_text(tmp_path):
    # build_client's backend advertises albedo only
    with build_client(tmp_path) as client:
        response = client.post("/v1/jobs", data={"prompt": "a cat"})
        assert response.status_code == 400
        assert "text" in response.json()["detail"]
