"""Checks for `stats` and `inspect` — the released-tier verbs.

The interesting assertions here are about honesty rather than reproduction:
Table 3 cannot be reproduced from the released tiers, and the tests pin down
exactly why so the discrepancy cannot quietly disappear.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def run(verb, *args):
    proc = subprocess.run(
        [sys.executable, "-m", "messy_streets", verb, "--json", *args],
        capture_output=True, text=True, cwd=REPO,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO), "HOME": str(REPO)},
    )
    if not proc.stdout.strip():
        raise AssertionError(f"no output; stderr:\n{proc.stderr[-2000:]}")
    return proc.returncode, json.loads(proc.stdout)


class TierTest(unittest.TestCase):

    def test_every_tier_has_ten_thousand_records(self):
        from messy_streets import tiers
        for tier in tiers.TIERS:
            self.assertEqual(sum(1 for _ in tiers.read(tier)), 10000, tier)

    def test_every_record_has_a_street(self):
        """The one requirement common to all three tiers."""
        from messy_streets import tiers
        for tier in tiers.TIERS:
            missing = [r for r in tiers.read(tier)
                       if not tiers.present(tiers.address(r).get("streetAddress"))]
            self.assertEqual(missing, [], f"{tier}: {len(missing)} records without a street")

    def test_gold_and_silver_are_existence_verified(self):
        from messy_streets import tiers
        for tier in ("gold", "silver"):
            for record in tiers.read(tier):
                self.assertIn("existence", record["aux"], tier)
                self.assertIn(record["aux"]["existence"]["source"], ("oa", "osd"))

    def test_raw_is_not_existence_verified(self):
        from messy_streets import tiers
        self.assertFalse(any("existence" in r["aux"] for r in tiers.read("raw")))

    def test_bare_nan_parses(self):
        """A documented deviation: the files are not strict RFC 8259."""
        from messy_streets import tiers
        record = next(tiers.read("silver"))
        self.assertIsInstance(record, dict)


class StatsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.code, cls.report = run("stats")

    def test_succeeds(self):
        self.assertEqual(self.code, 0)

    def test_reports_all_fifteen_cells(self):
        self.assertEqual(len(self.report["component_existence"]), 15)

    def test_street_is_universal_in_every_tier(self):
        for row in self.report["component_existence"]:
            if row["component"] == "Street":
                self.assertEqual(row["released"], 100.0, row["tier"])

    def test_gold_has_every_component_the_paper_claims(self):
        """Gold is verified for street, country and postcode by construction."""
        for row in self.report["component_existence"]:
            if row["tier"] == "gold" and row["component"] in ("Street", "Country", "Postcode"):
                self.assertEqual(row["released"], 100.0, row["component"])

    def test_the_paper_disagrees_with_its_own_analysis(self):
        """Six cells. Pinned so the finding cannot silently vanish."""
        disagreements = {(d["tier"], d["component"])
                         for d in self.report["paper_vs_its_own_analysis"]}
        self.assertEqual(disagreements, {
            ("raw", "Street"), ("raw", "Country"), ("raw", "Postcode"),
            ("raw", "Locality"), ("raw", "Region"), ("silver", "Locality"),
        })

    def test_method_note_records_the_sampling(self):
        note = self.report["method_note"]
        self.assertIn("1,000", note)
        self.assertIn("mq_1000", note)

    def test_latin_script_shares_match_the_paper(self):
        """98% gold, 96% silver, 94% raw, to the precision the paper prints."""
        for tier, expected in (("gold", 98), ("silver", 96), ("raw", 94)):
            latin = self.report["distributions"][tier]["script"]["Latin"]
            self.assertEqual(round(latin), expected, f"{tier}: {latin}")


class InspectTest(unittest.TestCase):

    def test_returns_the_requested_count(self):
        code, report = run("inspect", "--tier", "gold", "-n", "3")
        self.assertEqual(code, 0)
        self.assertEqual(report["count"], 3)

    def test_filters_by_content(self):
        code, report = run("inspect", "--tier", "gold", "-n", "5", "--contains", "France")
        self.assertEqual(code, 0)
        for record in report["records"]:
            self.assertIn("france", record["input"].lower())

    def test_filters_by_missing_component(self):
        code, report = run("inspect", "--tier", "silver", "-n", "5", "--missing", "country")
        self.assertEqual(code, 0)
        self.assertTrue(report["records"], "silver should have records without a country")
        from messy_streets import tiers
        for record in report["records"]:
            self.assertFalse(tiers.present(record["aux"]["address"].get("addressCountry")))

    def test_rejects_an_unknown_tier(self):
        proc = subprocess.run(
            [sys.executable, "-m", "messy_streets", "inspect", "--tier", "platinum"],
            capture_output=True, text=True, cwd=REPO,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO), "HOME": str(REPO)})
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
