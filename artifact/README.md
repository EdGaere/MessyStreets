# MESSY STREETS — reproduction artefact

Reproduction artefact for *MESSY STREETS: A Benchmark for Geocoding Real-World
Addresses* (ACM SIGSPATIAL). The benchmark itself — three tiers of 10,000
verbatim web addresses with verified existence — is described in the paper and
released alongside this repository.

> **Both result tables in the paper reproduce offline** — from predictions
> recorded when the experiments ran, with no network and no API keys.

## Build and run

Everything below assumes only Docker (or podman). Nothing else is installed on
the host.

```sh
git clone https://github.com/EdGaere/MessyStreets.git
cd MessyStreets/artifact

docker build -t "$(grep -v '^#' IMAGE | head -1)" .   # ~3 min, no compiler needed

./messy-streets doctor                                # can this machine reproduce anything?
./messy-streets tables                                # Tables 4 and 5 of the paper, ~4 min
```

The image is tagged from the `IMAGE` file so the `./messy-streets` wrapper
finds it. The wrapper checks the host first — runtime, image, mount,
architecture — then runs the container with the network switched off.

The build needs no toolchain: every pinned dependency ships a prebuilt wheel,
so it works natively on `linux/amd64` and `linux/arm64` alike.

**Without a container runtime**, the same commands work natively:

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt && pip install -e .
messy-streets doctor
```

## The commands

```sh
./messy-streets doctor    # can this machine reproduce anything?
./messy-streets smoke     # reproduce one run of one table  (~20 s)
./messy-streets tables    # reproduce Tables 4 and 5 of the paper  (~4 min)
./messy-streets stats     # dataset-level figures from the released tiers
./messy-streets inspect   # look at the addresses themselves
./messy-streets sample    # check the benchmark slices against the tier database
./messy-streets pipeline  # the fifteen construction stages
./messy-streets geocode   # plan a live re-run; nothing is queried without opting in
./messy-streets judges    # re-run the stage-7 LLM judges; nothing is asked without opting in
./messy-streets scrape    # re-run stages 1-3 against WDC; nothing is fetched without opting in
./messy-streets credentials   # show, set or clear the geocoder API keys
```

That is the whole interaction. The wrapper checks the host, starts the
container with the network switched off, and reports whether this machine can
reproduce the results. If anything is wrong it says which thing, not that
something went wrong.

To check the host without starting a container:

```sh
./messy-streets --preflight
```

## Reproducibility layers

The paper spans a pipeline from 136 billion N-Quads to two LaTeX tables.
Different parts of it cost wildly different amounts to re-run, so the artefact
says which layer each command operates at rather than implying they are equal.

| Layer | What it reproduces | Cost |
|-------|--------------------|------|
| **L0** | The three released tiers and the statistics computed from them | seconds, offline |
| **L1** | Both paper tables, replayed from cached geocoder predictions | ~2 min, offline, no API keys |
| **L2** | The benchmark slices, regenerated from the tier databases at seed 42 | ~3 min, offline |
| **L3** | Live re-query of the twelve geocoders | ~14 h, 9 API keys, **will not match the paper** |
| **L4** | Construction of the tiers from Web Data Commons | 106 GB of reference data and four GPUs — documented, not run |
| **L4′** | The stage-7 LLM judges, re-run on released records | minutes, your own Ollama endpoint, no reference data |
| **L4″** | Stages 1–3 re-run on a bounded slice of Web Data Commons | minutes per part, your own bandwidth and disk |

L0–L2 are the artefact's actual promise. L3 reproduces the *finding*, not the
figures: the services and their OpenStreetMap snapshots have moved on. L4 is
shipped as fifteen documented stages so the construction method is inspectable
even though re-running it is not realistic. L4′ is the one part of L4 that *is*
within reach — see [Re-running the LLM judges](#re-running-the-llm-judges).

## Commands

Run `./messy-streets --help` for the current list. Verbs that are not built yet
are listed anyway, with the slice they arrive in, so the intended surface is
visible from the start.

## Build progress

| Slice | Delivers | Status |
|-------|----------|--------|
| 1 | The container runs at all, and says so — skeleton, wrapper, preflight, `doctor`, tests, CI | **done** |
| 2 | `smoke` — one table from cached predictions | **done** |
| 3 | `tables` — both paper tables *(ship point)* | **done** |
| 4 | `stats`, `inspect` | **done** |
| 5 | `sample` | **done** |
| 6 | `pipeline` and the stage-9 repair script | **done** |
| 7 | `geocode` | **done** |
| 8 | `shell`, release mechanics, DOI | **done** |
| 10 | `judges` — re-run the stage-7 judges on released records | **done** |
| 11 | `scrape` — re-run stages 1–3 against WDC, bounded or whole | **done** |

Each slice builds one command end to end and is tested before the next starts,
because the vendored dependency closure is a hypothesis until something
executes it.

## Developing without a container

The machine this was developed on has no container runtime, so everything works
natively too, with the same CLI and the same exit codes:

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt && pip install -e .
messy-streets doctor
```

