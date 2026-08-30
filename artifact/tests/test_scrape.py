"""Checks for `scrape` — stages 1 to 3, bounded or whole.

The download is the one part CI cannot do: the corpus is third-party, a part is
a few hundred megabytes, and the mirror is not something a test suite should
lean on. Everything either side of it is testable, and is — the class registry,
target expansion, the plan's arithmetic, the opt-in guard, and the N-Quad
extraction itself, which runs against a fixture rather than a download.

The extraction matters most. A re-scrape that parsed differently would not be
reproducing anything, so the join rule and the literal handling are pinned.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# A miniature quad file: two parents, one of which resolves to address+geo.
QUADS = '''\
_:parent1 <http://schema.org/address> _:addr1 <http://example.com/a> .
_:parent1 <http://schema.org/geo> _:geo1 <http://example.com/a> .
_:addr1 <http://schema.org/streetAddress> "12 Rue de l\\'\\u00c9glise" <http://example.com/a> .
_:addr1 <http://schema.org/postalCode> "75001" <http://example.com/a> .
_:addr1 <http://schema.org/addressLocality> "Paris" <http://example.com/a> .
_:addr1 <http://schema.org/addressCountry> "FR" <http://example.com/a> .
_:geo1 <http://schema.org/latitude> "4.8566e1" <http://example.com/a> .
_:geo1 <http://schema.org/longitude> "2.3522" <http://example.com/a> .
_:parent2 <http://schema.org/address> _:addr2 <http://example.com/b> .
_:addr2 <http://schema.org/streetAddress> "1 No Coordinates Way" <http://example.com/b> .
this line is not a quad at all
'''


def run(*args, env=None):
    environment = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO), "HOME": str(REPO)}
    environment.update(env or {})
    proc = subprocess.run(
        [sys.executable, "-m", "messy_streets", "scrape", *args, "--json"],
        capture_output=True, text=True, cwd=REPO, env=environment)
    if not proc.stdout.strip():
        raise AssertionError(f"no output; stderr:\n{proc.stderr[-2000:]}")
    return proc.returncode, json.loads(proc.stdout)


class RegistryTest(unittest.TestCase):

    def test_fifty_classes_from_the_stats_the_paper_emitted(self):
        from messy_streets.scrape import classes
        names = classes()
        self.assertEqual(len(names), 50)
        self.assertIn("LocalBusiness", names)
        self.assertIn("SkiResort", names)

    def test_url_matches_the_mirror_layout(self):
        from messy_streets.scrape import url_for
        self.assertEqual(
            url_for("SkiResort", 3),
            "https://data.dws.informatik.uni-mannheim.de/structureddata/2024-12"
            "/quads/classspecific/SkiResort/part_3.gz")

    def test_targets_expand_as_asked(self):
        from messy_streets.scrape import targets
        one = targets(["SkiResort"], 0, False, False)
        self.assertEqual(len(one), 1)
        self.assertTrue(one[0].bounded)

        walk = targets(["SkiResort"], None, False, True)
        self.assertFalse(walk[0].bounded)

        whole = targets(None, None, True, True)
        self.assertEqual(len(whole), 50)
        self.assertTrue(all(not t.bounded for t in whole))


class ExtractionTest(unittest.TestCase):
    """Stage 2, pinned against a fixture."""

    def setUp(self):
        from messy_streets import nquads
        self.nquads = nquads
        self.records, self.counts = nquads.extract(QUADS.splitlines())

    def test_only_address_plus_geo_survives_the_join(self):
        self.assertEqual(len(self.records), 1)
        self.assertEqual(self.counts.with_street, 2)
        self.assertEqual(self.counts.with_street_and_geo, 1)

    def test_an_unparsable_line_is_counted_not_fatal(self):
        self.assertEqual(self.counts.failed, 1)
        self.assertEqual(self.counts.rows, self.counts.parsed + self.counts.failed)

    def test_components_are_carried_across(self):
        record = self.records[0]
        self.assertEqual(record["postalCode"], "75001")
        self.assertEqual(record["addressLocality"], "Paris")
        self.assertEqual(record["addressCountry"], "FR")
        self.assertEqual(record["postOfficeBoxNumber"], "")

    def test_scientific_notation_is_normalised(self):
        """4.8566e1 is 48.566 — the original normalised, so this must too."""
        self.assertEqual(self.records[0]["latitude"], "48.566")
        self.assertEqual(self.records[0]["longitude"], "2.3522")

    def test_escapes_in_a_literal_are_resolved(self):
        self.assertIn("Rue de l'", self.records[0]["streetAddress"])

    def test_tsv_shape_matches_the_original(self):
        lines = list(self.nquads.to_tsv(self.records))
        self.assertEqual(lines[0].split("\t")[0], '"subject"')
        self.assertEqual(len(lines[0].split("\t")), 9)
        self.assertEqual(len(lines[1].split("\t")), 9)
        self.assertTrue(lines[1].startswith('"_:parent1"'))

    def test_an_empty_input_is_not_an_error(self):
        records, counts = self.nquads.extract([])
        self.assertEqual(records, [])
        self.assertEqual(counts.rows, 0)


class PlanTest(unittest.TestCase):

    def test_nothing_downloads_without_the_opt_in(self):
        code, report = run("--class", "SkiResort", "--part", "0")
        self.assertEqual(code, 0)
        self.assertFalse(report["opt_in_given"])
        self.assertFalse(report["would_run"])

    def test_the_plan_needs_no_network(self):
        code, report = run("--class", "SkiResort", "--part", "0")
        self.assertEqual(code, 0)
        self.assertIn("part_0.gz", report["first_url"])

    def test_part_defaults_to_zero(self):
        _, report = run("--class", "SkiResort")
        self.assertEqual(report["part"], 0)

    def test_whole_corpus_is_named_as_such(self):
        _, report = run("--all-classes", "--all-parts")
        self.assertTrue(report["whole_corpus"])
        self.assertEqual(len(report["classes"]), 50)

    def test_a_bounded_run_is_not_the_whole_corpus(self):
        _, report = run("--class", "SkiResort", "--part", "0")
        self.assertFalse(report["whole_corpus"])
        self.assertEqual(report["estimated_parts"], 1)

    def test_unknown_class_is_refused(self):
        proc = subprocess.run(
            [sys.executable, "-m", "messy_streets", "scrape", "--class", "Wombat"],
            capture_output=True, text=True, cwd=REPO,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO), "HOME": str(REPO)})
        self.assertEqual(proc.returncode, 3)
        self.assertIn("unknown class", proc.stdout)

    def test_naming_nothing_is_refused_rather_than_assumed(self):
        """--all-classes is a decision; it should never be the default."""
        proc = subprocess.run(
            [sys.executable, "-m", "messy_streets", "scrape"],
            capture_output=True, text=True, cwd=REPO,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO), "HOME": str(REPO)})
        self.assertEqual(proc.returncode, 3)
        self.assertIn("--all-classes", proc.stdout)

    def test_the_corpus_is_not_claimed_as_redistributed(self):
        _, report = run("--class", "SkiResort")
        self.assertIn("not redistributed", report["note"])

    def test_output_goes_under_out_never_into_data(self):
        with TemporaryDirectory() as directory:
            _, report = run("--class", "SkiResort", "--out", directory)
            self.assertTrue(report["destination"].startswith(directory))
            self.assertNotIn("/data/", report["destination"])


class RetryPolicyTest(unittest.TestCase):
    """The mirror throttles, so the paper used a backoff. This carries its policy.

    `wget.py` is built on `requests`, which this package cannot import — the CLI
    is stdlib-only so `doctor` can diagnose a broken install. The constants and
    the status handling are therefore pinned here against the original.
    """

    def setUp(self):
        from messy_streets import fetch
        self.fetch = fetch
        self.slept = []

    def opener(self, *statuses):
        """An opener that replays a sequence of HTTP statuses, then succeeds."""
        from urllib.error import HTTPError
        sequence = list(statuses)

        def open_url(url, timeout=None):
            if sequence:
                code = sequence.pop(0)
                raise HTTPError(url, code, f"status {code}", {}, None)
            return f"stream of {url}"

        return open_url

    def test_constants_match_the_original_downloader(self):
        self.assertEqual(self.fetch.MAX_RETRIES, 10)
        self.assertEqual(self.fetch.BASE_DELAY, 5.0)

    def test_a_clean_response_is_returned_first_time(self):
        outcome = self.fetch.open_with_retry(
            "http://x/part_0.gz", 10.0, opener=self.opener(), sleep=self.slept.append)
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.attempts, 1)
        self.assertEqual(self.slept, [])

    def test_403_and_404_mean_no_such_part(self):
        """Which is how the walk finds the end of a class — never a retry."""
        for code in (403, 404):
            outcome = self.fetch.open_with_retry(
                "http://x/part_9.gz", 10.0, opener=self.opener(code),
                sleep=self.slept.append)
            self.assertTrue(outcome.missing, code)
            self.assertFalse(outcome.ok, code)
        self.assertEqual(self.slept, [], "a missing part must not be retried")

    def test_429_backs_off_exponentially_then_succeeds(self):
        outcome = self.fetch.open_with_retry(
            "http://x/part_0.gz", 10.0, opener=self.opener(429, 429, 429),
            sleep=self.slept.append)
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.attempts, 4)
        # base_delay * 2**attempt, exactly as wget.py computed it.
        self.assertEqual(self.slept, [5.0, 10.0, 20.0])

    def test_persistent_throttling_gives_up_rather_than_looping(self):
        outcome = self.fetch.open_with_retry(
            "http://x/part_0.gz", 10.0, opener=self.opener(*([429] * 20)),
            sleep=self.slept.append)
        self.assertFalse(outcome.ok)
        self.assertIn("max retries exceeded", outcome.error)
        self.assertEqual(len(self.slept), 10)

    def test_an_unexpected_status_is_not_retried(self):
        outcome = self.fetch.open_with_retry(
            "http://x/part_0.gz", 10.0, opener=self.opener(500),
            sleep=self.slept.append)
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.error, "HTTP 500")
        self.assertEqual(self.slept, [])

    def test_a_transport_failure_is_reported_not_raised(self):
        from urllib.error import URLError

        def broken(url, timeout=None):
            raise URLError(OSError("no route to host"))

        outcome = self.fetch.open_with_retry(
            "http://x/part_0.gz", 10.0, opener=broken, sleep=self.slept.append)
        self.assertFalse(outcome.ok)
        self.assertIn("no route to host", outcome.error)

    def test_scrape_uses_the_shared_policy(self):
        """Not its own inlined copy of it."""
        source = (REPO / "messy_streets" / "scrape.py").read_text(encoding="utf8")
        self.assertIn("fetch.open_with_retry", source)
        self.assertNotIn("urlopen(url", source)


class VerbTableTest(unittest.TestCase):

    def test_scrape_needs_the_network(self):
        from messy_streets import verbs
        table = verbs.load()
        self.assertIn("scrape", table)
        self.assertTrue(table["scrape"].needs_network)
        self.assertTrue(table["scrape"].implemented)


if __name__ == "__main__":
    unittest.main(verbosity=2)
