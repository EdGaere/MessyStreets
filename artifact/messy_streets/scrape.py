"""scrape — re-run stages 1 to 3 against Web Data Commons, bounded or whole.

Stage 1 downloads the December 2024 WDC corpus: fifty schema.org classes, each
split into parts numbered from zero. 136.7 billion quads, days of transfer, and
a third-party corpus the artefact is not allowed to redistribute. That is why
the shipped pipeline manifest marks it not runnable.

Not runnable is not the same as not reproducible, though, and the difference is
one flag. A single part of a single class is a few hundred megabytes: it
downloads in minutes, parses with the same code the paper used, and produces
counts that can be checked. That is enough to show the path works end to end
without asking anyone for a terabyte.

    scrape --class LocalBusiness --part 0     one archive
    scrape --all-classes --all-parts          the whole corpus, if you mean it

Both are the same code; only the extent differs, and the plan says which you
asked for. Nothing downloads without an explicit opt-in, and the plan needs no
network, so the plan is testable where the transfer is not.
"""

from json import dumps, loads
from typing import Dict, List, NamedTuple, Optional

from messy_streets import paths

OPT_IN = "--i-supply-my-own-storage"

RELEASE = "2024-12"
BASE_URL = ("https://data.dws.informatik.uni-mannheim.de/structureddata"
            f"/{RELEASE}/quads/classspecific")

# Observed while building the benchmark. Used only to price a plan, never to
# stand in for a real count.
TYPICAL_PART_BYTES = 380_000_000
TYPICAL_PARTS_PER_CLASS = 40


def classes() -> List[str]:
    """The fifty classes the paper drew from, as recorded by stage 3."""
    stats = paths.data() / "pipeline" / "wdc-filter-stats.json"
    return list(loads(stats.read_text(encoding="utf8"))["all_classes"])


def url_for(class_name: str, part: int) -> str:
    return f"{BASE_URL}/{class_name}/part_{part}.gz"


class Target(NamedTuple):
    class_name: str
    part: Optional[int]        # None means "every part, until one is missing"

    @property
    def bounded(self) -> bool:
        return self.part is not None

    def url(self) -> str:
        return url_for(self.class_name, self.part if self.bounded else 0)


def targets(class_names: Optional[List[str]], part: Optional[int],
            all_classes: bool, all_parts: bool) -> List[Target]:
    chosen = classes() if all_classes else (class_names or [])
    return [Target(name, None if all_parts else part) for name in chosen]


def _size(byte_count: float) -> str:
    for unit, scale in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6)):
        if byte_count >= scale:
            return f"{byte_count / scale:.1f} {unit}"
    return f"{byte_count:.0f} B"


def _duration(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f} s"
    if seconds < 5400:
        return f"{seconds / 60:.0f} min"
    if seconds < 172800:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} days"


def estimate(target_list: List[Target]) -> Dict[str, float]:
    """Rough, and labelled as rough. A bounded run is known; the corpus is not."""
    parts = sum(1 if t.bounded else TYPICAL_PARTS_PER_CLASS for t in target_list)
    return {"parts": parts, "bytes": parts * TYPICAL_PART_BYTES}


class PartResult(NamedTuple):
    class_name: str
    part: int
    status: str                # "ok", "missing", or an error
    rows: int = 0
    parsed: int = 0
    failed: int = 0
    with_street: int = 0
    with_street_and_geo: int = 0
    written: str = ""


def fetch_part(class_name: str, part: int, destination, timeout: float,
               verbose: bool = False) -> PartResult:
    """Download one part, parse it, write the extraction. Never touches data/."""
    from gzip import GzipFile
    from io import TextIOWrapper

    from messy_streets import fetch, nquads

    url = url_for(class_name, part)

    def announce(message: str) -> None:
        print(f"      {class_name} part {part}: {message}", flush=True)

    # The mirror throttles; the retry policy is the paper's own downloader's.
    outcome = fetch.open_with_retry(url, timeout=timeout, announce=announce)
    if outcome.missing:
        return PartResult(class_name, part, "missing")
    if not outcome.ok:
        return PartResult(class_name, part, outcome.error)

    try:
        with outcome.stream as response:
            with GzipFile(fileobj=response) as raw:
                lines = TextIOWrapper(raw, encoding="utf8", errors="replace")
                records, counts = nquads.extract(lines)
    except Exception as error:                                       # noqa: BLE001
        # A stream that breaks mid-part is an error, not a missing part: the
        # difference matters, because "missing" ends the walk.
        return PartResult(class_name, part, f"{type(error).__name__}: {error}")

    directory = destination / class_name
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f"{part}.tsv"
    with output.open("w", encoding="utf8") as handle:
        for line in nquads.to_tsv(records):
            handle.write(line + "\n")

    return PartResult(class_name, part, "ok", counts.rows, counts.parsed,
                      counts.failed, counts.with_street,
                      counts.with_street_and_geo, str(output))


def download(target_list: List[Target], destination, timeout: float,
             limit: Optional[int] = None, verbose: bool = False) -> List[PartResult]:
    results: List[PartResult] = []
    for target in target_list:
        if target.bounded:
            print(f"    {target.class_name} part {target.part} ...", flush=True)
            results.append(fetch_part(target.class_name, target.part,
                                      destination, timeout, verbose))
            continue

        # Walk parts from zero until one is missing, as the original did.
        part = 0
        while True:
            if limit is not None and part >= limit:
                break
            print(f"    {target.class_name} part {part} ...", flush=True)
            result = fetch_part(target.class_name, part, destination, timeout, verbose)
            if result.status == "missing":
                print(f"    {target.class_name}: {part} part(s), no more", flush=True)
                break
            results.append(result)
            if result.status != "ok":
                break
            part += 1
    return results


