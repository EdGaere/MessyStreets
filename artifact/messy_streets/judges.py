"""judges — re-run the LLM judges that built the tiers, and measure whether
they still say the same thing.

Stage 7 of the construction pipeline is not re-runnable: it consumes 106 GB of
OpenAddresses and OpenStreetMap reference data and a quantised 35B model on
four GPUs. Rebuilding the tiers from Web Data Commons is out of reach for
anyone but the authors, and the artefact says so.

The judges themselves are a different matter. Every released record carries
both sides of the pair the judges saw — the verbatim WDC address in
`aux.address`, and the OpenAddresses or OpenStreetMap street it was matched
against in `aux.existence`. So the judge decisions *can* be re-run on the
shipped data, without the 106 GB and without rebuilding anything.

What that establishes is narrow and worth stating exactly: it shows the judge
still reaches the same verdict on records whose verdict is known, not that the
tiers can be reconstructed. Every shipped record survived the filter chain, so
the expected answer for each one is `keep`. A disagreement is therefore either
model drift, sampling nondeterminism, or a genuine judgement the paper got
wrong — and the verb reports which record disagreed so it can be looked at.

Nothing runs without an explicit opt-in, and the plan needs neither network nor
a model, so the plan is testable where the live path is not. This mirrors
`geocode`, deliberately: same shape, same gate, same drift framing.
"""

from json import dumps, loads
from os import environ
from typing import Dict, List, NamedTuple, Optional, Tuple

from messy_streets import paths

OPT_IN = "--i-supply-my-own-judge"

# Ollama's default. Overridden by --endpoint or OLLAMA_HOST.
DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3.5:35b"

ROLES = ("street", "components", "pii")

# Where the reference street name lives, per existence source. OpenAddresses
# and the OpenStreetMap-derived set spell it differently.
REFERENCE_STREET = {"oa": "street", "osd": "street_name"}

# Judged records are survivors: every one of them was kept by every step.
EXPECTED = "keep"


def prompts_file():
    return paths.data() / "judges" / "prompts.json"


def load_prompts() -> Dict:
    path = prompts_file()
    if not path.is_file():
        raise FileNotFoundError(f"judge prompts not shipped: {path}")
    return loads(path.read_text(encoding="utf8"))


def endpoint(override: Optional[str] = None) -> str:
    chosen = override or environ.get("OLLAMA_HOST") or DEFAULT_ENDPOINT
    if not chosen.startswith(("http://", "https://")):
        chosen = f"http://{chosen}"
    return chosen.rstrip("/")


class Step(NamedTuple):
    role: str
    name: str
    prompt: str
    inputs: Dict[str, str]
    on_yes: str
    on_no: str
    description: str = ""


def chain(prompts: Dict, roles: Optional[List[str]] = None) -> List[Step]:
    wanted = set(roles or ROLES)
    fields = set(Step._fields)
    return [Step(**{k: v for k, v in step.items() if k in fields})
            for step in prompts["chain"] if step["role"] in wanted]


def reference_street(record: Dict) -> Optional[str]:
    """The OA/OSM street this address was matched against, from the shipped record."""
    existence = record.get("aux", {}).get("existence") or {}
    source = existence.get("source")
    payload = (existence.get("address") or {}).get("payload") or {}
    field = REFERENCE_STREET.get(source)
    if not field:
        return None
    value = payload.get(field)
    return str(value) if value not in (None, "") else None


def _blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and value != value:      # NaN
        return True
    return str(value).strip() == ""


def render(step: Step, record: Dict, prompts: Dict) -> Optional[str]:
    """Fill this step's template from the record, or None if it does not apply.

    A step is skipped when its field is absent — which is how the original
    chain behaved: a missing postOfficeBoxNumber was never sent to the PII
    judge. Skipping is reported, never silently counted as agreement.
    """
    template = prompts["templates"][step.prompt]["template"]
    address = record.get("aux", {}).get("address") or {}
    values: Dict[str, str] = {}

    for field, token in step.inputs.items():
        if field == "__reference_street__":
            value = reference_street(record)
        else:
            value = address.get(field)
        if _blank(value):
            return None
        values[token] = str(value)

    return template.format(**values)


