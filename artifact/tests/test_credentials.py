"""Checks for `credentials`, and a standing sweep for secrets in the repository.

The sweep matters more than the verb. Credential files now live next to the
repository by convention rather than by construction, and a convention that is
only checked by hand is checked until someone is in a hurry. It has been run
manually after every change so far; this makes it a test.
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# Shapes of the credentials that were found hardcoded in the research tree,
# plus the generic forms. A hit in this repository is a release blocker.
SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9_-]{20,}",            # OpenAI, Anthropic
    r"r8_[A-Za-z0-9]{20,}",              # Replicate
    r"AIza[A-Za-z0-9_-]{20,}",           # Google
    r"pk\.eyJ[A-Za-z0-9._-]{20,}",       # Mapbox
    r"\bge-[a-f0-9]{16}\b",              # Geocode Earth
    r"\bhf_[A-Za-z0-9]{20,}",            # Hugging Face
    r"\bxai-[A-Za-z0-9]{20,}",           # xAI
    r"[A-Z_]*(API_KEY|TOKEN|PASSWORD)[A-Z_]*\s*=\s*['\"]?[A-Za-z0-9_.+/-]{16,}",
    r"['\"]?(pwd|password|passwd)['\"]?\s*[:=]\s*['\"][^'\"]{6,}['\"]",
]


class SecretSweepTest(unittest.TestCase):

    def test_no_secrets_anywhere_in_the_repository(self):
        """Every tracked file, including the vendored tree and the tools."""
        pattern = "|".join(SECRET_PATTERNS)
        proc = subprocess.run(
            ["grep", "-rInE", "--exclude-dir=.git", pattern, "."],
            capture_output=True, text=True, cwd=REPO)
        hits = [line for line in proc.stdout.splitlines()
                # This test file necessarily contains the patterns it looks for.
                if not line.startswith("./tests/test_credentials.py")
                # And the vendoring tool defines them for the same reason.
                and not line.startswith("./tools/vendor.py")]
        self.assertEqual(hits, [], "secrets found:\n" + "\n".join(hits))

    def test_a_filled_credentials_file_cannot_be_committed_by_accident(self):
        for name in ("credentials_edward.hjson", "credentials.local.hjson",
                     "credentials_prod.hjson", ".env"):
            proc = subprocess.run(["git", "check-ignore", name],
                                  capture_output=True, text=True, cwd=REPO)
            self.assertEqual(proc.returncode, 0, f"{name} is NOT gitignored")

    def test_the_template_itself_stays_tracked(self):
        proc = subprocess.run(["git", "check-ignore", "credentials.hjson"],
                              capture_output=True, text=True, cwd=REPO)
        self.assertEqual(proc.returncode, 1, "the template must remain committable")

    def test_the_shipped_template_holds_no_values(self):
        import hjson
        with (REPO / "credentials.hjson").open(encoding="utf8") as handle:
            document = hjson.load(handle)
        for name, value in document["geocoders"].items():
            self.assertIsNone(value, f"{name} has a value in the template")


class CredentialsVerbTest(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.file = self.tmp / "credentials.hjson"

    def run_verb(self, *args, env=None):
        environment = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO),
                       "HOME": str(self.tmp), "MS_CREDENTIALS": str(self.file)}
        environment.update(env or {})
        proc = subprocess.run(
            [sys.executable, "-m", "messy_streets", "credentials", *args, "--json"],
            capture_output=True, text=True, cwd=REPO, env=environment)
        return proc.returncode, json.loads(proc.stdout)

    def test_reports_nine_credentials(self):
        code, report = self.run_verb()
        self.assertEqual(code, 0)
        self.assertEqual(len(report["credentials"]), 9)
        self.assertEqual(report["set"], 0)

    def test_missing_file_is_not_an_error(self):
        code, report = self.run_verb()
        self.assertEqual(code, 0)
        self.assertFalse(report["exists"])

    def test_the_environment_wins_over_the_file(self):
        from messy_streets import credentials
        credentials.write({"HERE_API_KEY": "from-file"}, self.file)
        code, report = self.run_verb(env={"HERE_API_KEY": "from-environment"})
        row = next(r for r in report["credentials"] if r["credential"] == "HERE_API_KEY")
        self.assertEqual(row["source"], "environment")

    def test_written_files_are_owner_only(self):
        from messy_streets import credentials
        written = credentials.write({"HERE_API_KEY": "x"}, self.file)
        self.assertEqual(stat.S_IMODE(written.stat().st_mode), 0o600)

    def test_values_are_never_printed(self):
        from messy_streets import credentials
        credentials.write({"HERE_API_KEY": "sentinel-value-do-not-print"}, self.file)
        proc = subprocess.run(
            [sys.executable, "-m", "messy_streets", "credentials"],
            capture_output=True, text=True, cwd=REPO,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO),
                 "HOME": str(self.tmp), "MS_CREDENTIALS": str(self.file)})
        self.assertNotIn("sentinel-value-do-not-print", proc.stdout + proc.stderr)

    def test_loading_supplies_only_what_is_unset(self):
        from messy_streets import credentials
        credentials.write({"HERE_API_KEY": "a", "TOMTOM_API_KEY": "b"}, self.file)
        os.environ["MS_CREDENTIALS"] = str(self.file)
        os.environ["HERE_API_KEY"] = "already-here"
        self.addCleanup(os.environ.pop, "HERE_API_KEY", None)
        self.addCleanup(os.environ.pop, "TOMTOM_API_KEY", None)
        self.addCleanup(os.environ.pop, "MS_CREDENTIALS", None)
        supplied = credentials.load_into_environment()
        self.assertEqual(supplied, ["TOMTOM_API_KEY"])
        self.assertEqual(os.environ["HERE_API_KEY"], "already-here")

    def test_clear_removes_the_file(self):
        from messy_streets import credentials
        credentials.write({"HERE_API_KEY": "x"}, self.file)
        self.assertTrue(self.file.is_file())
        self.run_verb("--clear")
        self.assertFalse(self.file.is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
