#!/usr/bin/env python3
"""Build data/expected/*.json from the LaTeX printed in the paper.

The artefact should check itself against what was *published*, not against an
intermediate that may have been regenerated since. So the reference is parsed
from the two table files the paper \\inputs:

    Tables/release-gold-2-error-bars.tex  -> Table 4
    Tables/effect_summary.tex             -> Table 5

The paper's row labels differ from the ones the pipeline generates ("Google
Maps v3" versus "Google Maps API v3"), and Table 5 is assembled by hand from
four divergence tables that are never printed on their own. Both mappings are
recorded here rather than inferred, so the artefact can say which published
cell each rebuilt number corresponds to.

Usage:
    python3 tools/expected.py --source /local/home/gaeree/phd
"""

from argparse import ArgumentParser
from json import dumps
from pathlib import Path
from re import DOTALL, finditer, search, sub
from sys import exit

ROOT = Path(__file__).resolve().parent.parent

# Paper row label -> label the pipeline produces.
GEOCODERS = {
    "Google Maps v3": "Google Maps API v3",
    "MapQuest v1": "MapQuest  API",
    "ArcGIS": "ArcGIS API",
    "Geoapify v1": "Geoapify API",
    "Here v7": "Here API v7",
    "Mapbox v5": "Mapbox API",
    "OpenCage v1": "OpenCage API",
    "Azure Maps": "Azure Maps API",
    "Pelias v1": "Pelias API",
    "TomTom v2": "TomTom API",
    "Photon": "Komoot Photon API",
    "Nominatim": "Nominatim API",
}

# Table 4's columns, in order, mapped to the rebuilt table's column names.
TABLE4_COLUMNS = [
    ("CRR", "Found"),
    ("GH1", "Geohash 1 (+/- 2'500 km)"),
    ("GH4", "Geohash 4 (+/- 20 km)"),
    ("GH6", "Geohash 6 (+/- 0.6 km)"),
]

# Table 5's four value columns, in order, each naming the error-bars table it
# comes from. "High divergence" means LOW trigram overlap with the canonical
# form -- the naming inverts, which is exactly why it is written down here.
TABLE5_COLUMNS = [
    ("High divergence CRR", "{tier}-low-trigrams-2-error-bars", "Found"),
    ("High divergence GH6", "{tier}-low-trigrams-2-error-bars", "6"),
    ("Low divergence CRR", "{tier}-high-trigrams-2-error-bars", "Found"),
    ("Low divergence GH6", "{tier}-high-trigrams-2-error-bars", "6"),
]

# mean and SEM, with the paper's bold/underline emphasis stripped.
CELL = r"\$(?:\\mathbf\{|\\underline\{)?([0-9.]+)\}?_\{\\pm ([0-9.]+)\}\$"


def clean(label: str) -> str:
    """Strip the open-source dagger and surrounding whitespace."""
    return sub(r"\$\^\\dagger\$", "", label).strip()


def body_rows(tex: str):
    """Yield (cells_before_first_number, [(mean, sem), ...]) for each body row."""
    body = search(r"\\midrule(.*?)\\bottomrule", tex, flags=DOTALL)
    if not body:
        raise SystemExit("expected: no table body found")
    for line in body.group(1).splitlines():
        cells = [(float(m.group(1)), float(m.group(2))) for m in finditer(CELL, line)]
        if not cells:
            continue
        prefix = [clean(part) for part in line.split("&")[: -len(cells)]]
        yield prefix, cells


def build_table4(tex: str) -> dict:
    values = {}
    for prefix, cells in body_rows(tex):
        label = prefix[0]
        if label not in GEOCODERS:
            raise SystemExit(f"expected: unknown geocoder in Table 4: {label!r}")
        if len(cells) != len(TABLE4_COLUMNS):
            raise SystemExit(f"expected: {label} has {len(cells)} cells, want {len(TABLE4_COLUMNS)}")
        values[GEOCODERS[label]] = {
            name: {"mean": mean, "sem": sem, "rebuilt_column": column}
            for (name, column), (mean, sem) in zip(TABLE4_COLUMNS, cells)
        }
    return {
        "paper_table": 4,
        "paper_label": "tab:address_gold",
        "describes": ("Candidate Return Rate and geohash accuracy of twelve geocoders on the "
                      "gold tier, in percent. Mean +/- 2 SEM over 10 runs of 100 addresses."),
        "source": "phd/publications/messy_streets/Tables/release-gold-2-error-bars.tex",
        "rebuilt_from": {"messy_streets/release-gold-2-error-bars": "all columns"},
        "values": values,
    }


def build_table5(tex: str) -> dict:
    values = {}
    for prefix, cells in body_rows(tex):
        # rows look like:  <geocoder> & <tier> & <4 cells>   or   & <tier> & <4 cells>
        parts = [p for p in prefix if p]
        if len(parts) == 2:
            geocoder, tier = parts
            build_table5.current = geocoder
        elif len(parts) == 1:
            geocoder, tier = build_table5.current, parts[0]
        else:
            raise SystemExit(f"expected: cannot read Table 5 row prefix {prefix!r}")
        if geocoder not in GEOCODERS:
            raise SystemExit(f"expected: unknown geocoder in Table 5: {geocoder!r}")
        if len(cells) != len(TABLE5_COLUMNS):
            raise SystemExit(f"expected: {geocoder}/{tier} has {len(cells)} cells")

        prefix_key = "release-gold" if tier.lower() == "gold" else "release-silver"
        values.setdefault(GEOCODERS[geocoder], {})[tier.lower()] = {
            name: {
                "mean": mean,
                "sem": sem,
                "rebuilt_table": f"messy_streets/{source.format(tier=prefix_key)}",
                "rebuilt_column": column,
            }
            for (name, source, column), (mean, sem) in zip(TABLE5_COLUMNS, cells)
        }
    return {
        "paper_table": 5,
        "paper_label": "tab:effect_summary",
        "describes": ("CRR and GH6 by component verification and surface-form divergence. "
                      "High divergence means LOW trigram overlap with the canonical form."),
        "source": "phd/publications/messy_streets/Tables/effect_summary.tex",
        "rebuilt_from": {
            "messy_streets/release-gold-low-trigrams-2-error-bars": "gold, high divergence",
            "messy_streets/release-gold-high-trigrams-2-error-bars": "gold, low divergence",
            "messy_streets/release-silver-low-trigrams-2-error-bars": "silver, high divergence",
            "messy_streets/release-silver-high-trigrams-2-error-bars": "silver, low divergence",
        },
        "values": values,
    }


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()

    tables = args.source / "phd/publications/messy_streets/Tables"
    target = ROOT / "data" / "expected"
    target.mkdir(parents=True, exist_ok=True)

    for filename, builder, out_name in (
        ("release-gold-2-error-bars.tex", build_table4, "table4.json"),
        ("effect_summary.tex", build_table5, "table5.json"),
    ):
        path = tables / filename
        if not path.is_file():
            print(f"expected: missing {path}")
            return 2
        document = builder(path.read_text(encoding="utf8"))
        (target / out_name).write_text(dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf8")
        count = sum(len(v) if isinstance(next(iter(v.values())), dict) and "mean" in next(iter(v.values()))
                    else sum(len(t) for t in v.values()) for v in document["values"].values())
        print(f"  Table {document['paper_table']}: {len(document['values'])} geocoders, {count} published cells")

    return 0


if __name__ == "__main__":
    exit(main())
