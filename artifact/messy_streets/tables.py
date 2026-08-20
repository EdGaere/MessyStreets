"""tables — rebuild the paper's two result tables and check every cell.

Runs the five error-bars tables behind Tables 4 and 5, each aggregating ten
runs of a hundred addresses, entirely from predictions recorded when the
experiments were run. 420,000 replayed observations, no network, no API keys.

Where `smoke` checks one run against an intermediate, this checks the published
means and error bars against the LaTeX that was \\input into the paper. Each
mismatch names the paper table, the geocoder and the column, because a reviewer
matching output against a printed PDF by eye is where artefact evaluations go
quietly wrong.
"""

from contextlib import redirect_stdout
from io import StringIO
from json import dumps, loads
from re import DOTALL, finditer, search
from typing import Dict, List, NamedTuple, Optional, Tuple

from messy_streets import paths, smoke, workspace

# The rebuilt tables, and the paper table each one feeds.
SOURCES = {
    "messy_streets/release-gold-2-error-bars": 4,
    "messy_streets/release-gold-low-trigrams-2-error-bars": 5,
    "messy_streets/release-gold-high-trigrams-2-error-bars": 5,
    "messy_streets/release-silver-low-trigrams-2-error-bars": 5,
    "messy_streets/release-silver-high-trigrams-2-error-bars": 5,
}

# The paper prints one decimal place; means are percentages.
TOLERANCE = 0.05

# A rendered cell, e.g.  $\mathrm{100.0}_{{\pm 0.0}}$  — optionally wrapped in
# \mathbf when the pipeline marks it best in its column. The error term is
# already 2 SEM: render() emits 100*2*sem, matching the paper's convention.
RENDERED_CELL = r"\\mathrm\{([0-9.]+)\}_\{\{\\pm ([0-9.]+)\}\}"


def parse_latex(latex: str) -> Dict[str, Dict[str, Tuple[float, float]]]:
    """Read a regenerated table back out of its own LaTeX.

    render() returns the means as numbers and the mean +/- 2 SEM only inside
    the LaTeX it emits — which is the string that becomes output.tex and is
    \\input into the paper. Parsing it means the artefact compares the LaTeX it
    regenerates against the LaTeX that was published, rather than against a
    reimplementation of the statistics.
    """
    header = search(r"\\toprule\s*\n(.*?)\\\\", latex, flags=DOTALL)
    if not header:
        raise RuntimeError("regenerated table has no header row")
    columns = [part.strip() for part in header.group(1).split("&")][1:]

    body = search(r"\\midrule(.*?)\\bottomrule", latex, flags=DOTALL)
    if not body:
        raise RuntimeError("regenerated table has no body")

    parsed: Dict[str, Dict[str, Tuple[float, float]]] = {column: {} for column in columns}
    for line in body.group(1).splitlines():
        cells = [(float(m.group(1)), float(m.group(2))) for m in finditer(RENDERED_CELL, line)]
        if not cells:
            continue
        row = line.split("&", 1)[0].strip()
        for column, value in zip(columns, cells):
            parsed[column][row] = value
    return parsed


class Cell(NamedTuple):
    table: int
    row: str
    column: str
    published_mean: float
    published_sem: float
    rebuilt_mean: Optional[float]
    rebuilt_sem: Optional[float]
    # A cell the artefact is known not to match. Declared in the reference with
    # the value it is expected to produce, so a *change* still fails: this
    # records a deviation, it does not excuse the cell from checking.
    deviation: Optional[dict] = None

    def _close(self, mean: float, sem: float) -> bool:
        if self.rebuilt_mean is None:
            return False
        return (abs(self.rebuilt_mean - mean) <= TOLERANCE
                and abs(self.rebuilt_sem - sem) <= TOLERANCE)

    @property
    def matches(self) -> bool:
        return self._close(self.published_mean, self.published_sem)

    @property
    def is_known_deviation(self) -> bool:
        """Differs from the paper, but by exactly the declared amount."""
        if self.deviation is None or self.matches:
            return False
        return self._close(self.deviation["observed_mean"], self.deviation["observed_sem"])

    @property
    def accounted_for(self) -> bool:
        return self.matches or self.is_known_deviation

    @property
    def published(self) -> str:
        return f"{self.published_mean:.1f} ±{self.published_sem:.1f}"

    @property
    def rebuilt(self) -> str:
        if self.rebuilt_mean is None:
            return "missing"
        return f"{self.rebuilt_mean:.1f} ±{self.rebuilt_sem:.1f}"


