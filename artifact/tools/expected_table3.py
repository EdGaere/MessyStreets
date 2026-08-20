#!/usr/bin/env python3
"""Build data/expected/table3.json — the component-existence table.

Table 3 has two reference points, not one, and they disagree:

  * what the paper prints, read from ms.tex;
  * what the analysis outputs in the source tree say, which is what the
    paper's method actually produced.

Six of fifteen cells differ between them. Recording both, with the method's
provenance, is the only honest option: the artefact can then show a reviewer
the released tiers' true values alongside each, rather than silently picking
a winner.

Usage:
    python3 tools/expected_table3.py --source /local/home/gaeree/phd
"""

from argparse import ArgumentParser
from collections import Counter
from json import dumps, load
from pathlib import Path
from re import DOTALL, search
from sys import exit

ROOT = Path(__file__).resolve().parent.parent

COMPONENTS = ["Street", "Country", "Postcode", "Locality", "Region"]
TIERS = ["gold", "silver", "raw"]

# Where each tier's analysis output lives, and which database it was drawn
# from. The silver row came from mq_1000 -- a 1,000-record pre-release
# database, not the released silver tier.
ANALYSIS_DIRS = {"gold": "release_gold", "silver": "release_silver_pre", "raw": "release_raw_pre"}


def paper_values(tex: str) -> dict:
    block = search(r"\\label\{tab:components\}(.*?)\\end\{tabular\}", tex, flags=DOTALL)
    if not block:
        raise SystemExit("expected: could not find tab:components in ms.tex")
    values = {}
    for line in block.group(1).splitlines():
        parts = [p.strip() for p in line.split("&")]
        if len(parts) != 4 or parts[0] not in COMPONENTS:
            continue
        numbers = [float(p.replace("\\%", "").replace("\\\\", "").strip()) for p in parts[1:]]
        values[parts[0]] = dict(zip(TIERS, numbers))
    if len(values) != len(COMPONENTS):
        raise SystemExit(f"expected: parsed {len(values)} components, want {len(COMPONENTS)}")
    return values


def analysis_values(source: Path) -> tuple[dict, dict]:
    base = source / "phd/datasets/address/messy_streets/v0/analysis"
    values, provenance = {}, {}
    for component in COMPONENTS:
        values[component] = {}
        for tier, directory in ANALYSIS_DIRS.items():
            path = base / directory / f"has({component.lower()}).json"
            with path.open(encoding="utf8") as handle:
                document = load(handle)
            stats = document["stats"]
            total = sum(stats.values())
            values[component][tier] = round(100.0 * stats.get("Yes", 0) / total, 1)
            databases = Counter(row[3]["source"] for row in document["data"])
            provenance[tier] = {
                "observations": total,
                "database": ", ".join(sorted(databases)),
                "benchmark": document["arguments"]["config"],
            }
    return values, provenance


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()

    tex = (args.source / "phd/publications/messy_streets/ms.tex").read_text(encoding="utf8")
    published = paper_values(tex)
    analysis, provenance = analysis_values(args.source)

    disagreements = [
        {"component": component, "tier": tier,
         "paper": published[component][tier], "analysis": analysis[component][tier]}
        for component in COMPONENTS for tier in TIERS
        if abs(published[component][tier] - analysis[component][tier]) > 0.05
    ]

    document = {
        "paper_table": 3,
        "paper_label": "tab:components",
        "describes": "Address component existence across the three benchmark tiers, in percent.",
        "source": "phd/publications/messy_streets/ms.tex",
        "method": (
            "Each cell is the share of records with a non-empty value, over 1,000 "
            "observations sampled from a benchmark slice -- not over the full 10,000 "
            "records of the released tier. The source database differs by tier: gold "
            "from hq_10000 and raw from lq_10000, but silver from mq_1000, a "
            "1,000-record pre-release database rather than the released silver tier."
        ),
        "provenance": provenance,
        "published": published,
        "analysis_output": analysis,
        "disagreements": disagreements,
    }
    (ROOT / "data/expected/table3.json").write_text(
        dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf8")

    print(f"  Table 3: {len(COMPONENTS)} components x {len(TIERS)} tiers = "
          f"{len(COMPONENTS) * len(TIERS)} cells")
    print(f"  {len(disagreements)} cell(s) where the paper and its own analysis output disagree")
    for item in disagreements:
        print(f"    {item['tier']} {item['component']}: paper {item['paper']}, analysis {item['analysis']}")
    return 0


if __name__ == "__main__":
    exit(main())
