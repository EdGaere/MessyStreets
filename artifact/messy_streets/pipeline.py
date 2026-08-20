"""pipeline — read, and where possible check, the fifteen construction stages.

Most of the pipeline cannot be re-run: it needs the December 2024 Web Data
Commons corpus, 106 GB of reference databases and a 35B judge model on four
GPUs. Recording it is the point. Fifteen numbered stages, each with its code,
its inputs and outputs, its scale and what it would take, is a map of how a
web-scale geocoding benchmark actually gets built — useful to people who will
never run it.

Two stages can be checked here without any of that:

  Stage 3, the filter cascade, because its output statistics file is Table 2
  and is small enough to ship.

  Stage 9, the disjointness repair, because the property it exists to
  establish — three tiers sharing no records — can be tested directly on the
  tier databases.
"""

from json import dumps, loads
from pathlib import Path
from typing import Dict, List, Optional

from messy_streets import paths

# Table 2's rows, in the order the paper prints them, mapped to the keys the
# stage-3 statistics file uses.
TABLE2_ROWS = [
    ("Empty streetAddress", "Missing streetAddress"),
    ("Missing latitude", "Missing latitude"),
    ("Missing longitude", "Missing longitude"),
    ("Latitude/longitude out-of-range", "latitude/longitude out-of-range"),
    ("Latitude/longitude non-numeric", "latitude/longitude non-numeric"),
    ("Lexical duplicates", "Duplicate rows"),
    ("Unresolved component reference", "Unresolved streetAddress"),
]

# As printed in the paper.
TABLE2_PUBLISHED = {
    "Empty streetAddress": 2471365,
    "Missing latitude": 1013389,
    "Missing longitude": 23840,
    "Latitude/longitude out-of-range": 376614,
    "Latitude/longitude non-numeric": 0,
    "Lexical duplicates": 71505431,
    "Unresolved component reference": 2755292,
}
TABLE2_TOTAL_REMOVED = 78145931
TABLE2_RETAINED = 16868598


def stages() -> List[Dict]:
    return loads((paths.data() / "pipeline/stages.json").read_text(encoding="utf8"))["stages"]


def check_table2() -> Dict:
    """Stage 3's statistics file is Table 2. Check every cell against the paper."""
    stats = loads((paths.data() / "pipeline/wdc-filter-stats.json").read_text(encoding="utf8"))
    dropped = stats["dropped_reasons"]

    cells, mismatches = [], []
    for paper_label, stats_key in TABLE2_ROWS:
        recorded = dropped.get(stats_key)
        published = TABLE2_PUBLISHED[paper_label]
        cells.append({"row": paper_label, "published": published, "recorded": recorded})
        if recorded != published:
            mismatches.append(cells[-1])

    total = sum(dropped.values())
    for label, published, recorded in (("Total removed", TABLE2_TOTAL_REMOVED, total),
                                       ("Retained records", TABLE2_RETAINED, stats["num_records"])):
        cells.append({"row": label, "published": published, "recorded": recorded})
        if recorded != published:
            mismatches.append(cells[-1])

    return {"cells": cells, "mismatches": mismatches, "matches": not mismatches}


def check_disjointness(data_dir: Optional[Path] = None) -> Dict:
    """Stage 9's purpose: the three tiers share no records."""
    from importlib.util import module_from_spec, spec_from_file_location

    directory = data_dir or (paths.data() / "tiers_duckdb")
    script = paths.root() / "pipeline/09-disjointness/repair.py"
    spec = spec_from_file_location("stage9_repair", script)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    report = module.plan(Path(directory))
    available = [t for t in report["tiers"] if not t.get("error")]
    return {
        "data_dir": str(directory),
        "tiers_available": len(available),
        "tiers_expected": 3,
        "report": report,
        "checked": len(available) == 3,
    }


def run(action: str = "list", stage: Optional[int] = None, as_json: bool = False,
        verbose: bool = False) -> int:
    from messy_streets.cli import EXIT_MISMATCH, EXIT_OK, EXIT_UNAVAILABLE

    catalogue = stages()

    if action == "show":
        matching = [s for s in catalogue if s["n"] == stage]
        if not matching:
            print(f"no stage {stage}; the pipeline has {len(catalogue)}")
            return EXIT_UNAVAILABLE
        entry = matching[0]

        extra = {}
        if entry["n"] == 3:
            extra["table2"] = check_table2()
        if entry["n"] == 9:
            extra["disjointness"] = check_disjointness()

        if as_json:
            print(dumps({"stage": entry, **extra}, indent=2))
            return EXIT_MISMATCH if extra.get("table2", {}).get("mismatches") else EXIT_OK

        print(f"\nStage {entry['n']} — {entry['title']}\n")
        for label in ("inputs", "outputs", "scale", "needs"):
            print(f"  {label:<10} {entry[label]}")
        print(f"  {'runnable':<10} {entry['runnable']}")
        if entry.get("verifies"):
            print(f"  {'verifies':<10} {entry['verifies']}")
        print(f"  {'code':<10} " + f"\n  {'':<10} ".join(entry["code"]))
        if entry.get("note"):
            print(f"\n  {entry['note']}")

        if "table2" in extra:
            result = extra["table2"]
            print("\n  Table 2, checked against the statistics this stage emitted:\n")
            for cell in result["cells"]:
                mark = "ok" if cell["published"] == cell["recorded"] else "DIFFERS"
                print(f"    {cell['row']:<34}{cell['published']:>13,}  {mark}")
            print(f"\n  {'all cells match' if result['matches'] else 'MISMATCH'}")

        if "disjointness" in extra:
            result = extra["disjointness"]
            print(f"\n  Disjointness, checked directly on the tier databases in "
                  f"{result['data_dir']}:\n")
            for tier in result["report"]["tiers"]:
                if tier.get("error"):
                    print(f"    {tier['tier']:<8} {tier['error']}")
                else:
                    print(f"    {tier['tier']:<8} {tier['records']:>6} records, "
                          f"{tier['duplicates']} duplicate, "
                          f"{tier['overlapping_with_higher_tier']} overlapping")
            if result["checked"]:
                print(f"\n  tiers are mutually disjoint: {result['report']['disjoint']}")
            else:
                print(f"\n  only {result['tiers_available']} of 3 tier databases are shipped; "
                      "point --data-dir at all six to check the full property")

        if extra.get("table2", {}).get("mismatches"):
            return EXIT_MISMATCH
        return EXIT_OK

    if as_json:
        print(dumps({"layer": "L4", "stages": catalogue}, indent=2))
        return EXIT_OK

    runnable = {True: "yes", False: "no", "partially": "partial", "with keys": "keys"}
    print(f"\nThe {len(catalogue)} stages that produced MESSY STREETS\n")
    print(f"  {'#':>3}  {'stage':<44}{'runnable':<10}scale")
    print("  " + "-" * 88)
    for entry in catalogue:
        print(f"  {entry['n']:>3}  {entry['title'][:43]:<44}"
              f"{runnable.get(entry['runnable'], '?'):<10}{entry['scale'][:30]}")
    print("\n  messy-streets pipeline show <n>   for one stage in full")
    print("  stages 3 and 9 are checked against the artefact's own data")
    return EXIT_OK
