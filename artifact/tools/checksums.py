#!/usr/bin/env python3
"""Generate data/CHECKSUMS.sha256 over everything `doctor` should verify.

Paths are relative to the repository root, so the manifest covers the shipped
results and benchmarks under src/ as well as the expected-value references
under data/. Vendored *code* is excluded: it is covered by VENDOR.md, which
records the hash of each source file before scrubbing.
"""

from hashlib import sha256
from pathlib import Path
from sys import exit

ROOT = Path(__file__).resolve().parent.parent

# Data the artefact's claims rest on. Code is deliberately not included.
INCLUDE = [
    "data/expected/**/*.json",
    "data/tiers/*.jsonl.gz",
    "data/tiers_duckdb/*",
    "data/pipeline/*.json",
    "croissant.json",
    "src/phd/benchmarks/**/*",
    "src/phd/experiments/**/*",
    "src/phd/tables/**/*.hjson",
]

EXCLUDE_NAMES = {".gitkeep", ".DS_Store"}
EXCLUDE_PARTS = {"__pycache__"}


def collect() -> list[Path]:
    found: set[Path] = set()
    for pattern in INCLUDE:
        for path in ROOT.glob(pattern):
            if not path.is_file():
                continue
            if path.name in EXCLUDE_NAMES or EXCLUDE_PARTS & set(path.parts):
                continue
            found.add(path)
    return sorted(found)


def main() -> int:
    files = collect()
    if not files:
        print("checksums: nothing matched; refusing to write an empty manifest")
        return 2

    lines = [
        "# sha256 of the data the artefact's claims rest on.",
        "# Paths are relative to the repository root. Regenerate with:",
        "#   python3 tools/checksums.py",
        f"# {len(files)} files",
    ]
    for path in files:
        digest = sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(ROOT)}")

    target = ROOT / "data" / "CHECKSUMS.sha256"
    target.write_text("\n".join(lines) + "\n", encoding="utf8")
    print(f"wrote {target.relative_to(ROOT)} — {len(files)} files")
    return 0


if __name__ == "__main__":
    exit(main())
