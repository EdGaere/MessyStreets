"""inspect — look at records from a released tier.

Not a verification step: the verb people will still be using after the paper.
Prints an address as it appears verbatim in the Web Data Commons extract, the
reference address it was matched against for existence verification, and the
surface-form divergence between them — which is the benchmark's whole subject.
"""

from json import dumps
from typing import Dict, List, Optional

from messy_streets import tiers


def _field(record: Dict, name: str) -> str:
    value = tiers.address(record).get(name)
    return str(value).strip() if tiers.present(value) else ""


def _existence(record: Dict) -> Optional[Dict]:
    return record.get("aux", {}).get("existence")


def select(tier: str, count: int, contains: Optional[str] = None,
           missing: Optional[str] = None) -> List[Dict]:
    chosen = []
    for record in tiers.read(tier):
        if contains and contains.lower() not in str(record.get("input", "")).lower():
            continue
        if missing:
            field = tiers.COMPONENTS.get(missing.title())
            if field is None:
                raise ValueError(f"unknown component {missing!r}; "
                                 f"choose from {', '.join(tiers.COMPONENTS)}")
            if tiers.present(tiers.address(record).get(field)):
                continue
        chosen.append(record)
        if len(chosen) >= count:
            break
    return chosen


def show(record: Dict) -> None:
    print(f"\n  {record.get('input', '')}")
    print(f"  {'-' * max(20, min(76, len(str(record.get('input', '')))))}")

    for name, field in tiers.COMPONENTS.items():
        value = _field(record, field)
        print(f"    {name.lower():<10} {value if value else '—'}")

    address = tiers.address(record)
    print(f"    {'coords':<10} {address.get('latitude')}, {address.get('longitude')}")
    print(f"    {'geohash10':<10} {record.get('target', '')}")

    existence = _existence(record)
    if existence:
        payload = existence.get("address", {}).get("payload", {})
        street = payload.get("street") or payload.get("street_name") or ""
        print(f"    {'verified':<10} against {existence.get('source', '?').upper()}: "
              f"{street or '(no street in reference)'}")
    else:
        print(f"    {'verified':<10} not existence-verified (raw tier)")


def run(tier: str = "gold", count: int = 5, contains: Optional[str] = None,
        missing: Optional[str] = None, as_json: bool = False) -> int:
    from messy_streets.cli import EXIT_ENVIRONMENT, EXIT_OK

    if tier not in tiers.TIERS:
        print(f"unknown tier {tier!r}; choose from {', '.join(tiers.TIERS)}")
        return EXIT_ENVIRONMENT

    try:
        records = select(tier, count, contains, missing)
    except ValueError as error:
        print(error)
        return EXIT_ENVIRONMENT

    if as_json:
        print(dumps({"tier": tier, "count": len(records), "records": records},
                    indent=2, default=str))
        return EXIT_OK

    if not records:
        print(f"no records in the {tier} tier matched.")
        return EXIT_OK

    print(f"\n{len(records)} record(s) from the {tier} tier")
    for record in records:
        show(record)
    print()
    return EXIT_OK
