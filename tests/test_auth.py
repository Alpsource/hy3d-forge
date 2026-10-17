"""API key enforcement and the refusal to expose an unauthenticated port."""

import pytest
from fastapi.testclient import TestClient

from hy3dforge.api import create_app
from hy3dforge.config import BackendConfig, Settings

KEY = "secret-key-123"


def make_settings(tmp_path, keys=(), host="127.0.0.1", allow_insecure=False):
    return Settings(
        artifacts_dir=tmp_path, host=host, gpu_total_gib=24.0,
        api_keys=list(keys), allow_insecure=allow_insecure,
        backends=[BackendConfig(name="small", repo_path=".", python="p", worker="w",
                                port=1, vram_required_gib=16.0, quality=1,
                                capabilities=["albedo"])],
    )


def test_no_key_configured_means_open(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))) as client:
        assert client.get("/v1/backends").status_code == 200


def test_missing_key_is_rejected(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, [KEY]))) as client:
        assert client.get("/v1/backends").status_code == 401


def test_wrong_key_is_forbidden(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, [KEY]))) as client:
        response = client.get("/v1/backends", headers={"X-API-Key": "nope"})
        assert response.status_code == 403


def test_x_api_key_header_accepted(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, [KEY]))) as client:
        assert client.get("/v1/backends", headers={"X-API-Key": KEY}).status_code == 200


def test_bearer_token_accepted(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, [KEY]))) as client:
        response = client.get("/v1/backends", headers={"Authorization": f"Bearer {KEY}"})
        assert response.status_code == 200


def test_multiple_keys_all_work(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, [KEY, "second"]))) as client:
        for key in (KEY, "second"):
            assert client.get("/v1/backends", headers={"X-API-Key": key}).status_code == 200


def test_healthz_stays_open_for_probes(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, [KEY]))) as client:
        assert client.get("/healthz").status_code == 200


def test_job_submission_requires_a_key(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, [KEY]))) as client:
        files = {"image": ("a.png", b"data", "image/png")}
        assert client.post("/v1/jobs", files=files).status_code == 401
        assert client.post("/v1/jobs", files=files,
                           headers={"X-API-Key": KEY}).status_code == 202


def test_public_bind_without_keys_is_refused(tmp_path):
    with pytest.raises(ValueError, match="no api_keys"):
        create_app(make_settings(tmp_path, host="0.0.0.0"))


def test_public_bind_allowed_with_keys(tmp_path):
    app = create_app(make_settings(tmp_path, [KEY], host="0.0.0.0"))
    assert app is not None


def test_public_bind_allowed_when_explicitly_insecure(tmp_path):
    app = create_app(make_settings(tmp_path, host="0.0.0.0", allow_insecure=True))
    assert app is not None


def test_env_var_overrides_config_keys(tmp_path, monkeypatch):
    import yaml
    from hy3dforge.config import load_settings

    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({
        "api_keys": ["from-file"],
        "backends": [{"name": "b", "repo_path": ".", "python": "p", "worker": "w", "port": 1}],
    }))
    monkeypatch.setenv("HY3DFORGE_API_KEYS", "env-one, env-two")
    assert load_settings(config).api_keys == ["env-one", "env-two"]
