#!/usr/bin/env python3
"""Copy the dependency closure out of the source tree into src/.

Vendoring rather than symlinking is deliberate: it forces the dependency set to
be finite and explicit, and it means the artefact cannot silently start
depending on something new in the source tree.

Two things happen on the way in:

  * Credentials are stripped. Several modules carry live API keys in their
    module docstrings — usage notes that were never meant to leave the machine.
    Nothing imports them, so removal is safe, but it must be mechanical rather
    than remembered.

  * Provenance is recorded. VENDOR.md lists every file, where it came from and
    what its content hash was, so the vendored copy can be diffed against the
    tree that produced the paper.

Usage:
    python3 tools/vendor.py --source /local/home/gaeree/phd [--check]
"""

from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from re import compile as re_compile
from shutil import copy2
from sys import exit, path as sys_path, stderr

sys_path.insert(0, str(Path(__file__).resolve().parent))
from config_stub import STUB as CONFIG_STUB
from patches import PATCHES

# Modules replaced wholesale rather than copied. See the stub for why.
REPLACEMENTS = {"serentec/config.py": CONFIG_STUB}

# Modules the closure needs, relative to the source tree root. Grouped by the
# slice that first required them, so the list stays auditable as it grows.
MODULES = {
    "slices 2-3 — smoke and tables: rebuild the paper's tables from cached predictions": [
        "phd/__init__.py",
        "phd/experiments/__init__.py",
        "phd/experiments/config.py",
        "phd/experiments/run_experiment.py",
        "phd/experiments/run_experiment_batch.py",
        "phd/models/__init__.py",
        "phd/models/load_model.py",
        "phd/models/model_base.py",
        "phd/tables/build_table.py",
        "phd/tables/error_bars.py",
        "serentec/__init__.py",
        "serentec/exceptions.py",
        "serentec/ingestion/__init__.py",
        "serentec/ingestion/load_benchmark.py",
        "serentec/ml/__init__.py",
        "serentec/ml/config.py",
        "serentec/ml/llm/__init__.py",
        "serentec/ml/llm/prompts.py",
        "serentec/ml/llm/responses.py",
        "serentec/utils/__init__.py",
        "serentec/utils/check_isinstance.py",
        "serentec/utils/comparator.py",
        "serentec/utils/exception_info.py",
        "serentec/utils/file/__init__.py",
        "serentec/utils/file/check_isfile.py",
        "serentec/utils/interpreters/__init__.py",
        "serentec/utils/interpreters/python_interpreter.py",
        "serentec/utils/json/__init__.py",
        "serentec/utils/json/load_json.py",
        "serentec/utils/logger.py",
        "serentec/utils/optional_abstractmethod.py",
        "serentec/utils/parse_function_args.py",
        "serentec/utils/timeout.py",
    ],
    "slice 4 — stats and inspect: dataset-level figures from the released tiers": [
        "serentec/utils/strings/__init__.py",
        "serentec/utils/strings/dominant_script.py",
    ],
    "slice 7 — geocode: the twelve geocoder wrappers": [
        "phd/models/models/__init__.py",
        "phd/models/models/arcgis/model.py",
        "phd/models/models/azure_maps/model.py",
        "phd/models/models/geoapify/model.py",
        "phd/models/models/google-geocoding/model.py",
        "phd/models/models/here/model.py",
        "phd/models/models/mapbox/model.py",
        "phd/models/models/nominatim/model.py",
        "phd/models/models/opencage/model.py",
        "phd/models/models/openmapquest/model.py",
        "phd/models/models/pelias/model.py",
        "phd/models/models/photon/model.py",
        "phd/models/models/tomtom/model.py",
        "serentec/backend/__init__.py",
        "serentec/backend/cache/__init__.py",
        "serentec/backend/cache/disk_cache/__init__.py",
        "serentec/backend/cache/disk_cache/adisk_cache.py",
        "serentec/backend/cache/disk_cache/disk_cache.py",
    ],
    "slice 5 — sample: regenerate the benchmark slices from the tier databases": [
        "phd/benchmarks/__init__.py",
        "phd/benchmarks/create_benchmark.py",
        "phd/datasets/__init__.py",
        "phd/datasets/address/__init__.py",
        "phd/datasets/address/messy_streets/v0/generators/v2.py",
        "phd/datasets/address/messy_streets/v0/generators/v3.py",
        "serentec/config.py",
        "serentec/ml/generators/__init__.py",
        "serentec/ml/generators/load_generator.py",
        "serentec/ml/generators/load_generators.py",
        "serentec/ml/training_pair.py",
        "serentec/utils/analysis/descriptive_stats.py",
        "serentec/utils/analysis/histogram.py",
        "serentec/utils/strings/insert_noise.py",
        "serentec/utils/strings/lexical_similarity.py",
    ],
}

# Packages that exist in the source tree without an __init__.py; the artefact
# adds one so the closure imports cleanly.
NAMESPACE_PACKAGES = [
    "phd/tables",
    "phd/datasets/address/messy_streets",
    "phd/datasets/address/messy_streets/v0",
    "phd/datasets/address/messy_streets/v0/generators",
    "serentec/utils/analysis",
]