`MS_NATIVE=1 ./messy-streets <verb>` takes the same path through the wrapper.
Environment warnings are expected outside the container — the image sets the
pins that make runs comparable.

## What reproduces today

| Paper table | What it is | Status |
|-------------|------------|--------|
| Table 1 | Representative messy addresses | Hand-picked; checkable with `inspect` (slice 4) |
| Table 2 | WDC filtering cascade | **verifies — 9/9 cells** against the statistics stage 3 emitted |
| Table 3 | Component existence across tiers | **recomputed — and it does not match the paper; see below** |
| **Table 4** | Twelve geocoders on the gold tier | **46/48 cells exact, 2 known deviations** |
| **Table 5** | CRR and GH6 by divergence and tier | **32/32 cells exact** |

Tables 4 and 5 are the two the paper's findings rest on. Both are checked
against the mean *and* the error bar of every published cell, parsed from the
LaTeX that was `\input` into the paper itself — the artefact regenerates that
LaTeX and compares it to what was published.

The two deviations are both Pelias, both 0.1 percentage points, and both
declared in `data/expected/table4.json` with the value the rebuild is expected
to produce. They report as *known deviations* rather than failures, but they
are still checked: if either changes, `tables` fails.

## Table 3 does not reproduce, and that is a finding

`messy-streets stats` recomputes component existence over all 10,000 records of
each released tier. It disagrees with the paper's Table 3, for three reasons
worth stating plainly:

- **The paper's cells are 1,000-observation samples**, drawn from a benchmark
  slice, not computed over the released tiers.
- **The silver row was drawn from `mq_1000`** — a 1,000-record pre-release
  database — while gold came from `hq_10000` and raw from `lq_10000`.
- **Six of the fifteen cells differ from the analysis outputs the paper's own
  method produced**, by up to 2.8 percentage points.

`stats` prints all three columns side by side — released, analysis output,
published — so the difference is visible rather than resolved by fiat. The
tests pin the six disagreeing cells so the finding cannot quietly vanish.

The Biases paragraph fares better: Latin-script shares recompute to 98.4%,
96.3% and 93.8%, which round to the published 98/96/94.

## Re-running the LLM judges

Three LLM judges built the gold tier: one asks whether a WDC address and the
street it matched are the same street, one checks that the components are
usable, and one looks for personally identifiable information — six times, once
per address field. Ten judge calls per candidate record, 28K candidates.

Re-running *that* would mean rebuilding the tiers, which needs 106 GB of
OpenAddresses and OpenStreetMap reference data and a quantised 35B model on four
GPUs. The artefact does not pretend otherwise.

But the judges can be re-run on the records that were released, because every
record ships both sides of the pair the judge saw — the verbatim WDC address in
`aux.address` and the matched OA/OSM street in `aux.existence`. That costs an
Ollama endpoint and a few minutes:

