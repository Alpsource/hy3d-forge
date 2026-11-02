"""What someone sees the first time they run the command.

A new install gets its config wrong before it gets anything else wrong, so these check that
the failure reads as an instruction rather than as a crash.
"""

import pytest

from hy3dforge import __version__
from hy3dforge.cli import main


@pytest.fixture(autouse=True)
def _clean_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HY3DFORGE_CONFIG", raising=False)


def _run(monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["hy3dforge", *argv])
    with pytest.raises(SystemExit) as caught:
        main()
    return caught.value


def test_version_flag(monkeypatch, capsys):
    assert _run(monkeypatch, "--version").code == 0
    assert capsys.readouterr().out.strip() == f"hy3dforge {__version__}"


def test_missing_config_explains_itself(monkeypatch):
    message = str(_run(monkeypatch, "serve").code)
    assert "config.example.yaml" in message
    assert "Traceback" not in message


def test_malformed_config_explains_itself(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("backends: [oops\n")
    assert "hy3dforge:" in str(_run(monkeypatch, "serve").code)


def test_unservable_config_explains_itself(monkeypatch, tmp_path):
    # Valid YAML, invalid settings: gpu_total_gib must be a number.
    (tmp_path / "config.yaml").write_text("gpu_total_gib: plenty\n")
    assert "hy3dforge:" in str(_run(monkeypatch, "serve").code)


def test_open_port_without_keys_is_refused(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("host: 0.0.0.0\nbackends: []\n")
    message = str(_run(monkeypatch, "serve").code)
    assert "api_keys" in message
