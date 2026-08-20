"""Checks that `smoke` reproduces, and that it can fail.

The point of a verification command is that it says no when the answer is no.
These tests corrupt the inputs in the ways that matter — a changed prediction,
a changed reference, a missing cache entry — and assert that each is caught.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run_smoke(root: Path):
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(REPO),
        "MS_ROOT": str(root),
        "HOME": str(root),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "messy_streets", "smoke", "--json"],
        capture_output=True, text=True, env=env, cwd=REPO,
    )
    if not proc.stdout.strip():
        raise AssertionError(f"no output; stderr:\n{proc.stderr[-2000:]}")
    return proc.returncode, json.loads(proc.stdout)


class SmokeTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """One copy of the repository, reused; each test mutates a fresh clone."""
        cls.pristine = Path(tempfile.mkdtemp(prefix="ms-smoke-pristine-"))
        for item in ("src", "data"):
            shutil.copytree(REPO / item, cls.pristine / item,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copy(REPO / "requirements.txt", cls.pristine / "requirements.txt")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pristine, ignore_errors=True)

    def clone(self) -> Path:
        target = Path(tempfile.mkdtemp(prefix="ms-smoke-"))
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        shutil.copytree(self.pristine, target, dirs_exist_ok=True)
        return target

    # --- the reproduction itself -------------------------------------------

    def test_reproduces(self):
        code, report = run_smoke(self.clone())
        self.assertEqual(code, 0, report.get("mismatches"))
        self.assertTrue(report["reproduced"])
        self.assertEqual(report["cells"], 48)
        self.assertEqual(report["layer"], "L1")

    def test_is_hermetic(self):
        """A run must not modify its own inputs."""
        root = self.clone()
        before = {p: p.read_bytes() for p in sorted((root / "src").rglob("*.json"))}
        run_smoke(root)
        after = {p: p.read_bytes() for p in sorted((root / "src").rglob("*.json"))}
        self.assertEqual(before.keys(), after.keys(), "a run created or removed inputs")
        changed = [str(p.relative_to(root)) for p in before if before[p] != after[p]]
        self.assertEqual(changed, [], "a run modified its own inputs")

    # --- it must be able to say no -----------------------------------------

    def test_changed_prediction_is_caught(self):
        root = self.clone()
        target = (root / "src/phd/experiments/experiments/address"
                  "/messy-streets-release-gold-2/Nominatim-geohash1_found/run1/all_results.json")
        results = json.loads(target.read_text())
        flipped = 0
        for record in results:
            if record.get("prediction") is None:
                record["prediction"] = "9"
                flipped += 1
        self.assertGreater(flipped, 0, "expected some null predictions to flip")
        target.write_text(json.dumps(results))

        code, report = run_smoke(root)
        self.assertEqual(code, 1)
        self.assertFalse(report["reproduced"])
        rows = {m["row"] for m in report["mismatches"]}
        self.assertIn("Nominatim API", rows)

    def test_changed_reference_is_caught(self):
        root = self.clone()
        reference = root / "data/expected/release-gold-2-run1.json"
        doc = json.loads(reference.read_text())
        doc["values"]["Found"]["Google Maps API v3"] = 0.42
        reference.write_text(json.dumps(doc))

        code, report = run_smoke(root)
        self.assertEqual(code, 1)
        self.assertEqual(len(report["mismatches"]), 1)
        self.assertEqual(report["mismatches"][0]["row"], "Google Maps API v3")

    def test_missing_cache_entry_is_not_silently_filled(self):
        """assert_cache must stop a replay, never fall through to a live call.

        Uses the geohash4 column deliberately. The `Found` and `Geohash 1`
        columns run the same model at the same config over the same benchmark
        and differ only in their comparator, so they produce identical cache
        keys and seed each other — corrupting one would not create a gap.
        """
        root = self.clone()
        target = (root / "src/phd/experiments/experiments/address"
                  "/messy-streets-release-gold-2/Google-geohash4/run1/all_results.json")
        results = json.loads(target.read_text())
        for record in results[:5]:
            record["exception"] = "removed for this test"
        target.write_text(json.dumps(results))

        env_root = root
        proc = subprocess.run(
            [sys.executable, "-m", "messy_streets", "smoke"],
            capture_output=True, text=True, cwd=REPO,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO),
                 "MS_ROOT": str(env_root), "HOME": str(env_root)},
        )
        # 2, not 1: an absent prediction is a data-integrity problem, not a
        # disagreement with the published number.
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        combined = (proc.stdout + proc.stderr).lower()
        self.assertIn("cache", combined)
        self.assertIn("doctor", combined, "the failure should point somewhere useful")


if __name__ == "__main__":
    unittest.main(verbosity=2)
