"""Checks for `judges` — the second verb CI cannot exercise end to end.

Everything except the HTTP calls is testable, and is: the shipped prompts, the
filter chain transcribed from the build configuration, prompt rendering from
released records, answer parsing, verdict mapping, and the opt-in guard. The
live path needs a 35B model on a GPU, which no runner has.

The prompts matter as much as the code here. If a template changes, a re-run no
longer asks what the paper asked, so the templates are pinned by content.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

ROLES = {"street", "components", "pii"}


def run(*args, env=None):
    environment = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO), "HOME": str(REPO)}
    environment.update(env or {})
    proc = subprocess.run(
        [sys.executable, "-m", "messy_streets", "judges", *args, "--json"],
        capture_output=True, text=True, cwd=REPO, env=environment)
    if not proc.stdout.strip():
        raise AssertionError(f"no output; stderr:\n{proc.stderr[-2000:]}")
    return proc.returncode, json.loads(proc.stdout)


class PromptsTest(unittest.TestCase):
    """The shipped prompts are the ones the paper ran. Pinned, not paraphrased."""

    def setUp(self):
        from messy_streets import judges
        self.prompts = judges.load_prompts()

    def test_prompts_are_shipped(self):
        from messy_streets import judges
        self.assertTrue(judges.prompts_file().is_file())

    def test_three_roles_ten_steps(self):
        """One street judge, six PII fields, three component checks."""
        chain = self.prompts["chain"]
        self.assertEqual(len(chain), 10)
        self.assertEqual({s["role"] for s in chain}, ROLES)
        counts = {role: sum(1 for s in chain if s["role"] == role) for role in ROLES}
        self.assertEqual(counts, {"street": 1, "pii": 6, "components": 3})

    def test_every_step_names_a_shipped_template(self):
        for step in self.prompts["chain"]:
            self.assertIn(step["prompt"], self.prompts["templates"], step["name"])

    def test_the_pii_judge_runs_once_per_address_field(self):
        fields = [next(iter(s["inputs"])) for s in self.prompts["chain"] if s["role"] == "pii"]
        self.assertEqual(sorted(fields), sorted([
            "addressCountry", "addressLocality", "addressRegion",
            "postOfficeBoxNumber", "postalCode", "streetAddress"]))

    def test_templates_are_deterministic(self):
        """Temperature 0: a re-run is a fair test of the judge, not of sampling."""
        for name, template in self.prompts["templates"].items():
            self.assertEqual(template.get("temperature"), 0.0, name)

    def test_street_template_asks_the_paper_s_question(self):
        template = self.prompts["templates"]["messy_streets_similar_street_1"]["template"]
        self.assertIn("{street1}", template)
        self.assertIn("{street2}", template)
        self.assertIn("Match on street name only", template)
        self.assertIn("Yes or No", template)

    def test_the_boolean_system_prompt_is_shipped(self):
        self.assertIn("boolean", self.prompts["system_prompts"])
        self.assertTrue(self.prompts["system_prompts"]["boolean"])

    def test_the_model_is_the_one_in_the_paper(self):
        self.assertEqual(self.prompts["model"]["name"], "qwen3.5:35b")


class RenderTest(unittest.TestCase):
    """Rendering runs against real released records, not fixtures."""

    @classmethod
    def setUpClass(cls):
        from messy_streets import judges, tiers
        cls.judges = judges
        cls.prompts = judges.load_prompts()
        cls.steps = {s.name: s for s in judges.chain(cls.prompts)}
        cls.records = []
        for index, record in enumerate(tiers.read("gold")):
            if index >= 40:
                break
            cls.records.append(record)

    def test_the_reference_street_is_recoverable_from_every_record(self):
        """This is what makes the re-run possible without the 106 GB."""
        for record in self.records:
            self.assertIsNotNone(self.judges.reference_street(record),
                                 record.get("idx"))

    def test_both_existence_sources_are_handled(self):
        sources = {r["aux"]["existence"]["source"] for r in self.records}
        self.assertTrue(sources <= {"oa", "osd"}, sources)
        for source in sources:
            self.assertIn(source, self.judges.REFERENCE_STREET)

    def test_street_prompt_carries_both_sides_of_the_pair(self):
        step = self.steps["street_similarity"]
        record = self.records[0]
        text = self.judges.render(step, record, self.prompts)
        self.assertIn(record["aux"]["address"]["streetAddress"], text)
        self.assertIn(self.judges.reference_street(record), text)

    def test_absent_fields_are_skipped_not_sent_blank(self):
        """The original chain never asked the judge about a field that is not there."""
        step = self.steps["pid_in_pobox"]
        rendered = [self.judges.render(step, r, self.prompts) for r in self.records]
        self.assertTrue(all(text is None for text in rendered),
                        "postOfficeBoxNumber is absent throughout the gold tier")

    def test_a_populated_field_does_render(self):
        step = self.steps["pid_in_street"]
        text = self.judges.render(step, self.records[0], self.prompts)
        self.assertIsNotNone(text)
        self.assertIn(self.records[0]["aux"]["address"]["streetAddress"], text)

    def test_no_unfilled_placeholder_survives(self):
        for step in self.steps.values():
            for record in self.records[:10]:
                text = self.judges.render(step, record, self.prompts)
                if text is not None:
                    self.assertNotIn("{", text, f"{step.name} left a placeholder")


class AnswerTest(unittest.TestCase):

    def test_yes_and_no_in_the_shapes_a_model_produces(self):
        from messy_streets.judges import parse_answer
        for text in ("Yes", "yes", " YES ", "Yes.", "**Yes**", "Yes, it does"):
            self.assertIs(parse_answer(text), True, text)
        for text in ("No", "no", " NO ", "No.", "**No**", "No — different street"):
            self.assertIs(parse_answer(text), False, text)

    def test_anything_ambiguous_is_not_guessed(self):
        from messy_streets.judges import parse_answer
        for text in ("", "   ", "Maybe", "I cannot tell", "42"):
            self.assertIsNone(parse_answer(text), repr(text))

    def test_verdict_follows_the_step_s_own_mapping(self):
        """on_yes differs per step: yes means keep for street, discard for PII."""
        from messy_streets import judges
        prompts = judges.load_prompts()
        steps = {s.name: s for s in judges.chain(prompts)}
        self.assertEqual(judges.verdict(steps["street_similarity"], True), "keep")
        self.assertEqual(judges.verdict(steps["street_similarity"], False), "discard")
        self.assertEqual(judges.verdict(steps["pid_in_street"], True), "discard")
        self.assertEqual(judges.verdict(steps["pid_in_street"], False), "keep")
        self.assertIsNone(judges.verdict(steps["pid_in_street"], None))


class PlanTest(unittest.TestCase):

    def test_nothing_runs_without_the_opt_in(self):
        code, report = run("-n", "3")
        self.assertEqual(code, 0)
        self.assertFalse(report["opt_in_given"])
        self.assertFalse(report["would_run"])

    def test_the_plan_needs_no_model_and_no_network(self):
        """Which is why this test can exist at all."""
        code, report = run("-n", "3", env={"OLLAMA_HOST": "http://127.0.0.1:1"})
        self.assertEqual(code, 0)
        self.assertEqual(report["endpoint"], "http://127.0.0.1:1")

    def test_roles_can_be_restricted(self):
        _, report = run("-n", "3", "--role", "street")
        self.assertEqual(report["roles"], ["street"])
        self.assertEqual(len(report["steps"]), 1)

    def test_unknown_role_is_refused(self):
        proc = subprocess.run(
            [sys.executable, "-m", "messy_streets", "judges", "--role", "vibes"],
            capture_output=True, text=True, cwd=REPO,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO), "HOME": str(REPO)})
        self.assertNotEqual(proc.returncode, 0)

    def test_call_volume_counts_only_applicable_fields(self):
        """A step whose field is absent costs nothing, and says so."""
        _, report = run("-n", "5")
        by_name = {s["name"]: s["applicable"] for s in report["steps"]}
        self.assertEqual(by_name["pid_in_pobox"], 0)
        self.assertEqual(by_name["street_similarity"], 5)
        self.assertEqual(report["total_calls"], sum(by_name.values()))

    def test_volume_scales_with_n(self):
        _, small = run("-n", "3", "--role", "street")
        _, large = run("-n", "9", "--role", "street")
        self.assertEqual(small["total_calls"], 3)
        self.assertEqual(large["total_calls"], 9)

    def test_endpoint_gets_a_scheme_when_given_bare(self):
        _, report = run("-n", "2", "--endpoint", "gpu01:11434")
        self.assertEqual(report["endpoint"], "http://gpu01:11434")

    def test_the_scope_limit_is_stated_in_the_output(self):
        """It re-runs the judges; it does not rebuild the tiers."""
        _, report = run("-n", "2")
        self.assertIn("not that the tiers can be rebuilt", report["note"])
        self.assertEqual(report["layer"], "L4")

    def test_expected_verdict_is_keep(self):
        _, report = run("-n", "2")
        self.assertEqual(report["expected_verdict"], "keep")


class PreflightTest(unittest.TestCase):
    """A wrong endpoint should say what is wrong, not raise a parse error."""

    def test_an_unreachable_endpoint_is_reported_not_raised(self):
        from messy_streets.judges import preflight
        ok, detail = preflight("http://127.0.0.1:1", "qwen3.5:35b", timeout=2.0)
        self.assertFalse(ok)
        self.assertIn("cannot reach", detail)


class StubOllama:
    """A stand-in for Ollama, so the live path is exercised rather than assumed.

    It cannot tell us what a 35B model would answer. It does tell us that the
    request is well formed, the response is parsed, verdicts map the right way,
    disagreements are captured and errors are counted — which is everything
    between the record and the model.
    """

    def __init__(self, answer="Yes", model="qwen3.5:35b", status=200):
        import json as _json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):        # keep the test output quiet
                pass

            def do_GET(self):
                body = _json.dumps({"models": [{"name": model}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                request = _json.loads(self.rfile.read(length) or b"{}")
                outer.seen.append(request)
                if status != 200:
                    self.send_response(status)
                    self.end_headers()
                    return
                answer_for = outer.answer
                if callable(answer_for):
                    answer_for = answer_for(request)
                body = _json.dumps({"response": answer_for}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.answer = answer
        self.seen = []
        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()


class LivePathTest(unittest.TestCase):
    """Everything between a released record and the model, end to end."""

    @classmethod
    def setUpClass(cls):
        from messy_streets import judges, tiers
        cls.judges = judges
        cls.prompts = judges.load_prompts()
        cls.records = []
        for index, record in enumerate(tiers.read("gold")):
            if index >= 4:
                break
            cls.records.append(record)

    def steps(self, *names):
        chain = {s.name: s for s in self.judges.chain(self.prompts)}
        return [chain[n] for n in names]

    def test_preflight_finds_the_model(self):
        with StubOllama() as stub:
            ok, detail = self.judges.preflight(stub.url, "qwen3.5:35b")
        self.assertTrue(ok, detail)

    def test_preflight_reports_a_model_that_is_not_pulled(self):
        with StubOllama(model="llama3:8b") as stub:
            ok, detail = self.judges.preflight(stub.url, "qwen3.5:35b")
        self.assertFalse(ok)
        self.assertIn("not pulled", detail)

    def test_a_yes_on_the_street_judge_is_agreement(self):
        step = self.steps("street_similarity")
        with StubOllama(answer="Yes") as stub:
            results, disagreements = self.judges.judge(
                self.records, step, self.prompts, "qwen3.5:35b", stub.url, 10.0)
        self.assertEqual(results[0].asked, 4)
        self.assertEqual(results[0].agreed, 4)
        self.assertEqual(results[0].agreement, 100.0)
        self.assertEqual(disagreements, [])

    def test_a_no_on_the_street_judge_is_a_disagreement(self):
        """on_yes=keep, so 'No' means the judge would now discard the record."""
        step = self.steps("street_similarity")
        with StubOllama(answer="No") as stub:
            results, disagreements = self.judges.judge(
                self.records, step, self.prompts, "qwen3.5:35b", stub.url, 10.0)
        self.assertEqual(results[0].disagreed, 4)
        self.assertEqual(results[0].agreed, 0)
        self.assertEqual(len(disagreements), 4)
        self.assertEqual(disagreements[0].said, "discard")

    def test_the_pii_judge_maps_the_other_way(self):
        """on_yes=discard: 'No' is agreement, 'Yes' is a disagreement."""
        step = self.steps("pid_in_street")
        with StubOllama(answer="No") as stub:
            results, _ = self.judges.judge(
                self.records, step, self.prompts, "qwen3.5:35b", stub.url, 10.0)
        self.assertEqual(results[0].agreed, 4)
        with StubOllama(answer="Yes") as stub:
            results, disagreements = self.judges.judge(
                self.records, step, self.prompts, "qwen3.5:35b", stub.url, 10.0)
        self.assertEqual(results[0].disagreed, 4)
        self.assertEqual(disagreements[0].said, "discard")

    def test_an_unusable_answer_is_counted_not_guessed(self):
        step = self.steps("street_similarity")
        with StubOllama(answer="I am not sure about this one") as stub:
            results, _ = self.judges.judge(
                self.records, step, self.prompts, "qwen3.5:35b", stub.url, 10.0)
        self.assertEqual(results[0].unparsed, 4)
        self.assertEqual(results[0].agreed, 0)
        self.assertEqual(results[0].disagreed, 0)

    def test_an_http_error_is_counted_as_an_error_not_a_verdict(self):
        step = self.steps("street_similarity")
        with StubOllama(status=500) as stub:
            results, _ = self.judges.judge(
                self.records, step, self.prompts, "qwen3.5:35b", stub.url, 10.0)
        self.assertEqual(results[0].errors, 4)
        self.assertEqual(results[0].asked, 0)

    def test_absent_fields_are_never_sent_to_the_model(self):
        step = self.steps("pid_in_pobox")
        with StubOllama() as stub:
            results, _ = self.judges.judge(
                self.records, step, self.prompts, "qwen3.5:35b", stub.url, 10.0)
            self.assertEqual(stub.seen, [], "a blank field reached the model")
        self.assertEqual(results[0].skipped, 4)
        self.assertEqual(results[0].asked, 0)

    def test_the_request_carries_the_prompt_the_paper_used(self):
        step = self.steps("street_similarity")
        with StubOllama() as stub:
            self.judges.judge(self.records[:1], step, self.prompts,
                              "qwen3.5:35b", stub.url, 10.0)
            sent = stub.seen[0]
        record = self.records[0]
        self.assertEqual(sent["model"], "qwen3.5:35b")
        self.assertEqual(sent["options"]["temperature"], 0.0)
        self.assertFalse(sent["stream"])
        self.assertIn("Match on street name only", sent["prompt"])
        self.assertIn(record["aux"]["address"]["streetAddress"], sent["prompt"])
        self.assertIn(self.judges.reference_street(record), sent["prompt"])
        self.assertIn("Yes", sent["system"])

    def test_a_self_hosted_endpoint_bypasses_the_proxy(self):
        """A proxy in the environment must not swallow a loopback endpoint."""
        step = self.steps("street_similarity")
        with StubOllama() as stub:
            import os
            saved = {k: os.environ.get(k) for k in ("http_proxy", "HTTP_PROXY")}
            os.environ["http_proxy"] = "http://127.0.0.1:9"
            os.environ["HTTP_PROXY"] = "http://127.0.0.1:9"
            try:
                results, _ = self.judges.judge(
                    self.records[:2], step, self.prompts,
                    "qwen3.5:35b", stub.url, 10.0)
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
        self.assertEqual(results[0].asked, 2)
        self.assertEqual(results[0].errors, 0)


class VerbTableTest(unittest.TestCase):

    def test_judges_needs_the_network_like_geocode(self):
        """So the wrapper does not start it with --network none."""
        from messy_streets import verbs
        table = verbs.load()
        self.assertIn("judges", table)
        self.assertTrue(table["judges"].needs_network)
        self.assertTrue(table["judges"].implemented)

    def test_every_other_verb_stays_air_gapped(self):
        from messy_streets import verbs
        offline = {n for n, v in verbs.load().items() if v.offline}
        self.assertIn("tables", offline)
        self.assertIn("smoke", offline)
        self.assertNotIn("judges", offline)


if __name__ == "__main__":
    unittest.main(verbosity=2)
