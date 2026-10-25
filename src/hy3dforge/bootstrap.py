"""`hy3dforge setup`: clone and install the backends declared in config.yaml.

The config doubles as a manifest. Each backend names a repository and a ref, so a checkout
is reproducible the way a submodule would be, without the detached-HEAD workflow that makes
submodules awkward to develop in - these repositories are forks you push branches from.

Existing checkouts are never modified. If `repo_path` is already a directory, setup reports
its current ref and leaves it alone.

Cloning a backend is the one moment this project fetches someone else's model code on a
user's behalf, so it is also the moment their licence has to be shown and acknowledged.
Nothing here sublicenses those weights - whoever runs a backend is that licence's licensee,
not this project - and `hy3dforge setup` refuses to clone until the person installing it has
said so explicitly.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
import sys
from typing import Iterable, List, Optional

from .config import BackendConfig, Settings

logger = logging.getLogger(__name__)


class SetupError(RuntimeError):
    pass


def _run(command: List[str], cwd: Optional[Path] = None) -> str:
    """Run a command, surfacing its output when it fails."""
    result = subprocess.run(
        command, cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    if result.returncode != 0:
        raise SetupError(
            f"{' '.join(command)} failed ({result.returncode}):\n{result.stdout[-4000:]}"
        )
    return result.stdout


def current_ref(repo: Path) -> str:
    """Describe what a checkout is on, for reporting."""
    try:
        branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo).strip()
        commit = _run(["git", "rev-parse", "--short", "HEAD"], repo).strip()
        return f"{branch}@{commit}"
    except SetupError:
        return "not a git checkout"


def license_notice(backend: BackendConfig) -> str:
    """The text shown before a backend is cloned."""
    lines = [f"{backend.name}: {backend.label or backend.name} is distributed by a third "
             f"party under its own licence."]
    if backend.license:
        lines.append(f"  licence: {backend.license}")
    if backend.license_url:
        lines.append(f"  terms:   {backend.license_url}")
    for note in backend.license_notes:
        lines.append(f"  - {note}")
    lines.append("  Installing it makes you that licence's licensee. hy3dforge grants you "
                 "nothing in respect of it.")
    return "\n".join(lines)


def acknowledge_license(backend: BackendConfig, assume_yes: bool = False) -> None:
    """Show the backend's licence and require the installer to accept it.

    Raises SetupError rather than prompting when there is nobody to prompt - a scripted or
    CI install has to pass --accept-licenses, which keeps the acceptance an explicit act
    instead of something a pipeline does by not noticing.
    """
    if not (backend.license or backend.license_url or backend.license_notes):
        return

    print(license_notice(backend), flush=True)
    if assume_yes:
        print(f"  accepted for {backend.name} via --accept-licenses", flush=True)
        return
    if not sys.stdin.isatty():
        raise SetupError(
            f"{backend.name}: its licence has to be accepted before it can be installed. "
            f"Re-run with --accept-licenses, having read {backend.license_url or 'its terms'}."
        )

    answer = input(f"  Type 'accept' to install {backend.name}, anything else to skip: ")
    if answer.strip().lower() != "accept":
        raise SetupError(f"{backend.name}: licence not accepted, nothing was installed")


def clone_backend(backend: BackendConfig, assume_yes: bool = False) -> bool:
    """Clone the backend if its directory is missing. Returns True if a clone happened."""
    if backend.repo_path.exists():
        # Already obtained by whoever put it there; this is not our fetch to gate.
        logger.info("%s: already present at %s (%s)",
                    backend.name, backend.repo_path, current_ref(backend.repo_path))
        return False
    if not backend.repo_url:
        raise SetupError(
            f"{backend.name}: {backend.repo_path} is missing and no repo_url is configured"
        )

    acknowledge_license(backend, assume_yes)

    logger.info("%s: cloning %s @ %s", backend.name, backend.repo_url, backend.repo_ref)
    backend.repo_path.parent.mkdir(parents=True, exist_ok=True)
    # Not a shallow clone: these are forks you will branch and push from, and GitHub
    # rejects pushes made from a shallow checkout.
    _run(["git", "clone", "--branch", backend.repo_ref,
          backend.repo_url, str(backend.repo_path)])
    return True


def install_backend(backend: BackendConfig) -> bool:
    """Run the backend's own installer unless its virtualenv already exists."""
    if backend.python.exists():
        logger.info("%s: virtualenv already built (%s)", backend.name, backend.python)
        return False

    script = backend.repo_path / backend.install_script
    if not script.exists():
        raise SetupError(
            f"{backend.name}: no installer at {script}. Build the virtualenv by hand so that "
            f"{backend.python} exists, then run setup again."
        )
    logger.info("%s: running %s (this downloads several GB and takes a while)",
                backend.name, backend.install_script)
    _run(["bash", str(script)], cwd=backend.repo_path)
    return True


def verify_backend(backend: BackendConfig) -> None:
    """Confirm the pieces the router will actually use are in place."""
    missing = [str(p) for p in (backend.python, backend.worker) if not p.exists()]
    if missing:
        raise SetupError(f"{backend.name}: missing after setup: {', '.join(missing)}")


def setup(settings: Settings, only: Optional[Iterable[str]] = None,
          accept_licenses: bool = False) -> int:
    """Clone, install and verify each selected backend. Returns a process exit code."""
    wanted = set(only) if only else None
    selected = [b for b in settings.backends if wanted is None or b.name in wanted]
    if wanted:
        unknown = wanted - {b.name for b in settings.backends}
        if unknown:
            logger.error("unknown backend(s): %s", ", ".join(sorted(unknown)))
            return 2
    if not selected:
        logger.error("no backends selected")
        return 2

    failures = []
    for backend in selected:
        logger.info("--- %s ---", backend.name)
        try:
            clone_backend(backend, accept_licenses)
            install_backend(backend)
            verify_backend(backend)
            logger.info("%s: ready (%s)", backend.name, current_ref(backend.repo_path))
        except SetupError as error:
            logger.error("%s", error)
            failures.append(backend.name)

    if failures:
        logger.error("setup failed for: %s", ", ".join(failures))
        return 1
    logger.info("all selected backends ready; start the service with: hy3dforge serve")
    return 0
