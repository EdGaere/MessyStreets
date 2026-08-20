"""Checks for `geocode` — the one verb CI cannot exercise end to end.

Everything except the HTTP calls is testable, and is: the provider registry,
credential detection, the opt-in guard, and the call-volume arithmetic. The
live path is exercised by hand against the three providers that need no
credential; there is no way to assert on a third-party service in CI without
making the suite depend on it being up.
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

CREDENTIALS = ["GEOCODE_EARTH_API_KEY", "GOOGLE_MAPS_API_KEY", "HERE_API_KEY",
               "MAPBOX_API_KEY", "AZURE_MAPS_API_KEY", "OPENCAGE_API_KEY",
               "TOMTOM_API_KEY", "GEOAPIFY_MAPS_API_KEY", "MAPQUEST_API_KEY"]


def run(*args, env=None):
    environment = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO), "HOME": str(REPO)}
    environment.update(env or {})
    proc = subprocess.run(
        [sys.executable, "-m", "messy_streets", "geocode", *args, "--json"],
        capture_output=True, text=True, cwd=REPO, env=environment)
    if not proc.stdout.strip():
        raise AssertionError(f"no output; stderr:\n{proc.stderr[-2000:]}")
    return proc.returncode, json.loads(proc.stdout)


class RegistryTest(unittest.TestCase):

    def test_twelve_providers(self):
        from messy_streets.geocode import PROVIDERS
        self.assertEqual(len(PROVIDERS), 12)

    def test_exactly_three_need_no_credential(self):
        """Nominatim, Photon and ArcGIS. The paper's findings are about the first two."""
        from messy_streets.geocode import PROVIDERS
        free = {name for name, (_, credential, _) in PROVIDERS.items() if credential is None}
        self.assertEqual(free, {"nominatim", "photon", "arcgis"})

    def test_nine_credentials_are_needed_in_total(self):
        from messy_streets.geocode import PROVIDERS
        needed = {credential for _, credential, _ in PROVIDERS.values() if credential}
        self.assertEqual(needed, set(CREDENTIALS))

    def test_every_provider_is_vendored(self):
        from messy_streets.geocode import PROVIDERS
        for name in PROVIDERS:
            self.assertTrue((REPO / f"src/phd/models/models/{name}/model.py").is_file(), name)

    def test_every_provider_has_a_geohash1_config(self):
        from messy_streets.geocode import PROVIDERS
        for name in PROVIDERS:
            self.assertTrue((REPO / f"src/phd/models/models/{name}/configs/geohash1.hjson").is_file(), name)


class PlanTest(unittest.TestCase):

    def test_nothing_runs_without_the_opt_in(self):
        code, report = run()
        self.assertEqual(code, 0)
        self.assertFalse(report["opt_in_given"])
        self.assertFalse(report["would_run"])

    def test_credential_detection(self):
        code, report = run("--provider", "here", env={"HERE_API_KEY": "x"})
        self.assertEqual(report["configured"], ["here"])
        code, report = run("--provider", "here")
        self.assertEqual(report["configured"], [])
        self.assertEqual(report["missing_credentials"], {"here": "HERE_API_KEY"})

    def test_keyless_providers_are_always_configured(self):
        for name in ("nominatim", "photon", "arcgis"):
            _, report = run("--provider", name)
            self.assertEqual(report["configured"], [name])

    def test_call_volume_matches_the_paper(self):
        """12 providers x 10 runs x 100 addresses x 4 precisions."""
        _, report = run()
        self.assertEqual(report["total_calls"], 12 * 10 * 100 * 4)

    def test_volume_scales_with_the_requested_size(self):
        _, report = run("--provider", "nominatim", "--runs", "2", "--observations", "50")
        self.assertEqual(report["total_calls"], 2 * 50 * 4)

    def test_unknown_provider_is_refused(self):
        proc = subprocess.run(
            [sys.executable, "-m", "messy_streets", "geocode", "--provider", "yahoo"],
            capture_output=True, text=True, cwd=REPO,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO), "HOME": str(REPO)})
        self.assertEqual(proc.returncode, 3)
        self.assertIn("unknown provider", proc.stdout)

    def test_the_drift_warning_is_always_present(self):
        _, report = run()
        self.assertIn("will not match the paper", report["note"].lower())


class RecordedPredictionsTest(unittest.TestCase):
    """Drift is measured against what each provider answered in June 2026."""

    def test_every_provider_has_recorded_predictions(self):
        from messy_streets.geocode import PROVIDERS, recorded_predictions
        for name in PROVIDERS:
            recorded = recorded_predictions(name, "geohash1", 1)
            self.assertIsNotNone(recorded, name)
            self.assertEqual(len(recorded), 100, name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
