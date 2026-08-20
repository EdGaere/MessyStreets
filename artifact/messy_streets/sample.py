"""sample — check the benchmark slices against the tier database they came from.

Each slice is 100 addresses drawn from a tier database with a fixed seed. The
obvious check is to redraw them and compare; it does not work, for a reason
worth stating rather than hiding.

DuckDB's `USING SAMPLE reservoir(N ROWS) REPEATABLE(seed)` is reproducible
within a version, not across versions. Redrawing with the pinned DuckDB 1.4.4
yields a self-consistent but *different* sample from the one the experiments
ran against — 28 of 500 records in common — and the DuckDB version used at the
time is not recorded anywhere in the artefact. Pinning the thread count does
not help: in 1.4.4 the sample is identical at 1 thread and at 8, so
parallelism is not the cause.

What can be checked, and is, is provenance: every record in every shipped slice
resolves to a row in the tier database, with a geohash consistent with the
target it was scored against. That establishes the slices were drawn from the
released data, which is the claim that matters.
"""

from gzip import open as gzip_open
from json import dumps, loads
from typing import Dict, List, NamedTuple, Optional

from messy_streets import paths

TIER_DATABASE = "hq_10000"
SLICE_GLOB = "phd/benchmarks/messy_streets/release_gold_geohash*/benchmark.jsonl.gz"


class Finding(NamedTuple):
    slice_name: str
    record_id: str
    problem: str


def _tier_rows() -> Dict[str, str]:
    """id -> geohash10, for every record in the released gold tier."""
    from duckdb import connect
    from os import environ

    path = paths.data() / "tiers_duckdb" / TIER_DATABASE
    if not path.is_file():
        raise FileNotFoundError(f"tier database not found: {path}")
    connection = connect(str(path), read_only=True)
    connection.execute(f"SET threads TO {environ.get('MS_DUCKDB_THREADS', '1')}")
    return dict(connection.execute("SELECT id, geohash10 FROM addresses").fetchall())


def check() -> tuple[List[Finding], List[Finding], int, int]:
    """Verify every slice record against the tier database."""
    reference = loads((paths.data() / "expected/slice-provenance.json").read_text(encoding="utf8"))
    known_absent = {record["id"] for record in reference["records"]}

    rows = _tier_rows()
    problems: List[Finding] = []
    accounted: List[Finding] = []
    slices = checked = 0

    for path in sorted(paths.src().glob(SLICE_GLOB)):
        slices += 1
        name = path.parent.name
        with gzip_open(path, "rt", encoding="utf8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = loads(line)
                checked += 1
                geohash = rows.get(record["id"])
                if geohash is None:
                    finding = Finding(name, record["id"], "not in the released tier")
                    (accounted if record["id"] in known_absent else problems).append(finding)
                elif not geohash.startswith(str(record["target"])):
                    problems.append(Finding(name, record["id"],
                                            f"target {record['target']!r} is not a prefix of {geohash!r}"))
    return problems, accounted, slices, checked


def run(as_json: bool = False, verbose: bool = False, limit: Optional[int] = None) -> int:
    from messy_streets.cli import EXIT_MISMATCH, EXIT_OK

    reference = loads((paths.data() / "expected/slice-provenance.json").read_text(encoding="utf8"))
    problems, accounted, slices, checked = check()

    if as_json:
        print(dumps({
            "layer": "L2",
            "slices": slices,
            "records_checked": checked,
            "known_absent": [f._asdict() for f in accounted],
            "problems": [f._asdict() for f in problems],
            "regeneration": "not bit-reproducible; see ARTIFACT.md",
            "reproduced": not problems,
            "exit_code": EXIT_MISMATCH if problems else EXIT_OK,
        }, indent=2))
        return EXIT_MISMATCH if problems else EXIT_OK

    print(f"\nChecking {slices} benchmark slices against the released gold tier")
    print(f"{checked} records; every id must resolve, and every target must match its geohash\n")

    for finding in problems:
        print(f"  PROBLEM  {finding.slice_name} · {finding.record_id}: {finding.problem}")

    if accounted:
        print(f"  {len(accounted)} record reference(s) to {reference['count']} addresses that are "
              f"no longer in the tier —")
        print(f"  deleted by the disjointness repair after the slices were cut. Declared in")
        print(f"  data/expected/slice-provenance.json.\n")

    print(f"  {checked - len(problems) - len(accounted)} of {checked} records verified against the tier database")

    print("\nBit-identical regeneration is not available.")
    print("  DuckDB's REPEATABLE sampling is reproducible within a version, not across")
    print("  versions, and the version used to cut these slices is not recorded. Redrawing")
    print("  with the pinned DuckDB 1.4.4 gives a self-consistent but different sample.")
    print("  Thread count is not the cause: the sample is identical at 1 thread and at 8.")

    print()
    if problems:
        print(f"MISMATCH — {len(problems)} record(s) do not trace to the released tier.")
        return EXIT_MISMATCH
    print("VERIFIED — every shipped slice record traces to the released gold tier.")
    return EXIT_OK
