"""smoke — rebuild one table from cached predictions and check it.

The thinnest thing that exercises the whole stack: the vendored closure, the
benchmark loader, the comparator, the table builder, and the offline replay
path. Nothing here talks to a geocoder; every prediction comes from the results
recorded when the paper's experiments were run.

What it verifies is the *machinery*. The numbers it checks are the intermediate
per-run values behind Table 4, not the published means — those are ten runs
aggregated, which is what `tables` does.
"""

from contextlib import redirect_stdout
from io import StringIO
from json import dumps, loads
from logging import DEBUG, ERROR, Handler, getLogger
from typing import Dict, List, NamedTuple

from messy_streets import paths, workspace

TABLE = "messy_streets/release-gold-2/run1"
EXPECTED = "expected/release-gold-2-run1.json"

# Rebuilt values are floats produced by a different code path from the ones
# recorded in the reference, so compare at the precision the table is rendered
# at rather than for bit equality.
TOLERANCE = 5e-4


class Cell(NamedTuple):
    row: str
    column: str
    expected: float
    actual: float

    @property
    def matches(self) -> bool:
        if self.actual is None or self.expected is None:
            return self.actual == self.expected
        return abs(self.actual - self.expected) <= TOLERANCE


class _Recorder(Handler):
    """Holds the pipeline's log records so they can be shown if it fails.

    Silence is right while a verification is passing and wrong the moment it
    is not: the reason a replay stopped is in a warning the quiet mode hides.
    """

    def __init__(self) -> None:
        super().__init__(level=DEBUG)
        self.records: List[str] = []

    def emit(self, record) -> None:
        self.records.append(self.format(record))


def _quieten(verbose: bool) -> _Recorder:
    """Turn down the vendored pipeline's logging.

    It logs every observation at debug level and attaches its own handler at
    import time — useful when it was a research tool, noise when it is a
    verification step. Both the logger and its handler have to be lowered, and
    it has to happen after the import that installs them. --verbose puts it
    back.
    """
    recorder = _Recorder()
    logger = getLogger("serentec")
    logger.addHandler(recorder)
    if verbose:
        return recorder
    # ERROR, not WARNING, on the console: the pipeline warns on every
    # experiment it overwrites, which is exactly what a rebuild does. The
    # recorder still keeps everything, in case it is needed.
    logger.setLevel(DEBUG)
    for handler in logger.handlers:
        if handler is not recorder:
            handler.setLevel(ERROR)
    return recorder


def _rebuild(verbose: bool) -> Dict[str, Dict[str, float]]:
    from asyncio import run as async_run
    from phd.tables.build_table import BuildTable

    # After the import: serentec installs its handler at import time.
    recorder = _quieten(verbose)

    async def build():
        table = BuildTable(TABLE)
        _, frame, exceptions = await table.run(
            auto_run=True,        # run any experiment that has no result yet
            re_run_all=True,      # rebuild rather than reading a stale result
            try_cache=True,       # replay recorded predictions
            assert_cache=True,    # ... and never fall through to a live API
            stop_on_error=True,
        )
        return frame, exceptions

    # build_table prints its working as it goes; keep it unless asked for it.
    # On failure the captured output and the log are the only explanation the
    # reviewer gets, so both are released before the error propagates. The
    # pipeline calls exit() on a hard stop, so BaseException, not Exception.
    captured = StringIO()
    try:
        if verbose:
            frame, exceptions = async_run(build())
        else:
            with redirect_stdout(captured):
                frame, exceptions = async_run(build())
    except BaseException:
        _release(captured, recorder)
        raise

    if exceptions:
        raise RuntimeError(f"table build reported exceptions: {exceptions}")
    return loads(frame.to_json())


def _release(captured: StringIO, recorder: "_Recorder") -> None:
    """Show what the pipeline said, now that it matters."""
    from sys import stderr

    text = captured.getvalue().strip()
    if text:
        print(text, file=stderr)
    for line in recorder.records[-25:]:
        print(line, file=stderr)


def compare(work, verbose: bool) -> List[Cell]:
    reference = loads((paths.data() / EXPECTED).read_text(encoding="utf8"))

    actual = _rebuild(verbose)

    cells = []
    for column, rows in reference["values"].items():
        for row, expected in rows.items():
            cells.append(Cell(row, column, expected, actual.get(column, {}).get(row)))
    return cells


def run(as_json: bool = False, verbose: bool = False) -> int:
    from messy_streets.cli import EXIT_MISMATCH, EXIT_OK

    from messy_streets.cli import EXIT_ENVIRONMENT

    try:
        with workspace.vendored_tree() as work:
            cells = compare(work, verbose)
    except SystemExit:
        # The pipeline stopped rather than reaching a live API — a cached
        # prediction it needed was absent. That is a data-integrity problem.
        print("\nThe replay stopped: a prediction it needed was not in the "
              "shipped results.\nRun `messy-streets doctor` to check the data.",
              file=__import__("sys").stderr)
        return EXIT_ENVIRONMENT

    bad = [c for c in cells if not c.matches]

    if as_json:
        print(dumps({
            "table": TABLE,
            "layer": "L1",
            "cells": len(cells),
            "mismatches": [c._asdict() for c in bad],
            "reproduced": not bad,
            "exit_code": EXIT_MISMATCH if bad else EXIT_OK,
        }, indent=2))
        return EXIT_MISMATCH if bad else EXIT_OK

    columns = sorted({c.column for c in cells}, key=lambda name: (name != "Found", name))
    rows = list(dict.fromkeys(c.row for c in cells))
    lookup = {(c.row, c.column): c for c in cells}

    print(f"\nTable 4, run 1 of 10 — gold tier, {len(rows)} geocoders, 100 addresses each")
    print("replayed from cached predictions; no network, no API keys\n")

    width = max(len(r) for r in rows) + 2
    header = f"  {'geocoder':<{width}}" + "".join(f"{c[:9]:>12}" for c in columns)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for row in rows:
        line = f"  {row:<{width}}"
        for column in columns:
            cell = lookup[(row, column)]
            value = "—" if cell.actual is None else f"{100 * cell.actual:.1f}"
            line += f"{value + ('' if cell.matches else ' ✗'):>12}"
        print(line)

    print()
    if bad:
        print(f"MISMATCH — {len(bad)} of {len(cells)} cells differ from the published run:")
        for cell in bad:
            got = "missing" if cell.actual is None else f"{100 * cell.actual:.1f}"
            print(f"  {cell.row} · {cell.column}: expected {100 * cell.expected:.1f}, got {got}")
        return EXIT_MISMATCH

    print(f"REPRODUCED — {len(cells)} of {len(cells)} cells match the published run.")
    print("Run `messy-streets tables` for the published means over all 10 runs.")
    return EXIT_OK