def report(results: List[PartResult]) -> None:
    print()
    width = max([len(r.class_name) for r in results] + [len("class")]) + 2
    print(f"  {'class':<{width}}{'part':>5}{'quads':>14}{'unparsed':>10}"
          f"{'street':>9}{'+geo':>8}   status")
    print("  " + "-" * (width + 55))
    for item in results:
        print(f"  {item.class_name:<{width}}{item.part:>5}{item.rows:>14,}"
              f"{item.failed:>10,}{item.with_street:>9,}"
              f"{item.with_street_and_geo:>8,}   {item.status}")

    good = [r for r in results if r.status == "ok"]
    if good:
        print("  " + "-" * (width + 55))
        print(f"  {'total':<{width}}{'':>5}{sum(r.rows for r in good):>14,}"
              f"{sum(r.failed for r in good):>10,}"
              f"{sum(r.with_street for r in good):>9,}"
              f"{sum(r.with_street_and_geo for r in good):>8,}")

    print("\n  'street' is address nodes carrying a streetAddress; '+geo' is those that")
    print("  also resolve to a latitude and longitude. The second number is what stage 3")
    print("  filters and what the benchmark is eventually drawn from.")
    print("  These are the counts for what you downloaded, not for the whole corpus:")
    print("  the paper's 95,014,529 is the sum over all fifty classes and every part.")


def run(class_names: Optional[List[str]] = None, part: Optional[int] = None,
        all_classes: bool = False, all_parts: bool = False,
        limit: Optional[int] = None, timeout: float = 600.0,
        opt_in: bool = False, as_json: bool = False, verbose: bool = False) -> int:
    from messy_streets.cli import EXIT_OK, EXIT_UNAVAILABLE

    known = classes()
    unknown = [c for c in (class_names or []) if c not in known]
    if unknown:
        print(f"unknown class(es): {', '.join(unknown)}")
        print(f"choose from: {', '.join(known[:8])} ... ({len(known)} in total)")
        return EXIT_UNAVAILABLE

    if not all_classes and not class_names:
        print("nothing to scrape: give --class <name> or --all-classes")
        print(f"classes: {', '.join(known[:8])} ... ({len(known)} in total)")
        return EXIT_UNAVAILABLE

    if not all_parts and part is None:
        part = 0

    target_list = targets(class_names, part, all_classes, all_parts)
    scale = estimate(target_list)
    destination = paths.out() / "scrape"
    whole_corpus = all_classes and all_parts

    if as_json:
        print(dumps({
            "layer": "L4",
            "opt_in_given": opt_in,
            "release": RELEASE,
            "classes": [t.class_name for t in target_list],
            "part": part if not all_parts else None,
            "all_parts": all_parts,
            "whole_corpus": whole_corpus,
            "estimated_parts": scale["parts"],
            "estimated_bytes": scale["bytes"],
            "destination": str(destination),
            "first_url": target_list[0].url() if target_list else None,
            "would_run": opt_in,
            "note": ("Re-runs stages 1-3 on what you ask for. The corpus is "
                     "third-party and is not redistributed by this artefact; a "
                     "bounded run shows the path works without transferring it all."),
            "exit_code": EXIT_OK,
        }, indent=2))
        return EXIT_OK

    extent = ("the whole corpus" if whole_corpus else
              f"{len(target_list)} class(es), " +
              ("every part" if all_parts else f"part {part}"))
    print(f"\nWeb Data Commons scrape plan — {RELEASE} release, {extent}\n")

    shown = target_list[:8]
    print(f"  {'class':<28}{'part':<10}url")
    print("  " + "-" * 92)
    for target in shown:
        where = "0..N" if not target.bounded else str(target.part)
        print(f"  {target.class_name:<28}{where:<10}{target.url()}")
    if len(target_list) > len(shown):
        print(f"  ... and {len(target_list) - len(shown)} more class(es)")

    print(f"\n  about {scale['parts']:,} part(s), roughly {_size(scale['bytes'])} "
          f"to transfer.")
    if not all_parts:
        print("  A part is a few hundred MB and takes minutes.")
    else:
        print(f"  Part counts per class are discovered by walking from zero until one")
        print(f"  is missing, so the total is an estimate until it runs.")
    print(f"  destination  {destination}")

    if whole_corpus:
        print("\n  This is the full December 2024 corpus: 136.7 bn quads across fifty")
        print("  classes, days of transfer, and hundreds of gigabytes on disk. The paper")
        print("  ran it once, on a dedicated machine. A single part proves the same code")
        print("  path — consider --class <name> --part 0 first.")

    print("\n  The corpus belongs to Web Data Commons and is not redistributed here.")
    print("  What this verb re-runs is stages 1-3: download, parse the quads, join")
    print("  address to geo. Building the tiers from the result is stage 7, which")
    print("  needs the reference data and the judges as well.")

    if not opt_in:
        print(f"\n  This was a plan; nothing was downloaded. To run it, pass {OPT_IN}.")
        print("  You supply the bandwidth and the disk, and accept the source's terms.")
        return EXIT_OK

    print(f"\n  {OPT_IN} given — downloading into {destination}.\n")
    destination.mkdir(parents=True, exist_ok=True)
    results = download(target_list, destination, timeout, limit=limit, verbose=verbose)
    if not results:
        print("  nothing was downloaded.")
        return EXIT_UNAVAILABLE
    report(results)
    return EXIT_OK if any(r.status == "ok" for r in results) else EXIT_UNAVAILABLE
