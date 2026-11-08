"""Bootstrap: cloning, pinning to a ref, and never touching existing checkouts."""

import subprocess

import pytest

from hy3dforge.bootstrap import (SetupError, clone_backend, current_ref, install_backend,
                                 license_notice, preflight, setup)
from hy3dforge.config import BackendConfig, Settings, load_settings


def make_origin(tmp_path, branch="main"):
    """A real local git repo to clone from, so no network is involved."""
    origin = tmp_path / "origin"
    origin.mkdir()
    run = lambda *a: subprocess.run(a, cwd=origin, check=True, capture_output=True)
    run("git", "init", "-q", "-b", branch)
    run("git", "config", "user.email", "t@t")
    run("git", "config", "user.name", "t")
    (origin / "README.md").write_text("backend")
    scripts = origin / "scripts"
    scripts.mkdir()
    (scripts / "install_linux.sh").write_text("#!/bin/bash\nmkdir -p env/bin\ntouch env/bin/python\n")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "init")
    return origin


def make_backend(tmp_path, origin, ref="main"):
    return BackendConfig(
        name="b", repo_path=tmp_path / "checkout", repo_url=str(origin), repo_ref=ref,
        python=tmp_path / "checkout" / "env" / "bin" / "python",
        worker=tmp_path / "worker.py", port=1,
    )



@pytest.fixture(autouse=True)
def _preflight_passes(monkeypatch):
    """Let the setup tests run on a machine without a GPU or a CUDA toolchain.

    setup() now preflights the host, which these tests are not about. The preflight's own
    behaviour is checked explicitly further down, where each input is set deliberately.
    """
    monkeypatch.setattr("hy3dforge.bootstrap._gpu_total_gib", lambda: 24.0)
    monkeypatch.setattr("hy3dforge.bootstrap.shutil.which", lambda name: f"/usr/bin/{name}")


def test_clone_creates_the_checkout(tmp_path):
    backend = make_backend(tmp_path, make_origin(tmp_path))
    assert clone_backend(backend) is True
    assert (backend.repo_path / "README.md").exists()


def test_existing_checkout_is_left_alone(tmp_path):
    backend = make_backend(tmp_path, make_origin(tmp_path))
    clone_backend(backend)
    (backend.repo_path / "local_change.txt").write_text("mine")
    assert clone_backend(backend) is False
    assert (backend.repo_path / "local_change.txt").exists()


def test_clone_honours_the_pinned_ref(tmp_path):
    origin = make_origin(tmp_path, branch="main")
    subprocess.run(["git", "checkout", "-qb", "pinned"], cwd=origin, check=True)
    (origin / "only_on_branch.txt").write_text("x")
    subprocess.run(["git", "add", "-A"], cwd=origin, check=True)
    subprocess.run(["git", "commit", "-qm", "branch"], cwd=origin, check=True)

    backend = make_backend(tmp_path, origin, ref="pinned")
    clone_backend(backend)
    assert (backend.repo_path / "only_on_branch.txt").exists()
    assert current_ref(backend.repo_path).startswith("pinned@")


def test_missing_checkout_without_url_is_an_error(tmp_path):
    backend = BackendConfig(name="b", repo_path=tmp_path / "nope", python="p",
                            worker="w", port=1)
    with pytest.raises(SetupError, match="no repo_url"):
        clone_backend(backend)


def test_install_runs_the_backend_script(tmp_path):
    backend = make_backend(tmp_path, make_origin(tmp_path))
    clone_backend(backend)
    assert install_backend(backend) is True
    assert backend.python.exists()


def test_install_skipped_when_venv_exists(tmp_path):
    backend = make_backend(tmp_path, make_origin(tmp_path))
    clone_backend(backend)
    install_backend(backend)
    assert install_backend(backend) is False


def test_setup_end_to_end(tmp_path):
    origin = make_origin(tmp_path)
    backend = make_backend(tmp_path, origin)
    backend.worker.write_text("# worker")
    settings = Settings(artifacts_dir=tmp_path, backends=[backend])
    assert setup(settings) == 0


def test_setup_rejects_unknown_backend_name(tmp_path):
    settings = Settings(artifacts_dir=tmp_path,
                        backends=[make_backend(tmp_path, make_origin(tmp_path))])
    assert setup(settings, only=["does-not-exist"]) == 2


# --- third-party licences -------------------------------------------------------------
#
# Cloning is the one moment hy3dforge fetches someone else's model code for a user, so it
# is the moment that licence has to be seen. A backend with no licence declared is not
# gated, which is what keeps the tests above untouched.

LICENSED = dict(
    license="Example Community License",
    license_url="https://example.invalid/LICENSE",
    license_notes=["Not licensed in the EU, the UK or South Korea."],
)


def make_licensed_backend(tmp_path, origin):
    backend = make_backend(tmp_path, origin)
    return backend.model_copy(update=LICENSED)


def test_unattended_clone_refuses_without_acceptance(tmp_path, monkeypatch):
    """A pipeline must not accept a licence by failing to notice it was asked."""
    backend = make_licensed_backend(tmp_path, make_origin(tmp_path))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    with pytest.raises(SetupError, match="accepted before it can be installed"):
        clone_backend(backend)
    assert not backend.repo_path.exists()


def test_accept_licenses_flag_allows_an_unattended_clone(tmp_path, monkeypatch):
    backend = make_licensed_backend(tmp_path, make_origin(tmp_path))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    assert clone_backend(backend, assume_yes=True) is True
    assert (backend.repo_path / "README.md").exists()


