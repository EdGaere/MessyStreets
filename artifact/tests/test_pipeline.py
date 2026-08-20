"""Checks for `pipeline` — the construction-stage catalogue and its two checks."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def run(*args):
    proc = subprocess.run(
        [sys.executable, "-m", "messy_streets", "pipeline", *args, "--json"],
        capture_output=True, text=True, cwd=REPO,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO), "HOME": str(REPO)})
    if not proc.stdout.strip():
        raise AssertionError(f"no output; stderr:\n{proc.stderr[-2000:]}")
    return proc.returncode, json.loads(proc.stdout)


class CatalogueTest(unittest.TestCase):

    def setUp(self):
        self.code, self.report = run()

    def test_fifteen_stages_numbered_in_order(self):
        self.assertEqual([s["n"] for s in self.report["stages"]], list(range(1, 16)))

    def test_every_stage_records_what_it_needs(self):
        for stage in self.report["stages"]:
            for field in ("title", "code", "inputs", "outputs", "scale", "needs", "runnable"):
                self.assertTrue(stage.get(field) not in (None, "", []), f"{stage['n']}/{field}")

    def test_the_stages_that_produce_paper_tables_say_so(self):
        verifies = {s["n"]: s.get("verifies") for s in self.report["stages"]}
        self.assertIn("Table 2", verifies[3])
        self.assertIn("Table 3", verifies[11])
        self.assertIn("Tables 4 and 5", verifies[14])


class Table2Test(unittest.TestCase):
    """Stage 3's statistics file is Table 2."""

    def setUp(self):
        self.code, self.report = run("show", "3")

    def test_every_published_cell_matches(self):
        self.assertEqual(self.code, 0)
        self.assertTrue(self.report["table2"]["matches"])
        self.assertEqual(self.report["table2"]["mismatches"], [])

    def test_all_nine_rows_are_checked(self):
        self.assertEqual(len(self.report["table2"]["cells"]), 9)

    def test_the_totals_are_internally_consistent(self):
        cells = {c["row"]: c["recorded"] for c in self.report["table2"]["cells"]}
        removed = sum(v for k, v in cells.items()
                      if k not in ("Total removed", "Retained records"))
        self.assertEqual(removed, cells["Total removed"])


class DisjointnessTest(unittest.TestCase):
    """Stage 9's purpose, checked on the shipped tier databases."""

    def setUp(self):
        self.code, self.report = run("show", "9")

    def test_all_three_tiers_are_shipped(self):
        self.assertEqual(self.report["disjointness"]["tiers_available"], 3)

    def test_the_tiers_are_disjoint(self):
        """The paper's claim. Verified directly rather than taken on trust."""
        self.assertTrue(self.report["disjointness"]["report"]["disjoint"])

    def test_each_tier_holds_exactly_ten_thousand_records(self):
        for tier in self.report["disjointness"]["report"]["tiers"]:
            self.assertEqual(tier["records"], 10000, tier["tier"])
            self.assertEqual(tier["duplicates"], 0, tier["tier"])
            self.assertEqual(tier["overlapping_with_higher_tier"], 0, tier["tier"])


class RepairScriptTest(unittest.TestCase):

    def test_apply_is_guarded_against_the_released_tiers(self):
        """Re-running the repair would produce a different tier from the paper's."""
        script = REPO / "pipeline/09-disjointness/repair.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--data-dir", str(REPO / "data/tiers_duckdb"), "--apply"],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, "already-repaired tiers need no changes")

    def test_reports_without_writing(self):
        script = REPO / "pipeline/09-disjointness/repair.py"
        before = (REPO / "data/tiers_duckdb/hq_10000").stat().st_mtime
        subprocess.run([sys.executable, str(script), "--data-dir",
                        str(REPO / "data/tiers_duckdb")], capture_output=True)
        self.assertEqual((REPO / "data/tiers_duckdb/hq_10000").stat().st_mtime, before)



class CroissantTest(unittest.TestCase):
    """The dataset descriptor must describe what is actually distributed."""

    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads((REPO / "croissant.json").read_text())

    def test_describes_all_three_tiers(self):
        names = {f["name"] for f in self.doc["distribution"]}
        self.assertEqual(names, {"gold-tier", "silver-tier", "raw-tier"})

    def test_checksums_match_the_shipped_files(self):
        from hashlib import sha256
        for entry in self.doc["distribution"]:
            path = REPO / entry["contentUrl"]
            self.assertTrue(path.is_file(), entry["contentUrl"])
            self.assertEqual(sha256(path.read_bytes()).hexdigest(), entry["sha256"],
                             entry["name"])

    def test_validates_against_mlcroissant(self):
        from mlcroissant import Dataset
        Dataset(jsonld=str(REPO / "croissant.json"))

    def test_licence_names_all_three_origins(self):
        """A machine reading only the metadata must still see the ODbL obligation."""
        licence = self.doc["license"].lower()
        for origin in ("mit", "odbl", "openaddresses", "web data commons"):
            self.assertIn(origin, licence, origin)

    def test_attribution_credits_openstreetmap(self):
        credit = self.doc["creditText"]
        self.assertIn("OpenStreetMap contributors", credit)
        self.assertIn("openstreetmap.org/copyright", credit)

    def test_the_licence_files_exist_and_are_not_placeholders(self):
        for name in ("LICENSE", "LICENSE-DATA"):
            text = (REPO / name).read_text()
            self.assertNotIn("NOT YET CHOSEN", text, name)
            self.assertGreater(len(text), 500, name)
        self.assertIn("MIT License", (REPO / "LICENSE").read_text())
        self.assertIn("ODbL", (REPO / "LICENSE-DATA").read_text())


class AuditTest(unittest.TestCase):
    """Nothing vendored for one function and forgotten; nothing missing."""

    def test_the_vendored_tree_is_exactly_what_is_reachable(self):
        proc = subprocess.run([sys.executable, str(REPO / "tools/audit.py"), "--json"],
                              capture_output=True, text=True, cwd=REPO)
        report = json.loads(proc.stdout)
        self.assertEqual(report["missing"], [], "reachable but absent from src/")
        self.assertEqual(report["unreachable"], [], "vendored but unreachable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
