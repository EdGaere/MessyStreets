#!/usr/bin/env python3
"""Audit the vendored tree: is everything there needed, and is everything needed there?

Demand-driven vendoring — copying a module the first time something fails to
import — tends to pull in a whole file to reach one helper, and tends to leave
modules behind when a verb is rewritten. Neither shows up in any test: an
unused module imports fine, and a missing one only fails on the code path that
wants it.

So the closure is recomputed from the artefact's own entry points and compared
with what is actually in src/. Reported, not enforced: a module can be legitimately
present without being statically reachable, and this says which.

Usage:
    python3 tools/audit.py [--json]
"""

from argparse import ArgumentParser
from ast import Import, ImportFrom, parse, walk
from json import dumps
from pathlib import Path
from sys import exit

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

# Everything the CLI can reach. Models are loaded by file path at runtime, so
# they are named explicitly rather than discovered.
ENTRY_POINTS = [
    "phd.tables.build_table",
    "phd.tables.error_bars",
    "phd.experiments.run_experiment",
    "phd.benchmarks.create_benchmark",
    "phd.datasets.address.messy_streets.v0.generators.v2",
    "phd.datasets.address.messy_streets.v0.generators.v3",
    "serentec.utils.strings.dominant_script",
] + [f"phd.models.models.{name}.model" for name in (
    "arcgis", "azure_maps", "geoapify", "here", "mapbox", "nominatim",
    "opencage", "openmapquest", "pelias", "photon", "tomtom")]

# google-geocoding has a hyphen, so it is not a dotted module path; it is
# loaded by file path at runtime like the others and audited as a file.
EXTRA_FILES = ["phd/models/models/google-geocoding/model.py"]


def module_path(module: str) -> Path | None:
    parts = module.split(".")
    package = SRC.joinpath(*parts) / "__init__.py"
    if package.is_file():
        return package
    single = SRC.joinpath(*parts).with_suffix(".py")
    return single if single.is_file() else None


def closure() -> tuple[set[Path], set[str]]:
    reached, missing, stack = set(), set(), list(ENTRY_POINTS)
    for extra in EXTRA_FILES:
        path = SRC / extra
        if path.is_file():
            reached.add(path)
            stack.extend(_imports(path))
        else:
            missing.add(extra)

    while stack:
        module = stack.pop()
        path = module_path(module)
        if path is None:
            # Could be an attribute imported from a module, not a module.
            parent = ".".join(module.split(".")[:-1])
            if parent and module_path(parent) is None and parent.split(".")[0] in ("phd", "serentec"):
                missing.add(module)
            continue
        if path in reached:
            continue
        reached.add(path)
        stack.extend(_imports(path))
    return reached, missing


def _imports(path: Path) -> list[str]:
    found = []
    try:
        tree = parse(path.read_text(encoding="utf8", errors="replace"))
    except SyntaxError:
        return found
    for node in walk(tree):
        if isinstance(node, Import):
            found += [a.name for a in node.names if a.name.split(".")[0] in ("phd", "serentec")]
        elif isinstance(node, ImportFrom) and node.module and not node.level:
            if node.module.split(".")[0] in ("phd", "serentec"):
                found.append(node.module)
                found += [f"{node.module}.{a.name}" for a in node.names]
    return found


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    reached, missing = closure()
    present = {p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts}
    unreachable = sorted(str(p.relative_to(SRC)) for p in present - reached)
    # __init__.py files exist to make packages importable, not to be reached.
    unreachable = [u for u in unreachable if not u.endswith("__init__.py")]

    report = {
        "modules_in_src": len(present),
        "statically_reachable": len(reached),
        "unreachable": unreachable,
        "missing": sorted(missing),
    }

    if args.json:
        print(dumps(report, indent=2))
    else:
        packages = sum(1 for path in present if path.name == "__init__.py")
        print(f"\nVendored tree audit\n")
        print(f"  {report['modules_in_src']} modules in src/ — "
              f"{report['statically_reachable']} reachable from the entry points, "
              f"{packages} package markers")
        if unreachable:
            print(f"\n  {len(unreachable)} not statically reachable:")
            for item in unreachable:
                print(f"    {item}")
        if missing:
            print(f"\n  {len(missing)} referenced but absent:")
            for item in missing:
                print(f"    {item}")
        if not unreachable and not missing:
            print("\n  every vendored module is reachable, and nothing reachable is absent.")

    return 1 if missing else 0


if __name__ == "__main__":
    exit(main())
