#!/usr/bin/env python3
"""Generate croissant.json describing the three released tiers.

Croissant is the ML-dataset metadata standard; a machine-readable descriptor is
what lets a benchmark be found and loaded without reading the paper first. This
describes what the artefact actually distributes -- data/tiers/*.jsonl.gz --
rather than the internal benchmark directories the research pipeline used.

Validated with mlcroissant, which is pinned in requirements.txt.

Usage:
    python3 tools/croissant.py [--check]
"""

from argparse import ArgumentParser
from gzip import open as gzip_open
from hashlib import sha256
from json import dumps
from pathlib import Path
from sys import exit, stderr

ROOT = Path(__file__).resolve().parent.parent

CITATION = ("Gaere, E. and von Wangenheim, F. MESSY STREETS: A Benchmark for Geocoding "
            "Real-World Addresses. ACM SIGSPATIAL.")
# The artefact's version, not the paper's. Bumped when the released data changes.
VERSION = "1.0.0"

# Software is MIT; the data carries the terms of its three origins. Stated in
# full in LICENSE-DATA, and summarised here so a machine reading the metadata
# alone sees the ODbL obligation.
LICENSE = ("Code: MIT. Data: OpenStreetMap-derived fields (7,842 records) under "
           "ODbL 1.0, (c) OpenStreetMap contributors; OpenAddresses-derived fields "
           "under their per-source terms; address records from Web Data Commons. "
           "See LICENSE and LICENSE-DATA.")
ATTRIBUTION = ("Contains information from OpenStreetMap, (c) OpenStreetMap "
               "contributors, available under the Open Database License 1.0 "
               "(https://www.openstreetmap.org/copyright), and from OpenAddresses "
               "(https://openaddresses.io/) under its per-source terms.")
DATE_PUBLISHED = "2026-08-19"

TIERS = {
    "gold": "10,000 verbatim web addresses, each verified to exist against OpenAddresses "
            "or OpenStreetMap, with street, country and postcode individually validated.",
    "silver": "10,000 existence-verified addresses whose individual components are not "
              "validated. Same construction as the gold tier without the component judge.",
    "raw": "10,000 addresses requiring only a street component. Neither existence-verified "
           "nor component-validated; released for reference.",
}

# The six schema.org fields carried verbatim from the source corpus.
FIELDS = [
    ("streetAddress", "sc:Text", "Street address, verbatim as found in the source page."),
    ("addressLocality", "sc:Text", "Locality or city, verbatim. May be absent."),
    ("addressRegion", "sc:Text", "Region, state or province, verbatim. May be absent."),
    ("postalCode", "sc:Text", "Postal code, verbatim. May be absent."),
    ("addressCountry", "sc:Text", "Country, verbatim and in any language. May be absent."),
    ("postOfficeBoxNumber", "sc:Text", "PO box, verbatim. Usually absent."),
    ("latitude", "sc:Float", "Reference latitude, from the source page's schema.org/geo."),
    ("longitude", "sc:Float", "Reference longitude, from the source page's schema.org/geo."),
]


def digest_and_count(path: Path) -> tuple[str, int]:
    checksum = sha256(path.read_bytes()).hexdigest()
    with gzip_open(path, "rt", encoding="utf8") as handle:
        return checksum, sum(1 for line in handle if line.strip())


