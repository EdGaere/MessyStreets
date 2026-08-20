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

L0–L2 are the artefact's actual promise. L3 reproduces the *finding*, not the
figures: the services and their OpenStreetMap snapshots have moved on. L4 is
shipped as fifteen documented stages so the construction method is inspectable
even though re-running it is not realistic.

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
