"""https://nox.thea.codes/en/stable/ sessions."""

from __future__ import annotations

import shutil
import tomllib

from typing import TYPE_CHECKING
from pathlib import Path

import nox

if TYPE_CHECKING:
    from nox import Session

nox.options.default_venv_backend = "uv"


def get_dependencies(*sections: str) -> list[str]:
    """Get list dependencies from sections optional-dependencies+common."""
    dependencies = []

    pyproject_path = Path("pyproject.toml")

    with pyproject_path.open("rb") as f:
        pyproject = tomllib.load(f)

    dependencies.extend(pyproject.get("project", {}).get("dependencies", []))

    for section in sections:
        optional_dependencies = pyproject.get("project", {}).get(
            "optional-dependencies", {}
        )
        dependencies.extend(optional_dependencies.get(section, []))

    return dependencies


@nox.session
def lint(session: Session) -> None:
    """Lint session: ruff format . + ruff ckeck ."""
    session.install(*get_dependencies("lint"))
    session.run("ruff", "format", ".")
    session.run("ruff", "check", ".")
    session.run("basedpyright", ".", success_codes=[0, 1])  # To use commit
    # session with errors


@nox.session
def clean(session: Session) -> None:
    """Clean all unnecessery files before commiting."""
    paths_to_remove = [
        Path(".nox"),
        Path(".ruff_cache"),
    ]

    pycache_dirs = list(Path().glob("**/__pycache__"))
    paths_to_remove.extend(pycache_dirs)

    for path in paths_to_remove:
        if path.exists() and path.is_dir():
            session.log(f"Removing {path}")
            shutil.rmtree(path)


@nox.session
def commit(session: Session) -> None:
    """Commit session: `nox -s lint` + `git add .` + `cz commit` + git push."""
    session.run("nox", "-s", "lint", external=True)
    session.run("nox", "-s", "clean", external=True)

    session.run("git", "add", ".", external=True)
    session.run("cz", "commit", external=True)
    session.run("git", "push", external=True)
