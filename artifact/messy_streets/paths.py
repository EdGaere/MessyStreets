"""Filesystem layout of the artefact.

Everything is resolved from MS_ROOT, which defaults to the repository that
contains this package. Inside the container the entrypoint sets MS_ROOT to a
writable copy of the tree, because the pipeline writes results back into its
own inputs (see ARTIFACT.md, "Why the data is copied").
"""

from os import environ
from pathlib import Path


def root() -> Path:
    """Repository root, or the writable working copy inside the container."""
    override = environ.get("MS_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parent.parent


def src() -> Path:
    """Vendored dependency closure; this is what PYTHONPATH must point at."""
    return root() / "src"


def data() -> Path:
    return root() / "data"


def out() -> Path:
    """Where every command writes. Nothing is written outside it."""
    return Path(environ.get("MS_OUT", root() / "out")).resolve()


def requirements() -> Path:
    return root() / "requirements.txt"


def verbs_file() -> Path:
    return Path(__file__).resolve().parent / "verbs.tsv"