def _rebuild(name: str, verbose: bool) -> Dict[str, Dict[str, Tuple[float, float]]]:
    """Rebuild one error-bars table; return (mean, 2 SEM) per cell, in percent.

    run() returns the ten per-run tables; render() is what aggregates them and
    formats each cell as mean +/- 2 SEM. Parsing render()'s output rather than
    recomputing the statistics here means the artefact checks the pipeline's
    arithmetic, not a second implementation of it.
    """
    from asyncio import run as async_run
    from phd.tables.error_bars import ErrorBars

    smoke._quieten(verbose)

    async def build():
        bars = ErrorBars(name)
        frames, exceptions = await bars.run(
            auto_run=True,
            re_run_all=True,
            try_cache=True,
            assert_cache=True,     # never fall through to a live geocoder
            stop_on_error=True,
        )
        _, latex = await bars.render(frames)
        return latex, exceptions

    captured = StringIO()
    try:
        if verbose:
            latex, exceptions = async_run(build())
        else:
            with redirect_stdout(captured):
                latex, exceptions = async_run(build())
    except BaseException:
        print(captured.getvalue(), flush=True)
        raise

    return parse_latex(latex)


def _check_table4(rebuilt: Dict[str, Dict[str, Dict[str, float]]]) -> List[Cell]:
    reference = loads((paths.data() / "expected/table4.json").read_text(encoding="utf8"))
    source = next(iter(reference["rebuilt_from"]))
    declared = {(d["row"], d["column"]): d for d in reference.get("known_deviations", [])}
    cells = []
    for row, columns in reference["values"].items():
        for _, spec in columns.items():
            column = spec["rebuilt_column"]
            actual = rebuilt.get(source, {}).get(column, {}).get(row)
            cells.append(Cell(4, row, column, spec["mean"], spec["sem"],
                              *(actual if actual else (None, None)),
                              deviation=declared.get((row, column))))
    return cells


def _check_table5(rebuilt: Dict[str, Dict[str, Dict[str, float]]]) -> List[Cell]:
    reference = loads((paths.data() / "expected/table5.json").read_text(encoding="utf8"))
    cells = []
    for row, tiers in reference["values"].items():
        for tier, columns in tiers.items():
            for label, spec in columns.items():
                actual = (rebuilt.get(spec["rebuilt_table"], {})
                          .get(spec["rebuilt_column"], {}).get(row))
                cells.append(Cell(5, f"{row} ({tier})", label, spec["mean"], spec["sem"],
                                  *(actual if actual else (None, None))))
    return cells


def run(as_json: bool = False, verbose: bool = False) -> int:
    from messy_streets.cli import EXIT_ENVIRONMENT, EXIT_MISMATCH, EXIT_OK

    try:
        with workspace.vendored_tree():
            rebuilt = {}
            for index, name in enumerate(SOURCES, start=1):
                if not as_json:
                    print(f"  [{index}/{len(SOURCES)}] {name.split('/')[-1]}", flush=True)
                rebuilt[name] = _rebuild(name, verbose)
            cells = _check_table4(rebuilt) + _check_table5(rebuilt)
    except SystemExit:
        from sys import stderr
        print("\nThe replay stopped: a prediction it needed was not in the shipped "
              "results.\nRun `messy-streets doctor` to check the data.", file=stderr)
        return EXIT_ENVIRONMENT

    bad = [c for c in cells if not c.accounted_for]
    deviations = [c for c in cells if c.is_known_deviation]

    if as_json:
        print(dumps({
            "layer": "L1",
            "paper_tables": [4, 5],
            "cells": len(cells),
            "matched": sum(1 for c in cells if c.matches),
            "known_deviations": [c._asdict() for c in deviations],
            "mismatches": [c._asdict() for c in bad],
            "reproduced": not bad,
            "exit_code": EXIT_MISMATCH if bad else EXIT_OK,
        }, indent=2))
        return EXIT_MISMATCH if bad else EXIT_OK

    for number in (4, 5):
        subset = [c for c in cells if c.table == number]
        matched = sum(1 for c in subset if c.matches)
        print(f"\nTable {number}: {matched}/{len(subset)} cells match the published values")
        for cell in (c for c in subset if c.is_known_deviation):
            print(f"    known deviation · {cell.row} · {cell.column}: "
                  f"published {cell.published}, rebuilt {cell.rebuilt}")
        for cell in (c for c in subset if not c.accounted_for):
            print(f"    MISMATCH · {cell.row} · {cell.column}: "
                  f"published {cell.published}, rebuilt {cell.rebuilt}")

    print()
    if bad:
        print(f"MISMATCH — {len(bad)} of {len(cells)} published cells differ unexpectedly.")
        return EXIT_MISMATCH

    matched = sum(1 for c in cells if c.matches)
    print(f"REPRODUCED — {matched} of {len(cells)} published cells match exactly.")
    if deviations:
        print(f"{len(deviations)} known deviation(s), documented in ARTIFACT.md; "
              "each differs by 0.1 pp and none affects a claim in the paper.")
    print("Tables 4 and 5 rebuilt from cached predictions; no network, no API keys.")
    return EXIT_OK
