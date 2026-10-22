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


class TestPrepareImage:
    """worker_common.prepare_image decides whether the cut-out runs.

    A stub stands in for a PIL image: the router's venv has no Pillow, and the decision
    only depends on mode and alpha anyway.
    """

    class FakeImage:
        def __init__(self, mode, min_alpha=255):
            self.mode = mode
            self._min_alpha = min_alpha
            self.converted_to = None

        def getextrema(self):
            return ((0, 255), (0, 255), (0, 255), (self._min_alpha, 255))

        def convert(self, mode):
            self.converted_to = mode
            return self

    @staticmethod
    def _load():
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "workers" / "worker_common.py"
        spec = importlib.util.spec_from_file_location("worker_common", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.prepare_image

    def test_never_returns_the_original_untouched(self):
        prepare = self._load()
        image = self.FakeImage("RGB")
        called = []
        assert prepare(image, "never", lambda i: called.append(i)) is image
        assert called == [], "rembg must not run when disabled"

    def test_always_cuts_out_even_an_already_transparent_image(self):
        prepare = self._load()
        marker = object()
        assert prepare(self.FakeImage("RGBA", min_alpha=0), "always", lambda i: marker) is marker

    def test_auto_cuts_out_an_opaque_image(self):
        prepare = self._load()
        marker = object()
        assert prepare(self.FakeImage("RGB"), "auto", lambda i: marker) is marker
        assert prepare(self.FakeImage("RGBA", min_alpha=255), "auto", lambda i: marker) is marker

    def test_auto_leaves_an_existing_cutout_alone(self):
        prepare = self._load()
        image = self.FakeImage("RGBA", min_alpha=0)
        assert prepare(image, "auto", lambda i: None) is image

    def test_cutout_input_is_converted_to_rgb_first(self):
        prepare = self._load()
        image = self.FakeImage("RGBA", min_alpha=255)
        prepare(image, "always", lambda i: i)
        assert image.converted_to == "RGB", "rembg expects RGB input"
