"""geocode — re-query the live geocoders, and measure how far they have moved.

The only verb that touches the network, and the only one whose output will not
match the paper. The services and the OpenStreetMap snapshots behind the
open-source ones have changed since June 2026; a live run reproduces the
*finding*, not the figures.

That makes the interesting output not the new numbers but the difference. A
live run is compared against the predictions recorded at the time, per
provider, so the result is a measurement — how much has this geocoder drifted?
— rather than a failed reproduction.

Nothing runs without an explicit opt-in. By default the verb plans: which
providers are configured, how many calls it would make, and how long that would
take. That plan needs no network and no keys, so it is testable, which the live
path is not.
"""

from json import dumps, loads
from os import environ
from typing import Dict, List, NamedTuple, Optional

from messy_streets import paths

# Provider -> (label, credential environment variable or None, rate limit in
# seconds between calls). The three with no credential are the open-source
# geocoders; they are also the ones the paper's findings are about.
PROVIDERS = {
    "nominatim":        ("Nominatim", None, 2.0),
    "photon":           ("Komoot Photon", None, 1.0),
    "pelias":           ("Pelias", "GEOCODE_EARTH_API_KEY", 1.0),
    "arcgis":           ("ArcGIS", None, 1.0),
    "google-geocoding": ("Google Maps v3", "GOOGLE_MAPS_API_KEY", 1.0),
    "here":             ("Here v7", "HERE_API_KEY", 1.0),
    "mapbox":           ("Mapbox v5", "MAPBOX_API_KEY", 1.0),
    "azure_maps":       ("Azure Maps", "AZURE_MAPS_API_KEY", 1.0),
    "opencage":         ("OpenCage v1", "OPENCAGE_API_KEY", 1.0),
    "tomtom":           ("TomTom v2", "TOMTOM_API_KEY", 1.0),
    "geoapify":         ("Geoapify v1", "GEOAPIFY_MAPS_API_KEY", 1.0),
    "openmapquest":     ("MapQuest v1", "MAPQUEST_API_KEY", 1.0),
}

# What a full re-run of the paper covers.
FULL_RUNS = 10
FULL_OBSERVATIONS = 100
FULL_PRECISIONS = 4

OPT_IN = "--i-supply-my-own-keys"


class Plan(NamedTuple):
    provider: str
    label: str
    credential: Optional[str]
    configured: bool
    calls: int
    seconds: float


def plan(providers: List[str], runs: int, observations: int) -> List[Plan]:
    planned = []
    for name in providers:
        label, credential, delay = PROVIDERS[name]
        calls = runs * observations * FULL_PRECISIONS
        planned.append(Plan(
            provider=name,
            label=label,
            credential=credential,
            configured=credential is None or bool(environ.get(credential)),
            calls=calls,
            seconds=calls * delay,
        ))
    return planned


def _duration(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f} s"
    if seconds < 5400:
        return f"{seconds / 60:.0f} min"
    if seconds < 172800:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} days"


def recorded_predictions(provider: str, precision: str, run: int) -> Optional[Dict[str, str]]:
    """The predictions this provider gave in June 2026, keyed by input address."""
    directories = {
        "nominatim": "Nominatim", "photon": "Photon", "pelias": "Pelias",
        "arcgis": "arcgis", "google-geocoding": "Google", "here": "here",
        "mapbox": "Mapbox", "azure_maps": "azure_maps", "opencage": "opencage",
        "tomtom": "tomtom", "geoapify": "geoapify", "openmapquest": "mapquest",
    }
    path = (paths.src() / "phd/experiments/experiments/address"
            / "messy-streets-release-gold-2"
            / f"{directories[provider]}-{precision}" / f"run{run}" / "all_results.json")
    if not path.is_file():
        return None
    return {record["input"]: record["prediction"]
            for record in loads(path.read_text(encoding="utf8"))}


class Drift(NamedTuple):
    provider: str
    label: str
    compared: int
    agreed: int
    now_found_then_not: int
    then_found_now_not: int
    error: str = ""

    @property
    def agreement(self) -> float:
        return 100.0 * self.agreed / self.compared if self.compared else 0.0


