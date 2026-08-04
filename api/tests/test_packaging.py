"""The dependency list exists twice, so this checks the two copies agree.

`requirements.txt` is what the Dockerfile installs. `pyproject.toml` is what
Vercel installs -- its Python builder treats any pyproject.toml as a uv project
and runs `uv lock`, which fails outright without a `[project]` table. Neither
file can be dropped, so the risk is drift: a dependency added for local work,
the deploy still building against the old set, and the failure only appearing in
production.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

API = Path(__file__).resolve().parents[1]


def read_requirements(name: str) -> set[str]:
    lines = (API / name).read_text(encoding="utf-8").splitlines()
    return {
        line.strip()
        for line in lines
        if line.strip() and not line.startswith(("#", "-"))
    }


def pyproject() -> dict:
    return tomllib.loads((API / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_runtime_dependencies_match():
    assert set(pyproject()["project"]["dependencies"]) == read_requirements("requirements.txt")


def test_the_dev_dependencies_match():
    declared = set(pyproject()["project"]["optional-dependencies"]["dev"])

    assert declared == read_requirements("requirements-dev.txt")


def test_it_is_declared_as_an_application_not_a_library():
    """Without this uv tries to build a wheel from a project that has no build
    backend and no package layout, and the deploy fails at install time."""
    assert pyproject()["tool"]["uv"]["package"] is False


def test_the_python_version_is_pinned_at_or_above_the_runtime():
    """`api/vercel.json` asks for python3.12. Requiring anything newer here
    would resolve locally and fail on the deploy."""
    assert pyproject()["project"]["requires-python"] == ">=3.12"
