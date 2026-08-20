"""Checks that `tables` reproduces the paper, and that it can fail.

These are slower than the other suites — each run replays a large fraction of
420,000 recorded observations — so the expensive reproduction is done once and
the failure cases operate on the parsed reference instead, which is where the
mapping from published cell to rebuilt cell actually lives.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def run_tables(root: Path, timeout: int = 3600):
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO),
           "MS_ROOT": str(root), "HOME": str(root)}
    proc = subprocess.run(
        [sys.executable, "-m", "messy_streets", "tables", "--json"],
        capture_output=True, text=True, env=env, cwd=REPO, timeout=timeout,
    )
    if not proc.stdout.strip():
        raise AssertionError(f"no output; stderr:\n{proc.stderr[-3000:]}")
    return proc.returncode, json.loads(proc.stdout)


class DeviationTest(unittest.TestCase):
    """A declared deviation records a difference; it must not excuse a cell."""

    def setUp(self):
        import messy_streets.tables as tables
        self.tables = tables
        self.declared = {
            "row": "Pelias API", "column": "Found",
            "published_mean": 96.6, "published_sem": 1.8,
            "observed_mean": 96.7, "observed_sem": 1.8, "note": "",
        }

    def cell(self, rebuilt_mean, rebuilt_sem):
        return self.tables.Cell(4, "Pelias API", "Found", 96.6, 1.8,
                                rebuilt_mean, rebuilt_sem, self.declared)

    def test_the_declared_value_is_accounted_for(self):
        cell = self.cell(96.7, 1.8)
        self.assertFalse(cell.matches)
        self.assertTrue(cell.is_known_deviation)
        self.assertTrue(cell.accounted_for)

    def test_matching_the_paper_is_still_a_match(self):
        cell = self.cell(96.6, 1.8)
        self.assertTrue(cell.matches)
        self.assertFalse(cell.is_known_deviation)

    def test_a_third_value_still_fails(self):
        """The point of declaring it: drifting further must not pass."""
        cell = self.cell(91.0, 1.8)
        self.assertFalse(cell.accounted_for)

    def test_a_changed_error_bar_still_fails(self):
        cell = self.cell(96.7, 9.9)
        self.assertFalse(cell.accounted_for)

    def test_an_undeclared_cell_has_no_leniency(self):
        cell = self.tables.Cell(4, "Google Maps API v3", "Found", 100.0, 0.0, 99.0, 0.0)
        self.assertFalse(cell.accounted_for)


class ReferenceTest(unittest.TestCase):
    """The published values, and how they map onto the rebuilt tables."""

    def setUp(self):
        self.table4 = json.loads((REPO / "data/expected/table4.json").read_text())
        self.table5 = json.loads((REPO / "data/expected/table5.json").read_text())

    def test_table4_covers_every_geocoder(self):
        self.assertEqual(len(self.table4["values"]), 12)
        for row, columns in self.table4["values"].items():
            self.assertEqual(set(columns), {"CRR", "GH1", "GH4", "GH6"}, row)

    def test_table4_matches_the_paper(self):
        """Spot-check against values read directly from the published PDF."""
        published = {
            "Google Maps API v3": {"CRR": (100.0, 0.0), "GH6": (88.3, 2.0)},
            "Nominatim API": {"CRR": (68.2, 4.3), "GH4": (66.6, 4.7)},
            "Komoot Photon API": {"CRR": (88.1, 1.0), "GH6": (62.8, 2.5)},
        }
        for row, columns in published.items():
            for column, (mean, sem) in columns.items():
                cell = self.table4["values"][row][column]
                self.assertEqual((cell["mean"], cell["sem"]), (mean, sem), f"{row}/{column}")

    def test_table5_divergence_naming_is_inverted(self):
        """High divergence means LOW trigram overlap. Easy to get backwards."""
        for row, tiers in self.table5["values"].items():
            for tier, columns in tiers.items():
                self.assertIn("low-trigrams", columns["High divergence GH6"]["rebuilt_table"])
                self.assertIn("high-trigrams", columns["Low divergence GH6"]["rebuilt_table"])

    def test_table5_shows_the_divergence_effect(self):
        """The paper's claim: accuracy falls as addresses diverge from canonical."""
        for row, tiers in self.table5["values"].items():
            for tier, columns in tiers.items():
                high = columns["High divergence GH6"]["mean"]
                low = columns["Low divergence GH6"]["mean"]
                self.assertLess(high, low, f"{row}/{tier}: GH6 should be worse when divergent")

    def test_open_source_geocoders_lose_more(self):
        """The paper's headline: Google loses ~9pp, Nominatim ~25pp."""
        values = self.table5["values"]
        def spread(row, tier):
            columns = values[row][tier]
            return columns["Low divergence GH6"]["mean"] - columns["High divergence GH6"]["mean"]
        self.assertLess(spread("Google Maps API v3", "silver"),
                        spread("Nominatim API", "silver"))


class ReproductionTest(unittest.TestCase):
    """The expensive one. Skipped unless MS_SLOW_TESTS=1."""

    @classmethod
    def setUpClass(cls):
        import os
        if os.environ.get("MS_SLOW_TESTS") != "1":
            raise unittest.SkipTest("set MS_SLOW_TESTS=1 to run the full rebuild")
        cls.root = Path(tempfile.mkdtemp(prefix="ms-tables-"))
        for item in ("src", "data"):
            shutil.copytree(REPO / item, cls.root / item,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copy(REPO / "requirements.txt", cls.root / "requirements.txt")
        cls.code, cls.report = run_tables(cls.root)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "root"):
            shutil.rmtree(cls.root, ignore_errors=True)

    def test_reproduces_every_published_cell(self):
        self.assertEqual(self.code, 0, self.report.get("mismatches"))
        self.assertTrue(self.report["reproduced"])
        self.assertEqual(self.report["mismatches"], [])

    def test_covers_both_paper_tables(self):
        self.assertEqual(self.report["paper_tables"], [4, 5])
        self.assertEqual(self.report["cells"], 48 + 32)

    def test_only_the_declared_deviations_deviate(self):
        """78 exact, and the 2 that are not are the ones we said would not be."""
        self.assertEqual(self.report["matched"], 78)
        deviating = {(d["row"], d["column"]) for d in self.report["known_deviations"]}
        self.assertEqual(deviating, {
            ("Pelias API", "Found"),
            ("Pelias API", "Geohash 1 (+/- 2'500 km)"),
        })


if __name__ == "__main__":
    unittest.main(verbosity=2)
