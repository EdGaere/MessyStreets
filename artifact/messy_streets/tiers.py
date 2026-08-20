"""Reading the released tiers.

Shared by `stats` and `inspect`. The released files use bare `NaN` for absent
values, which Python accepts and strict RFC 8259 parsers do not — see
ARTIFACT.md, Known deviations.
"""

from gzip import open as gzip_open
from json import loads
from math import isnan
from typing import Any, Dict, Iterator, List

from messy_streets import paths

TIERS = ("gold", "silver", "raw")

# Paper component name -> schema.org field in the record.
COMPONENTS = {
    "Street": "streetAddress",
    "Country": "addressCountry",
    "Postcode": "postalCode",
    "Locality": "addressLocality",
    "Region": "addressRegion",
}


def present(value: Any) -> bool:
    """A component counts as present when it carries a non-blank value."""
    if value is None:
        return False
    if isinstance(value, float) and isnan(value):
        return False
    return str(value).strip() != ""


def read(tier: str) -> Iterator[Dict]:
    path = paths.data() / "tiers" / f"{tier}.jsonl.gz"
    if not path.is_file():
        raise FileNotFoundError(f"tier not found: {path}")
    with gzip_open(path, "rt", encoding="utf8") as handle:
        for line in handle:
            if line.strip():
                yield loads(line)


def load(tier: str) -> List[Dict]:
    return list(read(tier))


def address(record: Dict) -> Dict:
    return record["aux"]["address"]