def parse_answer(text: str) -> Optional[bool]:
    """Yes/No from the model, or None when it answered something else.

    The system prompt asks for exactly one word. It is still worth being
    lenient about case, punctuation and a stray leading token, and strict
    about anything genuinely ambiguous.
    """
    if not text:
        return None
    words = text.strip().lower().split()
    if not words:
        return None
    # Strip decoration from the leading word itself: a model that answers
    # "**Yes**" or "Yes, it does" has still answered yes.
    first = words[0].strip("*_`'\".,;:!?()[]")
    if first in ("yes", "true"):
        return True
    if first in ("no", "false"):
        return False
    return None


def verdict(step: Step, answer: Optional[bool]) -> Optional[str]:
    if answer is None:
        return None
    return step.on_yes if answer else step.on_no


def _loopback_or_private(host: str) -> bool:
    """Is this endpoint one a proxy has no business handling?"""
    from urllib.parse import urlparse

    name = (urlparse(host).hostname or "").lower()
    if name in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    if name.startswith(("10.", "192.168.", "127.")):
        return True
    if name.startswith("172."):
        try:
            second = int(name.split(".")[1])
        except (IndexError, ValueError):
            return False
        return 16 <= second <= 31
    return False


def _opener(host: str):
    """An opener that does not hand a self-hosted endpoint to a corporate proxy.

    urllib honours http_proxy, so on a proxied network a local Ollama is routed
    to the proxy and the caller gets HTML back instead of JSON. Endpoints on
    loopback or a private range bypass it; anything else keeps the environment's
    own proxy settings, which a remote endpoint may legitimately need.
    """
    from urllib.request import ProxyHandler, build_opener

    if _loopback_or_private(host):
        return build_opener(ProxyHandler({}))
    return build_opener()


