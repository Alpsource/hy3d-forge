"""Backend selection rules - the part worth testing without a GPU."""

import pytest

from hy3dforge.backend import BackendError
from hy3dforge.config import BackendConfig, Settings
from hy3dforge.registry import BackendRegistry


def make_settings(gpu_gib=24.0):
    return Settings(
        gpu_total_gib=gpu_gib,
        backends=[
            BackendConfig(name="small", repo_path=".", python="p", worker="w", port=1,
                          vram_required_gib=16.0, quality=1, capabilities=["albedo"]),
            BackendConfig(name="big", repo_path=".", python="p", worker="w", port=2,
                          vram_required_gib=22.0, quality=2, capabilities=["albedo", "pbr"]),
        ],
    )


def test_auto_prefers_highest_quality_that_fits():
    registry = BackendRegistry(make_settings(24.0))
    assert registry.select("auto", require_pbr=False) == "big"


def test_auto_falls_back_when_vram_is_short():
    registry = BackendRegistry(make_settings(18.0))
    assert registry.select("auto", require_pbr=False) == "small"


def test_pbr_requirement_excludes_incapable_backends():
    registry = BackendRegistry(make_settings(18.0))
    with pytest.raises(BackendError, match="no backend with PBR"):
        registry.select("auto", require_pbr=True)


def test_explicit_backend_is_honoured_even_if_lower_quality():
    registry = BackendRegistry(make_settings(24.0))
    assert registry.select("small", require_pbr=False) == "small"


def test_explicit_backend_rejects_impossible_pbr_request():
    registry = BackendRegistry(make_settings(24.0))
    with pytest.raises(BackendError, match="cannot produce PBR"):
        registry.select("small", require_pbr=True)


def test_unknown_backend_is_rejected():
    registry = BackendRegistry(make_settings())
    with pytest.raises(BackendError, match="unknown backend"):
        registry.select("nope", require_pbr=False)