```sh
./messy-streets judges -n 25                       # plan: steps, calls, model, endpoint
./messy-streets judges -n 25 --i-supply-my-own-judge
```

The prompts are shipped verbatim in `data/judges/prompts.json`, together with the
filter chain that used them, transcribed from the build configuration that
produced the gold tier. You can read what the judges were asked without running
anything.

**What a re-run establishes, and what it does not.** Every released record
survived the filter chain, so the expected verdict for each one is `keep`. The
verb reports agreement per judge step and names the records that disagree. High
agreement means the judge still says what it said when the tiers were built. It
does **not** mean the tiers can be reconstructed — that is stage 7 in full, and
it stays out of reach.

An actual run, ten gold-tier records against `qwen3.8:27b` — a *different*
model from the `qwen3.5:35b` the paper used, which is the harder test:

```
  judge step           asked  agree  differ  unparsed  skipped  error   agreement
  street_similarity       10      9       1         0        0      0    90.0%
  pid_in_pobox             0      0       0         0       10      0       --
  pid_in_region            7      7       0         0        3      0   100.0%
  pid_in_locality          9      9       0         0        1      0   100.0%
  pid_in_country          10     10       0         0        0      0   100.0%
  pid_in_postcode         10     10       0         0        0      0   100.0%
  pid_in_street           10     10       0         0        0      0   100.0%
  valid_postcode          10     10       0         0        0      0   100.0%
  valid_street            10     10       0         0        0      0   100.0%
  valid_country           10     10       0         0        0      0   100.0%
  all steps               86     85       1         0       14      0    98.8%

  1 disagreement(s):
    street_similarity      record 4     said discard  車屋御池下ル梅屋町358 アーバネックス御池ビル　Ｂ１Ｆ
```