def test_typing_accept_allows_the_clone(tmp_path, monkeypatch):
    backend = make_licensed_backend(tmp_path, make_origin(tmp_path))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "accept")

    assert clone_backend(backend) is True


@pytest.mark.parametrize("answer", ["", "y", "yes", "no", "ACCEPTED"])
def test_anything_but_accept_installs_nothing(tmp_path, monkeypatch, answer):
    backend = make_licensed_backend(tmp_path, make_origin(tmp_path))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: answer)

    with pytest.raises(SetupError, match="licence not accepted"):
        clone_backend(backend)
    assert not backend.repo_path.exists()


def test_an_existing_checkout_is_not_gated(tmp_path, monkeypatch):
    """Whoever put it there already obtained it; this is not our fetch to gate."""
    backend = make_licensed_backend(tmp_path, make_origin(tmp_path))
    clone_backend(backend, assume_yes=True)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    assert clone_backend(backend) is False


def test_the_notice_carries_the_terms_and_disclaims_a_sublicence(tmp_path):
    backend = make_licensed_backend(tmp_path, make_origin(tmp_path))
    notice = license_notice(backend)

    assert "Example Community License" in notice
    assert "https://example.invalid/LICENSE" in notice
    assert "Not licensed in the EU" in notice
    assert "grants you nothing" in notice


def test_the_shipped_config_declares_both_tencent_licences():
    """The example config is what a new user copies; it must carry the real terms."""
    settings = load_settings("config.example.yaml")

    for backend in settings.backends:
        notice = license_notice(backend)
        assert "Tencent Hunyuan" in backend.license
        assert backend.license_url.startswith("https://")
        assert "EU" in notice and "South Korea" in notice
        assert "1 million monthly active users" in notice


# --- preflight -------------------------------------------------------------------------
#
# The point of these is that an install which cannot succeed should say so in seconds
# rather than after downloading 20 GiB and stopping in a compiler error.


def preflight_settings(tmp_path, gpu_total_gib=24.0):
    backend = BackendConfig(
        name="b", repo_path=tmp_path / "checkout",
        python=tmp_path / "checkout" / "env" / "bin" / "python",
        worker=tmp_path / "worker.py", port=1,
    )
    return Settings(artifacts_dir=tmp_path, gpu_total_gib=gpu_total_gib, backends=[backend])


def test_a_healthy_machine_has_nothing_to_report(tmp_path):
    settings = preflight_settings(tmp_path)
    assert preflight(settings, settings.backends) == []


def test_missing_git_is_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr("hy3dforge.bootstrap.shutil.which",
                        lambda name: None if name == "git" else f"/usr/bin/{name}")
    settings = preflight_settings(tmp_path)
    assert any("git" in p for p in preflight(settings, settings.backends))


def test_no_gpu_is_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr("hy3dforge.bootstrap._gpu_total_gib", lambda: None)
    settings = preflight_settings(tmp_path)
    assert any("NVIDIA" in p for p in preflight(settings, settings.backends))


def test_setup_stops_before_touching_anything_when_preflight_fails(tmp_path, monkeypatch):
    monkeypatch.setattr("hy3dforge.bootstrap._gpu_total_gib", lambda: None)
    settings = preflight_settings(tmp_path)
    assert setup(settings) == 2
    assert not (tmp_path / "checkout").exists()


def test_a_config_claiming_more_vram_than_the_card_has_warns(tmp_path, monkeypatch, caplog):
    # The trap this exists for: the shipped config says 24 GiB, so someone with a 12 GiB
    # card who changes nothing gets a backend selected that cannot load.
    monkeypatch.setattr("hy3dforge.bootstrap._gpu_total_gib", lambda: 12.0)
    settings = preflight_settings(tmp_path, gpu_total_gib=24.0)
    with caplog.at_level("WARNING"):
        assert preflight(settings, settings.backends) == []
    assert "gpu_total_gib" in caplog.text
    assert "12.0" in caplog.text


def test_a_smaller_card_than_configured_is_not_warned_about(tmp_path, monkeypatch, caplog):
    # Configuring less than the card holds is deliberate - leaving room for a display, say.
    monkeypatch.setattr("hy3dforge.bootstrap._gpu_total_gib", lambda: 24.0)
    settings = preflight_settings(tmp_path, gpu_total_gib=16.0)
    with caplog.at_level("WARNING"):
        preflight(settings, settings.backends)
    assert "gpu_total_gib" not in caplog.text


def test_missing_nvcc_warns_when_a_venv_must_be_built(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr("hy3dforge.bootstrap.shutil.which",
                        lambda name: None if name == "nvcc" else f"/usr/bin/{name}")
    settings = preflight_settings(tmp_path)
    with caplog.at_level("WARNING"):
        assert preflight(settings, settings.backends) == []
    assert "nvcc" in caplog.text


def test_missing_nvcc_is_quiet_when_every_venv_is_already_built(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr("hy3dforge.bootstrap.shutil.which",
                        lambda name: None if name == "nvcc" else f"/usr/bin/{name}")
    settings = preflight_settings(tmp_path)
    built = settings.backends[0].python
    built.parent.mkdir(parents=True)
    built.touch()
    settings.backends[0].repo_path.mkdir(exist_ok=True)
    with caplog.at_level("WARNING"):
        preflight(settings, settings.backends)
    assert "nvcc" not in caplog.text


def test_short_disk_warns(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr("hy3dforge.bootstrap._free_gib", lambda path: 3.0)
    settings = preflight_settings(tmp_path)
    with caplog.at_level("WARNING"):
        assert preflight(settings, settings.backends) == []
    assert "GiB free" in caplog.text
