"""N-Quad extraction — stage 2 of the construction pipeline.

Carried verbatim in behaviour from the script that produced the paper's data,
`phd/datasets/address/schema_org/v2/filter_addr_geo.py`. A re-scrape that
parsed differently would not be a reproduction of anything, so the regex, the
literal unescaping, the coordinate normalisation and the join rule are the
originals rather than a tidier rewrite.

The join: a parent node qualifies when it has a schema.org/address link to a
node carrying streetAddress, *and* a schema.org/geo link to a node carrying
both latitude and longitude. Everything else is dropped here, before the filter
cascade in stage 3 ever sees it.
"""

import re
from typing import Dict, Iterable, List, NamedTuple, Optional, Tuple

# N-Quads: subject predicate object graph .
NQUAD_PATTERN = re.compile(
    r'^'
    r'(?P<subject><[^>]+>|_:\S+)\s+'
    r'(?P<predicate><[^>]+>)\s+'
    r'(?P<object><[^>]+>|_:\S+|"(?:[^"\\]|\\.)*"(?:\^\^<[^>]+>|@[a-zA-Z-]+)?)\s+'
    r'(?P<graph><[^>]+>|_:\S+)\s+'
    r'\.\s*$'
)

COLUMNS = ("subject", "streetAddress", "postalCode", "addressLocality",
           "addressRegion", "addressCountry", "postOfficeBoxNumber",
           "latitude", "longitude")

# schema.org predicate -> the map it populates.
COMPONENTS = {
    "schema.org/streetAddress>": "streetAddress",
    "schema.org/postalCode>": "postalCode",
    "schema.org/addressLocality>": "addressLocality",
    "schema.org/addressRegion>": "addressRegion",
    "schema.org/addressCountry>": "addressCountry",
    "schema.org/postOfficeBoxNumber>": "postOfficeBoxNumber",
}


def parse_nquad(line: str) -> Optional[Tuple[str, str, str, str]]:
    match = NQUAD_PATTERN.match(line)
    if not match:
        return None
    return (match.group("subject"), match.group("predicate"),
            match.group("object"), match.group("graph"))


def extract_literal_value(obj: str) -> str:
    """The string inside a literal, with escapes resolved."""
    if not obj.startswith('"'):
        return obj
    index = 1
    chars: List[str] = []
    escapes = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"'}
    while index < len(obj):
        char = obj[index]
        if char == "\\" and index + 1 < len(obj):
            following = obj[index + 1]
            chars.append(escapes.get(following, following))
            index += 2
        elif char == '"':
            break
        else:
            chars.append(char)
            index += 1
    return "".join(chars)


def normalize_coordinate(value: str) -> str:
    """Scientific notation to a decimal string, as the original did."""
    try:
        return f"{float(value):.10f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        return value


class Counts(NamedTuple):
    rows: int
    parsed: int
    failed: int
    with_address: int
    with_street: int
    with_street_and_geo: int


def extract(lines: Iterable[str]) -> Tuple[List[Dict[str, str]], Counts]:
    """One pass over the quads, then the join. Returns records and counts."""
    address_link: Dict[str, str] = {}
    geo_link: Dict[str, str] = {}
    values: Dict[str, Dict[str, str]] = {name: {} for name in COMPONENTS.values()}
    latitude: Dict[str, str] = {}
    longitude: Dict[str, str] = {}

    rows = parsed = failed = with_address = 0

    for line in lines:
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        rows += 1

        quad = parse_nquad(line)
        if quad is None:
            failed += 1
            continue
        parsed += 1
        subject, predicate, obj, _ = quad

        if "schema.org/address>" in predicate:
            address_link[subject] = obj
            with_address += 1
            continue
        if "schema.org/geo>" in predicate:
            geo_link[subject] = obj
            continue
        if "schema.org/latitude>" in predicate:
            latitude[subject] = extract_literal_value(obj)
            continue
        if "schema.org/longitude>" in predicate:
            longitude[subject] = extract_literal_value(obj)
            continue
        for suffix, name in COMPONENTS.items():
            if suffix in predicate:
                values[name][subject] = extract_literal_value(obj)
                break

    records: List[Dict[str, str]] = []
    with_street = 0
    for parent, address_node in address_link.items():
        if address_node not in values["streetAddress"]:
            continue
        with_street += 1
        geo_node = geo_link.get(parent)
        if geo_node is None or geo_node not in latitude or geo_node not in longitude:
            continue
        record = {"subject": parent,
                  "latitude": normalize_coordinate(latitude[geo_node]),
                  "longitude": normalize_coordinate(longitude[geo_node])}
        for name in COMPONENTS.values():
            record[name] = values[name].get(address_node, "")
        records.append(record)

    return records, Counts(rows, parsed, failed, with_address, with_street,
                           len(records))


def to_tsv(records: List[Dict[str, str]]) -> Iterable[str]:
    """The original's output shape: every field quoted, because the data is messy."""
    yield "\t".join(f'"{name}"' for name in COLUMNS)
    for record in records:
        yield "\t".join(f'"{record.get(name, "")}"' for name in COLUMNS)