def ask(prompt_text: str, model: str, host: str, system: Optional[str],
        temperature: float, timeout: float) -> Tuple[Optional[str], str]:
    """One call to Ollama's /api/generate. Stdlib only, like the rest of the CLI."""
    from urllib.error import HTTPError, URLError
    from urllib.request import Request

    body = {
        "model": model,
        "prompt": prompt_text,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if system:
        body["system"] = system

    request = Request(
        f"{host}/api/generate",
        data=dumps(body).encode("utf8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _opener(host).open(request, timeout=timeout) as response:
            payload = loads(response.read().decode("utf8"))
        return payload.get("response", ""), ""
    except HTTPError as error:
        return None, f"HTTP {error.code}"
    except URLError as error:
        return None, f"{type(error.reason).__name__}: {error.reason}"
    except Exception as error:                                       # noqa: BLE001
        return None, f"{type(error).__name__}: {error}"


class Result(NamedTuple):
    role: str
    step: str
    asked: int
    agreed: int
    disagreed: int
    unparsed: int
    skipped: int
    errors: int

    @property
    def agreement(self) -> float:
        return 100.0 * self.agreed / self.asked if self.asked else 0.0


class Disagreement(NamedTuple):
    step: str
    record: int
    field_value: str
    said: str


def preflight(host: str, model: str, timeout: float = 10.0) -> Tuple[bool, str]:
    """Is there a model to talk to? Reported, never assumed."""
    from urllib.error import URLError

    try:
        with _opener(host).open(f"{host}/api/tags", timeout=timeout) as response:
            raw = response.read().decode("utf8", "replace")
    except URLError as error:
        return False, f"cannot reach {host}: {error.reason}"
    except Exception as error:                                       # noqa: BLE001
        return False, f"cannot reach {host}: {type(error).__name__}: {error}"

    try:
        payload = loads(raw)
    except ValueError:
        # Something answered, but not Ollama — commonly a proxy interposed on
        # the port, which is worth saying rather than reporting a parse error.
        return False, (f"{host} answered, but not with JSON — a proxy or the "
                       f"wrong port, not Ollama")

    available = [m.get("name", "") for m in payload.get("models", [])]
    if any(name == model or name.startswith(f"{model}:") or
           name.split(":")[0] == model.split(":")[0] for name in available):
        return True, f"{model} available at {host}"
    listed = ", ".join(available[:6]) or "none"
    return False, f"{model} not pulled at {host}; available: {listed}"


def judge(records: List[Dict], steps: List[Step], prompts: Dict, model: str,
          host: str, timeout: float, verbose: bool = False
          ) -> Tuple[List[Result], List[Disagreement]]:
    system = (prompts.get("system_prompts") or {}).get("boolean")
    results: List[Result] = []
    disagreements: List[Disagreement] = []

    for step in steps:
        temperature = prompts["templates"][step.prompt].get("temperature", 0.0)
        asked = agreed = disagreed = unparsed = skipped = errors = 0

        for index, record in enumerate(records):
            text = render(step, record, prompts)
            if text is None:
                skipped += 1
                continue

            raw, error = ask(text, model, host, system, temperature, timeout)
            if error:
                errors += 1
                continue

            asked += 1
            said = verdict(step, parse_answer(raw))
            if said is None:
                unparsed += 1
            elif said == EXPECTED:
                agreed += 1
            else:
                disagreed += 1
                shown = next(iter(step.inputs))
                value = (record.get("aux", {}).get("address") or {}).get(shown)
                if shown == "__reference_street__":
                    value = reference_street(record)
                disagreements.append(Disagreement(
                    step.name, record.get("idx", index), str(value)[:60], said))

            if not verbose and index % 5 == 4:
                print(f"    {step.name}: {index + 1}/{len(records)}",
                      end="\r", flush=True)

        print(f"    {step.name}: {asked} asked" + " " * 24, flush=True)
        results.append(Result(step.role, step.name, asked, agreed, disagreed,
                              unparsed, skipped, errors))

    return results, disagreements


def report(results: List[Result], disagreements: List[Disagreement]) -> None:
    print()
    width = max([len(r.step) for r in results] + [len("all steps")]) + 2
    print(f"  {'judge step':<{width}}{'asked':>7}{'agree':>7}{'differ':>8}"
          f"{'unparsed':>10}{'skipped':>9}{'error':>7}   agreement")
    print("  " + "-" * (width + 62))
    for item in results:
        rate = f"{item.agreement:>5.1f}%" if item.asked else f"{'--':>6}"
        print(f"  {item.step:<{width}}{item.asked:>7}{item.agreed:>7}{item.disagreed:>8}"
              f"{item.unparsed:>10}{item.skipped:>9}{item.errors:>7}"
              f"   {rate}")

    total_asked = sum(r.asked for r in results)
    total_agreed = sum(r.agreed for r in results)
    overall = 100.0 * total_agreed / total_asked if total_asked else 0.0
    print("  " + "-" * (width + 62))
    total_rate = f"{overall:>5.1f}%" if total_asked else f"{'--':>6}"
    print(f"  {'all steps':<{width}}{total_asked:>7}{total_agreed:>7}"
          f"{sum(r.disagreed for r in results):>8}"
          f"{sum(r.unparsed for r in results):>10}"
          f"{sum(r.skipped for r in results):>9}"
          f"{sum(r.errors for r in results):>7}   {total_rate}")

    print("\n  Every record judged here survived the filter chain when the tiers were")
    print("  built, so the expected verdict for each one is 'keep'. Agreement means the")
    print("  judge still says what it said; a difference is model drift or a judgement")
    print("  worth looking at, not a defect in the released data.")
    print("  'skipped' is a field the record does not carry — the original chain did")
    print("  not send those to the judge either.")

    if disagreements:
        print(f"\n  {len(disagreements)} disagreement(s):")
        for item in disagreements[:15]:
            print(f"    {item.step:<22} record {item.record:<8} said {item.said:<8} {item.field_value}")
        if len(disagreements) > 15:
            print(f"    ... and {len(disagreements) - 15} more")


def run(n: int = 25, roles: Optional[List[str]] = None, tier: str = "gold",
        model: str = DEFAULT_MODEL, host: Optional[str] = None,
        timeout: float = 120.0, opt_in: bool = False, as_json: bool = False,
        verbose: bool = False) -> int:
    from messy_streets import tiers
    from messy_streets.cli import EXIT_OK, EXIT_UNAVAILABLE

    unknown = [r for r in (roles or []) if r not in ROLES]
    if unknown:
        print(f"unknown role(s): {', '.join(unknown)}")
        print(f"choose from: {', '.join(ROLES)}")
        return EXIT_UNAVAILABLE

    try:
        prompts = load_prompts()
    except FileNotFoundError as error:
        print(str(error))
        return EXIT_UNAVAILABLE

    steps = chain(prompts, roles)
    resolved = endpoint(host)

    records = []
    for index, record in enumerate(tiers.read(tier)):
        if index >= n:
            break
        records.append(record)

    # A step costs one call per record that carries its field.
    applicable = {step.name: sum(1 for r in records if render(step, r, prompts) is not None)
                  for step in steps}
    total_calls = sum(applicable.values())

    if as_json:
        print(dumps({
            "layer": "L4",
            "opt_in_given": opt_in,
            "tier": tier,
            "records": len(records),
            "model": model,
            "endpoint": resolved,
            "roles": sorted({s.role for s in steps}),
            "steps": [{"role": s.role, "name": s.name, "prompt": s.prompt,
                       "applicable": applicable[s.name]} for s in steps],
            "total_calls": total_calls,
            "expected_verdict": EXPECTED,
            "would_run": opt_in,
            "note": ("Re-runs the stage-7 judges on released records. Establishes that "
                     "the judges reproduce, not that the tiers can be rebuilt: stage 7 "
                     "in full needs 106 GB of reference data and four GPUs."),
            "exit_code": EXIT_OK,
        }, indent=2))
        return EXIT_OK

    print(f"\nLLM judge re-run plan — {len(records)} {tier}-tier record(s), "
          f"{len(steps)} judge step(s)\n")
    width = max([len(s.name) for s in steps] + [len("judge step")]) + 2
    print(f"  {'judge step':<{width}}{'role':<13}{'prompt':<34}{'calls':>7}")
    print("  " + "-" * (width + 54))
    for step in steps:
        print(f"  {step.name:<{width}}{step.role:<13}{step.prompt:<34}"
              f"{applicable[step.name]:>7}")

    print(f"\n  {total_calls:,} call(s) in total, sequential.")
    print(f"  model     {model}")
    print(f"  endpoint  {resolved}")

    reachable, detail = (False, "not checked")
    if opt_in:
        reachable, detail = preflight(resolved, model)
    print(f"  status    {detail}" if opt_in else
          "  status    not checked; the plan needs no model and no network")

    print("\n  Every record judged here survived the filter chain, so the expected")
    print(f"  verdict for each is '{EXPECTED}'. What this measures is whether the judge")
    print("  still agrees with itself — not whether the tiers can be reconstructed.")
    print("  Rebuilding the tiers is stage 7 in full: 106 GB of reference data and")
    print("  four GPUs. This verb does not do that, and cannot.")

    if not opt_in:
        print(f"\n  This was a plan; no model was contacted. To run it, pass {OPT_IN}.")
        print("  You supply the Ollama endpoint and the model; both are yours to run.")
        return EXIT_OK

    if not reachable:
        print(f"\n  {detail}")
        print(f"  Start Ollama and pull the model:  ollama pull {model}")
        print(f"  Point at a remote one:            --endpoint host:11434")
        return EXIT_UNAVAILABLE

    print(f"\n  {OPT_IN} given — re-judging {len(records)} record(s).\n")
    results, disagreements = judge(records, steps, prompts, model, resolved,
                                   timeout, verbose=verbose)
    report(results, disagreements)
    return EXIT_OK
