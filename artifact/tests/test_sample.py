"""Checks for `sample` — slice provenance against the tier database."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def run_sample():
    proc = subprocess.run(
        [sys.executable, "-m", "messy_streets", "sample", "--json"],
        capture_output=True, text=True, cwd=REPO,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO), "HOME": str(REPO)})
    if not proc.stdout.strip():
        raise AssertionError(f"no output; stderr:\n{proc.stderr[-2000:]}")
    return proc.returncode, json.loads(proc.stdout)


class SampleTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.code, cls.report = run_sample()

    def test_every_slice_record_traces_to_the_tier(self):
        self.assertEqual(self.code, 0, self.report.get("problems"))
        self.assertEqual(self.report["problems"], [])

    def test_all_thirty_slices_are_checked(self):
        self.assertEqual(self.report["slices"], 30)
        self.assertEqual(self.report["records_checked"], 15000)

    def test_the_absent_records_are_the_declared_ones(self):
        declared = json.loads((REPO / "data/expected/slice-provenance.json").read_text())
        self.assertEqual({r["record_id"] for r in self.report["known_absent"]},
                         {r["id"] for r in declared["records"]})


class RegenerationTest(unittest.TestCase):
    """Why bit-identical regeneration is not offered."""

    def setUp(self):
        import duckdb
        self.duckdb = duckdb
        self.path = str(REPO / "data/tiers_duckdb/hq_10000")

    def draw(self, threads):
        connection = self.duckdb.connect(self.path, read_only=True)
        connection.execute(f"SET threads TO {threads}")
        return [r[0] for r in connection.execute(
            "SELECT id FROM addresses USING SAMPLE reservoir(500 ROWS) REPEATABLE(42)").fetchall()]

    def test_sampling_is_not_thread_sensitive(self):
        """The determinism worry that turned out not to apply to this version.

        If a future DuckDB makes reservoir sampling depend on thread count,
        this fails and the thread pin becomes load-bearing again.
        """
        self.assertEqual(self.draw(1), self.draw(8))

    def test_sampling_is_stable_within_a_version(self):
        self.assertEqual(self.draw(1), self.draw(1))

    def test_the_pinned_version_does_not_redraw_the_shipped_slice(self):
        """Documents the actual blocker: the sample differs across versions."""
        import gzip
        path = REPO / "src/phd/benchmarks/messy_streets/release_gold_geohash1_1/benchmark.jsonl.gz"
        shipped = {json.loads(l)["id"] for l in gzip.open(path, "rt", encoding="utf8") if l.strip()}
        redrawn = set(self.draw(1))
        overlap = len(shipped & redrawn)
        self.assertLess(overlap, len(shipped) // 2,
                        "the pinned DuckDB now reproduces the shipped sample — "
                        "if so, bit-identical regeneration can be offered after all")



class ShippedDatabaseTest(unittest.TestCase):
    """The tier databases must carry the released addresses and nothing else.

    The research copies also hold a `discarded` table — every rejected
    candidate with the reason it was rejected, including the records the PII
    judge removed — plus backup, deleted and replacements. Publishing those
    would publish exactly what the privacy filter took out.
    """

    def databases(self):
        import duckdb
        for name in ("hq_10000", "mq_10000", "lq_10000"):
            path = REPO / "data/tiers_duckdb" / name
            self.assertTrue(path.is_file(), name)
            yield name, duckdb.connect(str(path), read_only=True)

    def test_only_the_addresses_table_is_shipped(self):
        for name, connection in self.databases():
            tables = sorted(r[0] for r in connection.execute("SHOW TABLES").fetchall())
            self.assertEqual(tables, ["addresses"], f"{name} ships {tables}")

    def test_each_tier_holds_its_ten_thousand_records(self):
        for name, connection in self.databases():
            count = connection.execute("SELECT COUNT(*) FROM addresses").fetchone()[0]
            self.assertEqual(count, 10000, name)

    def test_no_rejected_candidates_are_reachable(self):
        """Belt and braces: the discard reasons must not appear anywhere."""
        for name, connection in self.databases():
            with self.assertRaises(Exception, msg=f"{name} still has a discarded table"):
                connection.execute("SELECT COUNT(*) FROM discarded").fetchone()


if __name__ == "__main__":
    unittest.main(verbosity=2)
