#!/usr/bin/env python3
"""Rebuild the shipped tier databases containing only the `addresses` table.

The databases as they exist in the research tree carry four more tables:

    discarded      every candidate the construction pipeline rejected, with the
                   reason -- including 180 records rejected by the PII judge
    backup         a pre-repair snapshot of the tier
    deleted        records the disjointness repair removed
    replacements   records it inserted

`discarded` is the one that matters. The paper states that a third LLM judge
filters personally identifiable information out of each of the six address
fields, rejecting about 0.4% of records. Shipping the database as-is would
publish exactly the records that filter removed, alongside the reason each was
flagged. The other three are surgery artefacts that also hold removed records.

Nothing in the artefact reads any of them; `messy-streets sample` and the
stage-9 repair script both query `addresses` only. So they are dropped rather
than redacted -- there is no reason for them to leave the research machine.

Usage:
    python3 tools/strip_tiers.py --source /path/to/original/databases
"""

from argparse import ArgumentParser
from pathlib import Path
from shutil import move
from sys import exit, stderr
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
TIERS = ["hq_10000", "mq_10000", "lq_10000"]
KEEP = "addresses"


def strip(source: Path, target: Path) -> dict:
    from duckdb import connect

    reader = connect(str(source), read_only=True)
    before = [row[0] for row in reader.execute("SHOW TABLES").fetchall()]
    rows = reader.execute(f"SELECT COUNT(*) FROM {KEEP}").fetchone()[0]

    sensitive = 0
    if "discarded" in before:
        sensitive = reader.execute(
            "SELECT COUNT(*) FROM discarded WHERE reason LIKE 'pid_%'").fetchone()[0]

    writer = connect(str(target))
    writer.execute(f"ATTACH '{source}' AS original (READ_ONLY)")
    writer.execute(f"CREATE TABLE {KEEP} AS SELECT * FROM original.{KEEP}")
    writer.execute("DETACH original")
    after = [row[0] for row in writer.execute("SHOW TABLES").fetchall()]
    kept_rows = writer.execute(f"SELECT COUNT(*) FROM {KEEP}").fetchone()[0]
    writer.close()

    if after != [KEEP] or kept_rows != rows:
        raise SystemExit(f"strip: {source.name} did not rebuild cleanly "
                         f"({after}, {kept_rows} of {rows} rows)")

    return {"dropped": [t for t in before if t != KEEP], "rows": rows,
            "pii_records_removed": sensitive}


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path,
                        help="directory holding the original tier databases")
    args = parser.parse_args()

    destination = ROOT / "data/tiers_duckdb"
    total_pii = 0

    with TemporaryDirectory(prefix="ms-strip-") as scratch:
        for tier in TIERS:
            source = args.source / tier
            if not source.is_file():
                print(f"strip: missing {source}", file=stderr)
                return 2
            staged = Path(scratch) / tier
            result = strip(source, staged)
            total_pii += result["pii_records_removed"]
            move(str(staged), str(destination / tier))
            print(f"  {tier}: kept {result['rows']:,} addresses; dropped "
                  f"{', '.join(result['dropped'])} "
                  f"({result['pii_records_removed']} PII-flagged records)")

    print(f"\n{total_pii} records flagged by the PII judge are no longer in the "
          f"shipped databases.")
    return 0


if __name__ == "__main__":
    exit(main())