def build() -> dict:
    distribution, record_sets = [], []
    for tier, description in TIERS.items():
        path = ROOT / "data/tiers" / f"{tier}.jsonl.gz"
        checksum, records = digest_and_count(path)
        name = f"{tier}-tier"
        distribution.append({
            "@type": "sc:FileObject",
            "@id": name,
            "name": name,
            "description": f"{description} {records:,} records.",
            "contentUrl": f"data/tiers/{tier}.jsonl.gz",
            "encodingFormat": "application/jsonlines+gzip",
            "sha256": checksum,
        })
        record_sets.append({
            "@type": "cr:RecordSet",
            "@id": f"{tier}-records",
            "name": f"{tier}-records",
            "description": description,
            "field": [
                {
                    "@type": "cr:Field",
                    "@id": f"{tier}-records/{field}",
                    "name": field,
                    "description": field_description,
                    "dataType": data_type,
                    "source": {"fileObject": {"@id": name},
                               "extract": {"jsonPath": f"$.aux.address.{field}"}},
                }
                for field, data_type, field_description in FIELDS
            ] + [{
                "@type": "cr:Field",
                "@id": f"{tier}-records/input",
                "name": "input",
                "description": "The address as submitted to a geocoder: the components "
                               "concatenated, verbatim.",
                "dataType": "sc:Text",
                "source": {"fileObject": {"@id": name}, "extract": {"jsonPath": "$.input"}},
            }, {
                "@type": "cr:Field",
                "@id": f"{tier}-records/target",
                "name": "target",
                "description": "Reference location as a geohash at precision 10.",
                "dataType": "sc:Text",
                "source": {"fileObject": {"@id": name}, "extract": {"jsonPath": "$.target"}},
            }],
        })

    return {
        "@context": {
            "@language": "en", "@vocab": "https://schema.org/",
            "cr": "http://mlcommons.org/croissant/",
            "sc": "https://schema.org/",
            "data": {"@id": "cr:data", "@type": "@json"},
            "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
            "extract": "cr:extract", "field": "cr:field", "fileObject": "cr:fileObject",
            "fileProperty": "cr:fileProperty", "format": "cr:format",
            "includes": "cr:includes", "jsonPath": "cr:jsonPath", "recordSet": "cr:recordSet",
            "references": "cr:references", "regex": "cr:regex", "repeated": "cr:repeated",
            "replace": "cr:replace", "separator": "cr:separator", "source": "cr:source",
            "subField": "cr:subField", "transform": "cr:transform",
        },
        # NOTE: the @context below is deliberately minimal. Extending it with the
        # remaining official keys (dct, rai, conformsTo, ...) makes mlcroissant
        # stop resolving the FileObject nodes, so the document validates as it
        # stands and emits one cosmetic warning about the shorter context.
        "@type": "sc:Dataset",
        "name": "MESSY-STREETS",
        "description": (
            "A benchmark for evaluating geocoders on verbatim real-world web addresses. "
            "Three tiers of 10,000 records each, drawn without overlap from 16.9M address "
            "records filtered from the December 2024 Web Data Commons corpus, with reference "
            "locations verified against OpenAddresses and OpenStreetMap. Unlike benchmarks "
            "built from clean or synthetically perturbed data, every address is retained "
            "exactly as it appeared on the web, including missing, duplicated, misspelled "
            "and malformed components."
        ),
        "conformsTo": "http://mlcommons.org/croissant/1.0",
        "version": VERSION,
        "datePublished": DATE_PUBLISHED,
        "citation": CITATION,
        "keywords": ["geocoding", "address", "benchmark", "spatial data quality",
                     "web data commons"],
        "license": LICENSE,
        "creditText": ATTRIBUTION,
        "url": "https://github.com/EdGaere/MessyStreets",
        "citeAs": CITATION,
        "creator": [
            {"@type": "sc:Person", "name": "Edward Gaere",
             "affiliation": {"@type": "sc:Organization", "name": "ETH Zurich"}},
            {"@type": "sc:Person", "name": "Florian von Wangenheim",
             "affiliation": {"@type": "sc:Organization", "name": "ETH Zurich"}},
        ],
        "distribution": distribution,
        "recordSet": record_sets,
    }


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate without writing")
    args = parser.parse_args()

    document = build()
    target = ROOT / "croissant.json"

    if not args.check:
        target.write_text(dumps(document, indent=2) + "\n", encoding="utf8")
        print(f"wrote {target.relative_to(ROOT)}")

    try:
        from mlcroissant import Dataset
    except ImportError:
        print("mlcroissant not installed; wrote without validating", file=stderr)
        return 0

    try:
        Dataset(jsonld=document if args.check else str(target))
        print("croissant.json validates against mlcroissant")
        return 0
    except Exception as error:                                   # noqa: BLE001
        print(f"croissant validation failed: {error}", file=stderr)
        return 1


if __name__ == "__main__":
    exit(main())
