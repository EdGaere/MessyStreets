"""Environment and integrity checks.

Two halves, deliberately. The *bootstrap* half — is there a container runtime,
did the image resolve, is the mount writable — cannot run here at all: if the
container never started, nothing inside it can say so. That half lives in the
./messy-streets wrapper, on the host.

What runs here is the *integrity* half: is this the environment the paper was
produced in, is the shipped data intact, and which reproducibility layers are
actually available on this machine. It grows as each slice adds something worth
checking; at slice 1 there is no data yet and it says so rather than pretending.

Stdlib only, on purpose: a doctor that imports pandas cannot diagnose a missing
pandas.
"""

from hashlib import sha256
from importlib import metadata
from importlib.util import find_spec
from os import environ
from platform import machine, python_version
from typing import Dict, List, NamedTuple, Optional

from messy_streets import DATA_REVISION, __version__, paths, verbs

OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"

# Distribution name -> module name, where they differ.
MODULE_NAMES = {
    "python-geohash": "geohash",
    "scikit-learn": "sklearn",
}

# Environment variables the container sets to keep runs comparable. Outside the
# container they are usually unset, which is a warning rather than a failure.
EXPECTED_ENV = {
    "TZ": "UTC",
    "LANG": "C.UTF-8",
    "PYTHONHASHSEED": "0",
    "MS_DUCKDB_THREADS": "1",
}


class Check(NamedTuple):
    group: str
    name: str
    status: str
    detail: str

    @property
    def failed(self) -> bool:
        return self.status == FAIL


def _pins() -> Dict[str, str]:
    """Parse requirements.txt into {distribution: version}."""
    pins: Dict[str, str] = {}
    path = paths.requirements()
    if not path.is_file():
        return pins
    for line in path.read_text(encoding="utf8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, version = line.split("==", 1)
        pins[name.strip()] = version.strip()
    return pins


def check_interpreter() -> List[Check]:
    version = python_version()
    major_minor = ".".join(version.split(".")[:2])
    status = OK if major_minor == "3.12" else WARN
    detail = version if status == OK else f"{version} (paper used 3.12.3)"
    return [
        Check("interpreter", "python", status, detail),
        Check("interpreter", "architecture", OK, machine()),
        Check("interpreter", "artefact", OK, f"v{__version__}, data revision {DATA_REVISION}"),
    ]


def check_environment() -> List[Check]:
    checks = []
    for key, expected in EXPECTED_ENV.items():
        actual = environ.get(key)
        if actual == expected:
            checks.append(Check("environment", key, OK, actual))
        elif actual is None:
            checks.append(Check("environment", key, WARN, f"unset (container sets {expected})"))
        else:
            checks.append(Check("environment", key, WARN, f"{actual!r}, expected {expected!r}"))
    return checks


def check_layout() -> List[Check]:
    checks = []
    for label, path in (("root", paths.root()), ("src", paths.src()), ("data", paths.data())):
        if not path.is_dir():
            checks.append(Check("layout", label, FAIL, f"missing: {path}"))
            continue
        entries = [p for p in path.iterdir() if p.name not in (".gitkeep",)]
        if entries:
            checks.append(Check("layout", label, OK, f"{len(entries)} entries"))
        else:
            checks.append(Check("layout", label, SKIP, "empty (populated by a later slice)"))
    return checks


def check_dependencies() -> List[Check]:
    pins = _pins()
    if not pins:
        return [Check("dependencies", "requirements.txt", FAIL, f"not found at {paths.requirements()}")]

    checks = []
    for dist, pinned in sorted(pins.items(), key=lambda kv: kv[0].lower()):
        module = MODULE_NAMES.get(dist, dist.replace("-", "_"))
        try:
            installed = metadata.version(dist)
        except metadata.PackageNotFoundError:
            checks.append(Check("dependencies", dist, FAIL, f"not installed (need {pinned})"))
            continue
        if installed != pinned:
            checks.append(Check("dependencies", dist, FAIL, f"{installed}, pinned {pinned}"))
            continue
        try:
            found = find_spec(module) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            checks.append(Check("dependencies", dist, FAIL, f"{installed} installed but '{module}' not importable"))
        else:
            checks.append(Check("dependencies", dist, OK, installed))
    return checks


def check_data() -> List[Check]:
    manifest = paths.data() / "CHECKSUMS.sha256"
    if not manifest.is_file():
        return [Check("data", "checksums", SKIP, "no manifest found")]

    ok = bad = missing = 0
    first_problem: Optional[str] = None
    for line in manifest.read_text(encoding="utf8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        expected, _, relative = line.partition("  ")
        # Paths are repository-root relative: the manifest covers the shipped
        # results under src/ as well as the references under data/.
        target = paths.root() / relative.strip()
        if not target.is_file():
            missing += 1
            first_problem = first_problem or f"missing {relative.strip()}"
            continue
        digest = sha256()
        with target.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        if digest.hexdigest() == expected:
            ok += 1
        else:
            bad += 1
            first_problem = first_problem or f"modified {relative.strip()}"

    total = ok + bad + missing
    if bad or missing:
        return [Check("data", "checksums", FAIL,
                      f"{ok}/{total} verified — {first_problem}")]
    return [Check("data", "checksums", OK, f"{ok}/{total} verified")]


def check_layers() -> List[Check]:
    """Which reproducibility layers can actually run on this machine."""
    checks = []
    for verb in verbs.load().values():
        if verb.layer == "-":
            continue
        if not verb.implemented:
            checks.append(Check("layers", f"{verb.layer} {verb.name}", SKIP,
                                f"not built yet (slice {verb.slice})"))
        else:
            checks.append(Check("layers", f"{verb.layer} {verb.name}", OK, "available"))
    return checks


def run() -> List[Check]:
    checks: List[Check] = []
    for group in (check_interpreter, check_environment, check_layout,
                  check_dependencies, check_data, check_layers):
        checks.extend(group())
    return checks