def query(planned: List[Plan], runs: int, observations: int,
          verbose: bool = False) -> List[Drift]:
    """Query each provider live and compare with what it answered in June 2026.

    Deliberately compared at geohash precision 1 — roughly 2,500 km. At that
    resolution a disagreement means the provider now returns a materially
    different place, or none at all, rather than having nudged a coordinate.
    """
    from asyncio import run as async_run
    from time import sleep

    from messy_streets import smoke, workspace

    drifts: List[Drift] = []
    with workspace.vendored_tree():
        smoke._quieten(verbose)
        from phd.models.load_model import LoadModel

        for item in planned:
            recorded = recorded_predictions(item.provider, "geohash1", 1)
            if not recorded:
                drifts.append(Drift(item.provider, item.label, 0, 0, 0, 0,
                                    "no recorded predictions shipped"))
                continue

            addresses = list(recorded)[: observations]
            _, _, delay = PROVIDERS[item.provider]

            try:
                model = LoadModel(model_name=item.provider, config="geohash1")
            except Exception as error:                       # noqa: BLE001
                drifts.append(Drift(item.provider, item.label, 0, 0, 0, 0,
                                    f"{type(error).__name__}: {error}"))
                continue

            agreed = now_only = then_only = compared = 0
            for index, address in enumerate(addresses):
                try:
                    prediction, _ = async_run(model.predict(input_sequence=address))
                except Exception:                            # noqa: BLE001
                    prediction = None
                then = recorded[address]
                compared += 1
                if prediction == then:
                    agreed += 1
                elif prediction is not None and then is None:
                    now_only += 1
                elif prediction is None and then is not None:
                    then_only += 1
                if not verbose and index % 10 == 9:
                    print(f"    {item.provider}: {index + 1}/{len(addresses)}",
                          end="\r", flush=True)
                sleep(delay)

            print(f"    {item.provider}: {compared} queried" + " " * 20, flush=True)
            drifts.append(Drift(item.provider, item.label, compared, agreed,
                                now_only, then_only))
    return drifts


def report_drift(drifts: List[Drift]) -> None:
    print()
    print(f"  {'provider':<18}{'compared':>9}{'agree':>8}{'now only':>10}"
          f"{'then only':>11}   agreement")
    print("  " + "-" * 74)
    for item in drifts:
        if item.error:
            print(f"  {item.provider:<18}{item.error}")
            continue
        print(f"  {item.provider:<18}{item.compared:>9}{item.agreed:>8}"
              f"{item.now_found_then_not:>10}{item.then_found_now_not:>11}"
              f"   {item.agreement:>5.1f}%")
    print("\n  Compared at geohash precision 1 (about 2,500 km): a disagreement means")
    print("  a materially different place, or no result at all — not a nudged coordinate.")
    print("  'now only' returns a candidate today but did not in June 2026; 'then only'")
    print("  is the reverse. Both are drift in the service, not error in the benchmark.")


def run(providers: Optional[List[str]] = None, runs: int = FULL_RUNS,
        observations: int = FULL_OBSERVATIONS, opt_in: bool = False,
        as_json: bool = False, verbose: bool = False) -> int:
    from messy_streets.cli import EXIT_OK, EXIT_UNAVAILABLE

    chosen = providers or list(PROVIDERS)
    unknown = [p for p in chosen if p not in PROVIDERS]
    if unknown:
        print(f"unknown provider(s): {', '.join(unknown)}")
        print(f"choose from: {', '.join(PROVIDERS)}")
        return EXIT_UNAVAILABLE

    planned = plan(chosen, runs, observations)
    total_calls = sum(p.calls for p in planned)
    total_seconds = sum(p.seconds for p in planned)
    configured = [p for p in planned if p.configured]
    missing = [p for p in planned if not p.configured]

    if as_json:
        print(dumps({
            "layer": "L3",
            "opt_in_given": opt_in,
            "plan": [p._asdict() for p in planned],
            "total_calls": total_calls,
            "estimated_seconds": total_seconds,
            "configured": [p.provider for p in configured],
            "missing_credentials": {p.provider: p.credential for p in missing},
            "would_run": opt_in and bool(configured),
            "note": ("Live results will not match the paper: the services and their "
                     "OpenStreetMap snapshots have moved since June 2026."),
            "exit_code": EXIT_OK,
        }, indent=2))
        return EXIT_OK

    print(f"\nLive geocoding plan — {len(chosen)} provider(s), "
          f"{runs} run(s) x {observations} addresses x {FULL_PRECISIONS} precisions\n")
    print(f"  {'provider':<18}{'credential':<26}{'status':<10}{'calls':>8}  time")
    print("  " + "-" * 74)
    for item in planned:
        credential = item.credential or "none needed"
        status = "ready" if item.configured else "NOT SET"
        print(f"  {item.provider:<18}{credential:<26}{status:<10}{item.calls:>8}  "
              f"{_duration(item.seconds)}")

    print(f"\n  {total_calls:,} calls, about {_duration(total_seconds)} in total, "
          f"queried sequentially.")
    print(f"  {len(configured)} of {len(planned)} providers are configured.")

    if missing:
        print(f"\n  Set these to include the rest:")
        for item in missing:
            print(f"    export {item.credential}=...")

    print("\n  Live results will NOT match the paper. The commercial services and the")
    print("  OpenStreetMap snapshots behind the open-source ones have changed since")
    print("  June 2026. A live run reproduces the finding, not the figures — so what")
    print("  this verb reports is drift against the recorded predictions.")

    if not opt_in:
        print(f"\n  This was a plan; nothing was queried. To run it, pass {OPT_IN}.")
        print("  You are responsible for the terms attached to your own API keys.")
        return EXIT_OK

    if not configured:
        print("\n  No provider is configured; nothing to run.")
        return EXIT_UNAVAILABLE

    print(f"\n  {OPT_IN} given — querying {len(configured)} provider(s).\n")
    results = query(configured, runs=runs, observations=observations, verbose=verbose)
    report_drift(results)
    return EXIT_OK