98.8% agreement across 86 calls, in about five minutes. The single disagreement
is worth reading rather than dismissing: a Kyoto address written in the
traditional intersection style (*Kurumaya-Oike-sagaru*, "south of the
Kurumaya/Oike crossing") matched against the street `御池通`. The paper's judge
accepted it; this one rejects it. That is a real difference of judgement on a
genuinely hard non-Latin address, which is what the verb exists to surface.

`skipped` is a field the record does not carry — `postOfficeBoxNumber` is absent
throughout the gold tier, and the original chain did not send those to the judge
either. Nothing is skipped silently, and a step that asked nothing reports `--`
rather than 0%.

### Setup

You supply the model; the artefact supplies the prompts.

```sh
ollama pull qwen3.5:35b                    # ~20 GB
./messy-streets judges --endpoint gpu01:11434 --i-supply-my-own-judge
```

The endpoint comes from `--endpoint`, else `$OLLAMA_HOST`, else
`127.0.0.1:11434`. `--role street|components|pii` restricts which judges run;
`--model` points at a different tag if you want to ask a different model the
same questions — which is a legitimate experiment, and not a reproduction.

Templates are pinned at temperature 0, so a disagreement is drift or a genuine
difference of judgement rather than sampling noise. Like `geocode`, this verb
needs the network, so CI runs the plan rather than a real model. Everything
between a released record and the model — request shape, answer parsing,
verdict mapping, skipping, error counting, proxy bypass — is driven against a
stubbed Ollama in `tests/test_judges.py`. What no test can cover is what a real
35B model answers, which is the thing the verb exists to find out.

## Re-scraping Web Data Commons

Stage 1 downloads the December 2024 WDC corpus: fifty schema.org classes, each
split into parts numbered from zero — 136.7 billion quads, days of transfer, and
a corpus this artefact is not allowed to redistribute. Stage 2 parses the quads
and joins each address to its coordinates; stage 3 applies the filter cascade in
Table 2.

Re-running all of that is unrealistic. Re-running *one part of one class* is not:

```sh
./messy-streets scrape --class SkiResort --part 0                  # plan
./messy-streets scrape --class SkiResort --part 0 --i-supply-my-own-storage
```

That downloads one archive, parses it with the same extraction the paper used,
and reports what came out:

```
  class       part         quads  unparsed   street    +geo   status
  SkiResort      0     1,173,165         0    6,909   2,734   ok
```

1.17 million quads in about six seconds, no parse failures, 2,734 addresses that
resolve to both a street and a coordinate. Those are the quantities stage 3
aggregates into Table 2's cascade — for one part, not for the corpus.

### Bounded, or the whole thing

```sh
--class <name> --part <n>     one archive; minutes
--class <name> --all-parts    every part of one class, walking until one is missing
--all-classes --all-parts     the corpus, if you mean it
```

`--all-parts` finds the end of a class the way the original did, by requesting
parts from zero until the mirror returns nothing. `--limit-parts` caps that.
Naming no class at all is refused rather than assumed to mean everything.

The mirror throttles concurrent requests, which is why the construction
pipeline used its own downloader rather than plain wget. That retry policy is
carried in `messy_streets/fetch.py` — the same constants, the same status codes,
the same exponential backoff on 429. It is a port rather than the file itself:
`wget.py` is built on `requests`, and this CLI is stdlib-only so `doctor` can
diagnose a broken dependency install. A 403 or 404 means *no such part* and is
never retried, which is how the part walk finds the end of a class.

The plan states the extent, the URLs and a rough size before anything is
fetched, and needs no network to produce. `--all-classes --all-parts` prints an
explicit warning that this is hundreds of gigabytes over days, and suggests a
single part first. Nothing is downloaded without `--i-supply-my-own-storage`,
and output goes under `--out`, never into `data/`.

### What it does and does not establish

It re-runs stages 1–3 on what you asked for: download, parse, join. It does not
rebuild the tiers — that is stage 7, which additionally needs 106 GB of
OpenAddresses and OpenStreetMap reference data and the judges. And the corpus
belongs to Web Data Commons; the artefact links to it rather than shipping it.

CI runs the plan, which needs no network. The extraction is tested against a
fixture that pins the join rule, the literal unescaping and the coordinate
normalisation, because a re-scrape that parsed differently would not be
reproducing anything.

## Where the API keys live

In one file on your machine, outside this repository, at mode 0600:

```
~/.config/messy-streets/credentials.hjson
```

Not in the image, which everyone who pulls it would receive. Not in the
repository, which is one `git add -A` from being public. `credentials.hjson`
here is an empty template; every other name matching `credentials*.hjson` is
gitignored, so a filled-in copy cannot be committed by accident.

```sh
./messy-streets credentials                # what is set — never a value
./messy-streets credentials --set here     # prompts without echoing
./messy-streets credentials --clear
./messy-streets geocode --credentials ~/.config/messy-streets/mine.hjson
```

The container borrows the file for the length of one command: mounted
read-only, read into the process environment, gone when the container exits. A
read-only mount rather than `--env-file`, because `--env-file` puts the values
into the container's configuration where `docker inspect` shows them to anyone
with Docker access while the run lasts.

Environment variables win over the file, so CI needs no edit. Nine providers
need a key; Nominatim, Photon and ArcGIS do not, so the geocoders the paper's
findings concern work with no credentials at all.

## Measuring drift instead of failing to reproduce

A live re-run cannot match the paper — the services and the OpenStreetMap
snapshots behind the open-source ones have moved since June 2026. So `geocode`
reports the *difference*: each live answer is compared with what that provider
returned at the time, per provider, at geohash precision 1. A disagreement
there means a materially different place, or no result at all.

Nine of the twelve providers need a credential. Nominatim, Photon and ArcGIS
do not, which is convenient, since two of them are what the paper's findings
are about. On 25 gold-tier addresses all three agree with their June 2026
answers exactly:

```
  provider           compared   agree  now only  then only   agreement
  nominatim                25      25         0          0   100.0%
  photon                   25      25         0          0   100.0%
  arcgis                   25      25         0          0   100.0%
```

Nothing is queried without `--i-supply-my-own-keys`. By default the verb prints
a plan: which providers are configured, how many calls, how long. The plan
needs no network and no credentials, which is why it can be tested and the live
path cannot.

## What `smoke` proves

It rebuilds run 1 of the ten runs behind Table 4 — twelve geocoders, 100
addresses each, 48 cells — entirely from predictions recorded when the
experiments were run, and compares every cell against the published value. No
network, no API keys, no geocoder client is ever constructed.

Those are the intermediate per-run values, not the published means; the paper
reports mean ±2 SEM over all ten runs, which `tables` reproduces.

Every command runs in a throwaway copy of the tree. The pipeline writes results
back into its own inputs, so running it in place would modify the data the next
run reads — and, worse, a partially failed run could truncate the cached
predictions that make offline reproduction possible.

## Tests

```sh
./tests/run.sh
```

63 assertions, no container runtime required. The entrypoint and the wrapper
are shell, so their real logic — the write probe, the working-copy revision
stamp, the preflight ladder, which verbs get `--network none` — is driven
directly against a stubbed runtime in `tests/fakes/`. `doctor`'s and `smoke`'s failure paths
are exercised too — a changed prediction, a changed reference, an absent cache
entry — because a check that cannot fail converts an unverified environment
into a green tick.

The one thing these cannot cover is whether the image *builds*, on both
architectures. That needs a real daemon and is verified in CI.

## Layout

```
messy_streets/     the CLI — stdlib only, so `doctor` can diagnose a broken install
  verbs.tsv        the command table; read by both the CLI and the shell wrapper
src/phd/           vendored dependency closure, resolved via PYTHONPATH
src/serentec/      "
data/              released tiers, cached predictions, benchmark slices
messy-streets      host wrapper: preflight, then exec into the container
docker-entrypoint.sh   makes the writable working copy, then runs the CLI
tests/             runs without a container runtime; see Tests
tools/vendor.py    copies the closure out of the source tree, scrubbing credentials
tools/patches.py   every modification to the vendored code, and why
tools/checksums.py regenerates data/CHECKSUMS.sha256
VENDOR.md          provenance: every vendored file, its source hash, its patches
IMAGE              the container image, pinned by digest
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Reproduced, or all checks passed |
| 1 | Mismatch against the published result |
| 2 | Environment or data-integrity failure |
| 3 | This layer is not available here |

## Machine-readable metadata

`croissant.json` describes the three released tiers in the MLCommons Croissant
format — fields, types, JSON paths and sha256 for each file. It validates
against `mlcroissant`.

## Licensing and attribution

The **code** — `messy_streets/`, `src/`, `tools/`, `pipeline/`, `tests/` and the
container files — is MIT. See `LICENSE`.

The **data** under `data/` carries the terms of its three origins, set out in
`LICENSE-DATA`:

> Contains information from OpenStreetMap, © OpenStreetMap contributors,
> available under the Open Database License 1.0.
> https://www.openstreetmap.org/copyright

7,842 records in the gold and silver tiers were verified against OpenStreetMap,
drawn from 7,689 distinct ways. Their `aux.existence` fields — way identifier,
street name, geometry and administrative hierarchy — are ODbL 1.0. Way
identifiers are retained throughout so provenance stays explicit. A further
12,158 records were verified against OpenAddresses and carry its per-source
terms, each keeping its `oa_source` field. The address records themselves come
verbatim from the December 2024 Web Data Commons corpus.

A request confirming this arrangement was sent to the OpenStreetMap Foundation
Licensing Working Group on 20 August 2026; `LICENSE-DATA` records that its
answer is still outstanding.

## Still outstanding

The credentials in the *source* tree at `~/phd` and `~/SerenTec` need rotating.
That exposure is on the research machine, not in this repository — `tools/vendor.py`
strips credentials mechanically on the way in and `tests/run.sh` re-checks. See
`TODO.md`.

## Citation

Pending a DOI. `croissant.json` carries the citation text.
