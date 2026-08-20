"""A disposable copy of the vendored tree to run in.

The pipeline writes its results back into its own inputs: results land beside
the cached predictions they were replayed from, and the sampler materialises a
table into the tier database on first use. Run it against the repository and a
`git status` fills with modified inputs; run it twice and the second run reads
what the first one wrote.

So every command runs in a copy and throws it away. The container entrypoint
does the same thing at a coarser grain, which means the property holds whether
the artefact is run in a container or not.
"""

from contextlib import contextmanager
from shutil import copytree, ignore_patterns
from sys import path as sys_path
from tempfile import TemporaryDirectory
from os import environ
from pathlib import Path
from typing import Iterator

from messy_streets import paths


@contextmanager
def vendored_tree() -> Iterator[Path]:
    """Yield a throwaway copy of src/, with the environment pointed at it.

    The vendored closure resolves experiment, benchmark and table locations
    from PYTHONPATH at runtime, exactly as it did in the tree that produced the
    paper. Repointing it here keeps that code identical to what ran.
    """
    with TemporaryDirectory(prefix="messy-streets-run-") as scratch:
        work = Path(scratch) / "src"
        copytree(paths.src(), work, ignore=ignore_patterns("__pycache__", "*.pyc"))

        previous = {key: environ.get(key) for key in ("PYTHONPATH", "MS_CACHE_DIR")}
        environ["PYTHONPATH"] = str(work)
        # A per-run cache, so a replay can never answer from a previous run.
        environ["MS_CACHE_DIR"] = str(Path(scratch) / "cache")
        # PYTHONPATH is read by the vendored code at runtime; sys.path is what
        # actually imports it. Both have to point at the copy.
        sys_path.insert(0, str(work))
        try:
            yield work
        finally:
            if str(work) in sys_path:
                sys_path.remove(str(work))
            for key, value in previous.items():
                if value is None:
                    environ.pop(key, None)
                else:
                    environ[key] = value
