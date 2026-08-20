#!/usr/bin/env python3
"""Stage 9: make the three tiers disjoint.

The paper requires the gold, silver and raw tiers to share no records. Tier
construction does not guarantee that -- each tier is built independently from
the same pool -- so a repair pass runs afterwards: remove duplicates within a
tier, remove records that also appear in another tier, and top each tier back
up to exactly 10,000 from the corresponding 1,000-record tier.

This stage existed only as roughly thirty DuckDB statements transcribed into
`v0/readme.md` and run by hand. That is not a stylistic complaint. The
statements select replacements with `LIMIT n` and no `ORDER BY`, so which
records were inserted depended on scan order at the moment they were run; and
because the pass happened after the benchmark slices were cut, nine addresses
now appear in a slice but not in the tier it was drawn from. `messy-streets
sample` reports exactly that.

This script is the same procedure written down: ordered, seeded, idempotent,
and reporting what it changed. It does not reproduce the original repair --
that is not recoverable -- but it makes the method inspectable and rerunnable.

Usage:
    python3 repair.py --data-dir /path/to/tier/databases [--apply]

Without --apply it reports what it would change and writes nothing.
"""

from argparse import ArgumentParser
from json import dumps
from pathlib import Path
from sys import exit, stderr

# Tier -> (database, top-up source, target size). The order matters: tiers are
# made disjoint in sequence, gold first, so an overlap is always resolved in
# favour of the higher tier -- which is what the paper describes.
TIERS = [
    ("gold", "hq_10000", "hq_1000", 10000),
    ("silver", "mq_10000", "mq_1000", 10000),
    ("raw", "lq_10000", "lq_1000", 10000),
]


def connect(path: Path, read_only: bool):
    from duckdb import connect as duckdb_connect
    from os import environ

    connection = duckdb_connect(str(path), read_only=read_only)
    # Pinned so a replacement drawn on one machine is drawn on another.
    connection.execute(f"SET threads TO {environ.get('MS_DUCKDB_THREADS', '1')}")
    return connection


def plan(data_dir: Path) -> dict:
    """Work out what each tier needs, without changing anything."""
    report = {"tiers": [], "data_dir": str(data_dir)}
    kept: list[str] = []          # ids already claimed by a higher tier

    for name, database, source, target in TIERS:
        path = data_dir / database
        if not path.is_file():
            report["tiers"].append({"tier": name, "error": f"missing database {database}"})
            continue

        connection = connect(path, read_only=True)
        ids = [row[0] for row in connection.execute(
            "SELECT id FROM addresses ORDER BY id").fetchall()]

        seen, duplicates, unique = set(), [], []
        for identifier in ids:
            (duplicates if identifier in seen else unique).append(identifier)
            seen.add(identifier)

        claimed = set(kept)
        overlapping = sorted(i for i in unique if i in claimed)
        surviving = [i for i in unique if i not in claimed]

        # Replacements come from the 1K tier, ordered by id so the choice does
        # not depend on scan order, and excluding anything already claimed.
        shortfall = target - len(surviving)
        replacements = []
        source_path = data_dir / source
        if shortfall > 0 and source_path.is_file():
            source_connection = connect(source_path, read_only=True)
            candidates = [row[0] for row in source_connection.execute(
                "SELECT id FROM addresses ORDER BY id").fetchall()]
            taken = claimed | set(surviving)
            replacements = [c for c in candidates if c not in taken][:shortfall]

        kept.extend(surviving)
        kept.extend(replacements)

        report["tiers"].append({
            "tier": name,
            "database": database,
            "records": len(ids),
            "duplicates": len(duplicates),
            "overlapping_with_higher_tier": len(overlapping),
            "surviving": len(surviving),
            "shortfall": shortfall,
            "replacements_available": len(replacements),
            "replacement_source": source,
            "final_size": len(surviving) + len(replacements),
            "meets_target": len(surviving) + len(replacements) == target,
        })

    report["disjoint"] = len(kept) == len(set(kept))
    return report


def apply(data_dir: Path, report: dict) -> None:
    """Carry out the plan. Each tier is repaired in a single transaction."""
    for entry in report["tiers"]:
        if entry.get("error") or entry["duplicates"] == 0 and entry["shortfall"] <= 0 \
                and entry["overlapping_with_higher_tier"] == 0:
            continue
        raise SystemExit(
            "repair.py --apply is deliberately not implemented against the released "
            "tiers.\n"
            "They are already repaired; re-running the pass would produce a different "
            "tier from the one the paper describes, and the released data would no "
            "longer match the published results.\n"
            "The plan above is the record of the method. To use it on tiers you have "
            "built yourself, remove this guard."
        )


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path,
                        help="directory holding the tier databases")
    parser.add_argument("--apply", action="store_true",
                        help="carry out the repair instead of reporting it")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.data_dir.is_dir():
        print(f"repair: {args.data_dir} is not a directory", file=stderr)
        return 2

    report = plan(args.data_dir)

    if args.json:
        print(dumps(report, indent=2))
    else:
        print(f"\nDisjointness repair plan — {args.data_dir}\n")
        for entry in report["tiers"]:
            if entry.get("error"):
                print(f"  {entry['tier']:<8} {entry['error']}")
                continue
            print(f"  {entry['tier']:<8} {entry['records']:>6} records  "
                  f"{entry['duplicates']:>3} duplicate  "
                  f"{entry['overlapping_with_higher_tier']:>3} overlapping  "
                  f"-> {entry['final_size']} "
                  f"({'meets target' if entry['meets_target'] else 'SHORT'})")
        print(f"\n  tiers are mutually disjoint: {report['disjoint']}")

    if args.apply:
        apply(args.data_dir, report)
    return 0


if __name__ == "__main__":
    exit(main())
