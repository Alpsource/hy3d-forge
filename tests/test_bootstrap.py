"""Bootstrap: cloning, pinning to a ref, and never touching existing checkouts."""

import subprocess

import pytest

from hy3dforge.bootstrap import SetupError, clone_backend, current_ref, install_backend, setup
from hy3dforge.config import BackendConfig, Settings


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