# Lines matching any of these are removed on the way in. They are all inside
# module docstrings — setup notes that pasted real credentials.
SECRET_PATTERNS = [
    re_compile(r"^\s*export\s+[A-Z0-9_]*(API_KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*\s*="),
    re_compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re_compile(r"r8_[A-Za-z0-9]{20,}"),
    re_compile(r"AIza[A-Za-z0-9_-]{20,}"),
    re_compile(r"pk\.eyJ[A-Za-z0-9._-]{20,}"),
    re_compile(r"\bge-[a-f0-9]{16}\b"),
    # Dict-style entries, e.g.  "pwd" : "hunter2"  — the export-line pattern
    # above does not see these, and serentec/config.py carries one.
    re_compile(r"""["']?(pwd|password|passwd|secret|api_key|token)["']?\s*[:=]\s*["'][^"']{6,}["']""",
               2),  # re.IGNORECASE
]

REDACTION = ("# [credential removed when vendoring; supply your own via the "
             "environment — see README]")


def scrub(text: str) -> tuple[str, int]:
    """Drop credential-bearing lines, leaving one marker where they were."""
    out, removed, marked = [], 0, False
    for line in text.splitlines(keepends=True):
        if any(pattern.search(line) for pattern in SECRET_PATTERNS):
            removed += 1
            if not marked:
                out.append(REDACTION + "\n")
                marked = True
            continue
        marked = False
        out.append(line)
    return "".join(out), removed


def apply_patches(relative: str, text: str) -> tuple[str, int]:
    """Apply every patch registered for this module, failing loudly on drift."""
    applied = 0
    for patch in PATCHES:
        if patch.module != relative:
            continue
        occurrences = text.count(patch.old)
        if occurrences != 1:
            raise SystemExit(
                f"vendor: patch does not apply cleanly to {relative}\n"
                f"  {patch.title}\n"
                f"  expected the anchor text exactly once, found {occurrences}.\n"
                f"  The source has changed; update tools/patches.py."
            )
        if patch.until:
            start = text.index(patch.old)
            stop = text.index(patch.until, start + len(patch.old))
            if stop < 0:
                raise SystemExit(f"vendor: closing anchor not found for {patch.title}")
            text = text[:start] + patch.new + text[stop + len(patch.until):]
        else:
            text = text.replace(patch.old, patch.new)
        applied += 1
    return text, applied


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path,
                        help="root of the source tree (contains phd/ and serentec/)")
    parser.add_argument("--dest", type=Path, default=Path(__file__).resolve().parent.parent / "src")
    parser.add_argument("--check", action="store_true",
                        help="report drift against the source tree; copy nothing")
    args = parser.parse_args()

    if not (args.source / "phd").is_dir():
        print(f"vendor: {args.source} does not look like the source tree", file=stderr)
        return 2

    manifest, total_removed, total_patched, drift = [], 0, 0, []

    for group, modules in MODULES.items():
        for relative in modules:
            source = args.source / relative
            target = args.dest / relative
            if not source.is_file():
                print(f"vendor: missing in source tree: {relative}", file=stderr)
                return 2

            # Patches anchor on the original source, so they run first; the
            # scrubber is the last net, and catches anything a patch missed.
            if relative in REPLACEMENTS:
                text = REPLACEMENTS[relative]
            else:
                text = source.read_text(encoding="utf8")
            patched, applied = apply_patches(relative, text)
            total_patched += applied
            cleaned, removed = scrub(patched)
            total_removed += removed

            if args.check:
                if not target.is_file():
                    drift.append(f"absent from src/: {relative}")
                elif target.read_text(encoding="utf8") != cleaned:
                    drift.append(f"differs from source: {relative}")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(cleaned, encoding="utf8")

            manifest.append((relative, digest(source), removed, group))

    if args.check:
        for item in drift:
            print(f"  {item}")
        print(f"{len(drift)} file(s) drifted" if drift else "vendored tree matches the source")
        return 1 if drift else 0

    for package in NAMESPACE_PACKAGES:
        init = args.dest / package / "__init__.py"
        init.parent.mkdir(parents=True, exist_ok=True)
        if not init.is_file():
            init.write_text("# Added when vendoring; absent from the source tree.\n", encoding="utf8")

    lines = [
        "# Vendored dependency closure",
        "",
        "Copied from the source tree by `tools/vendor.py`. Do not edit in place:",
        "change the source and re-run, or the two silently diverge.",
        "",
        "`python3 tools/vendor.py --source <tree> --check` reports drift.",
        "",
        "Hashes are of the **source** file before credential scrubbing, so a",
        "vendored copy can be traced back to the exact bytes that produced the",
        "paper.",
        "",
    ]
    for group in MODULES:
        lines += [f"## {group}", "",
                  "| Module | Source sha256 | Lines scrubbed |",
                  "|--------|---------------|----------------|"]
        for relative, sha, removed, item_group in manifest:
            if item_group == group:
                lines.append(f"| `{relative}` | `{sha[:16]}…` | {removed or ''} |")
        lines.append("")

    lines += ["## Patches applied", "",
              "Modifications to the vendored copy, defined in `tools/patches.py`.",
              "None change what the pipeline computes.", ""]
    for patch in PATCHES:
        lines += [f"### `{patch.module}` — {patch.title}", "", patch.why, ""]

    (args.dest.parent / "VENDOR.md").write_text("\n".join(lines) + "\n", encoding="utf8")

    print(f"vendored {len(manifest)} modules into {args.dest}")
    print(f"scrubbed {total_removed} credential line(s)")
    print(f"applied  {total_patched} patch(es); see VENDOR.md")
    return 0


if __name__ == "__main__":
    exit(main())
