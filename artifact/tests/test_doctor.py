"""Checks that `doctor` can actually fail.

A doctor that always passes is worse than no doctor: it converts an unverified
environment into a green tick. Each test here breaks something on purpose and
asserts that it is caught and named.

Stdlib only, matching the CLI.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run_doctor(root: Path, extra_env=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO)
    env["MS_ROOT"] = str(root)
    env.update(extra_env or {})
    proc = subprocess.run(
        [sys.executable, "-m", "messy_streets", "doctor", "--json"],
        capture_output=True, text=True, env=env, cwd=REPO,
    )
    return proc.returncode, json.loads(proc.stdout)


def status_of(report, group, name=None):
    for check in report["checks"]:
        if check["group"] == group and (name is None or check["name"] == name):
            return check
    return None


class DoctorTest(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        for name in ("messy_streets", "src", "data"):
            (self.tmp / name).mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / "requirements.txt", self.tmp / "requirements.txt")

    # --- the healthy case, so the failures below mean something -------------

    def test_clean_environment_passes(self):
        code, report = run_doctor(self.tmp)
        self.assertEqual(code, 0, report["summary"])
        self.assertEqual(report["summary"]["failed"], 0)

    # --- dependency pins ----------------------------------------------------

    def test_wrong_version_fails(self):
        text = (self.tmp / "requirements.txt").read_text()
        (self.tmp / "requirements.txt").write_text(
            text.replace("duckdb==1.4.4", "duckdb==9.9.9"))
        code, report = run_doctor(self.tmp)
        self.assertEqual(code, 2)
        self.assertEqual(status_of(report, "dependencies", "duckdb")["status"], "fail")

    def test_missing_package_fails(self):
        with (self.tmp / "requirements.txt").open("a") as handle:
            handle.write("\nnot-a-real-package==1.0.0\n")
        code, report = run_doctor(self.tmp)
        self.assertEqual(code, 2)
        self.assertIn("not installed",
                      status_of(report, "dependencies", "not-a-real-package")["detail"])

    def test_missing_requirements_fails(self):
        (self.tmp / "requirements.txt").unlink()
        code, report = run_doctor(self.tmp)
        self.assertEqual(code, 2)
        self.assertEqual(status_of(report, "dependencies")["status"], "fail")

    # --- data integrity -----------------------------------------------------

    def _manifest(self, payload=b"reference"):
        """Manifest paths are repository-root relative, so the one file the
        artefact ships under data/ and the results it ships under src/ can sit
        in the same manifest."""
        from hashlib import sha256
        (self.tmp / "data" / "probe.bin").write_bytes(payload)
        digest = sha256(payload).hexdigest()
        (self.tmp / "data" / "CHECKSUMS.sha256").write_text(f"{digest}  data/probe.bin\n")

    def test_intact_data_passes(self):
        self._manifest()
        code, report = run_doctor(self.tmp)
        self.assertEqual(code, 0)
        self.assertEqual(status_of(report, "data", "checksums")["status"], "ok")

    def test_modified_data_fails(self):
        self._manifest()
        (self.tmp / "data" / "probe.bin").write_bytes(b"tampered")
        code, report = run_doctor(self.tmp)
        self.assertEqual(code, 2)
        self.assertIn("modified", status_of(report, "data", "checksums")["detail"])

    def test_missing_data_fails(self):
        self._manifest()
        (self.tmp / "data" / "probe.bin").unlink()
        code, report = run_doctor(self.tmp)
        self.assertEqual(code, 2)
        self.assertIn("missing", status_of(report, "data", "checksums")["detail"])

    # --- environment pins are warnings, never failures ----------------------

    def test_unpinned_environment_warns_but_passes(self):
        env = {k: "" for k in ("TZ", "LANG", "PYTHONHASHSEED", "MS_DUCKDB_THREADS")}
        for key in list(env):
            env.pop(key)
        code, report = run_doctor(self.tmp, extra_env=env)
        self.assertEqual(code, 0, "missing env pins must not block a native run")

    def test_pinned_environment_is_clean(self):
        code, report = run_doctor(self.tmp, extra_env={
            "TZ": "UTC", "LANG": "C.UTF-8",
            "PYTHONHASHSEED": "0", "MS_DUCKDB_THREADS": "1",
        })
        self.assertEqual(code, 0)
        for name in ("TZ", "LANG", "PYTHONHASHSEED", "MS_DUCKDB_THREADS"):
            self.assertEqual(status_of(report, "environment", name)["status"], "ok", name)


class CommandTableTest(unittest.TestCase):
    """The wrapper reads verbs.tsv for its --network decision."""

    def test_table_is_well_formed(self):
        sys.path.insert(0, str(REPO))
        from messy_streets import verbs
        table = verbs.load()
        self.assertTrue(table)
        for verb in table.values():
            self.assertIn(verb.network, {"none", "host", "host-side"}, verb)
            self.assertIn(verb.layer, {"-", "L0", "L1", "L2", "L3", "L4"}, verb)
            self.assertGreater(verb.slice, 0, verb)

    def test_only_geocode_needs_the_network(self):
        sys.path.insert(0, str(REPO))
        from messy_streets import verbs
        networked = [v.name for v in verbs.load().values() if v.needs_network]
        self.assertEqual(networked, ["geocode"])

    def test_only_credentials_runs_outside_the_container(self):
        """It writes a file the container is deliberately unable to reach."""
        sys.path.insert(0, str(REPO))
        from messy_streets import verbs
        host_side = [v.name for v in verbs.load().values() if v.host_side]
        self.assertEqual(host_side, ["credentials"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
