# Artefact appendix

> **Draft.** Sections marked *(pending)* are completed by the slice that
> produces the thing they describe.

## Summary

This artefact reproduces the results of *MESSY STREETS: A Benchmark for
Geocoding Real-World Addresses*. It contains the benchmark's three released
tiers, the cached geocoder predictions behind both tables in the paper, the
code that turns those into the published LaTeX, and documentation of the
fifteen-stage pipeline that constructed the dataset.

## What is and is not reproducible

The artefact is explicit about this rather than implying uniform
reproducibility.

- **Reproducible offline, bit-for-bit** — the released tiers and their
  statistics (L0), both paper tables from cached predictions (L1), and the
  benchmark slices regenerated at seed 42 (L2). No network, no API keys.
- **Reproducible in principle, but not identical** — live re-query of the
  twelve geocoders (L3). Requires nine commercial API keys — Nominatim, Photon
  and ArcGIS need none — and roughly fourteen hours at the rate limits the
  wrappers apply. Commercial geocoding services and the OpenStreetMap snapshots behind
  the open-source ones have changed since June 2026, so the numbers will
  differ. This layer reproduces the *finding* — that surface-form divergence
  dominates component completeness as a source of failure — not the figures.
- **Documented, not reproducible** — construction of the tiers from the
  December 2024 Web Data Commons corpus (L4). Needs a 10.7 GB OpenAddresses
  and an 89.5 GB OpenStreetMap street database, and a quantised 35B judge model
  on four GPUs. The code ships and the stages are individually inspectable, but
  no evaluator is expected to run it.

## Known deviations *(pending)*

Recorded here rather than left for a reviewer to discover.

- **Pelias, Table 4.** Rebuilding from the shipped predictions yields
  CRR 96.7 ±1.8 and GH1 94.2 ±2.4 where the paper prints 96.6 ±1.8 and
  94.1 ±2.5. These are the only two cells in Tables 4 and 5 that differ; the
  other 78 match exactly, including every error bar. Both deviations are
  0.1 percentage points, within the printed precision, and neither affects a
  claim in the paper. The cause was not investigated.

  They are declared in `data/expected/table4.json` with the value the rebuild
  is expected to produce, so `messy-streets tables` reports them as known
  deviations rather than failures — and still fails if either one changes.
- **`NaN` in the released JSONL.** The tier files use bare `NaN` for absent
  values, which `jq` and Python accept but strict RFC 8259 parsers — JavaScript
  `JSON.parse`, Go, Rust — reject. Parse with `jq` or Python.
- **Provenance paths.** `aux.address.part` retains the source corpus path from
  the machine the extraction ran on.

- **Table 3 does not reproduce from the released tiers.** Three separate
  issues, all surfaced by `messy-streets stats`:

  *Method.* Each published cell is the share over 1,000 observations sampled
  from a benchmark slice, not over the 10,000 records of the released tier.

  *Provenance.* The source database differs by row: gold from `hq_10000` and
  raw from `lq_10000`, but silver from `mq_1000` — a 1,000-record pre-release
  database, not the released silver tier.

  *Internal disagreement.* Six of the fifteen cells differ from the analysis
  outputs that the paper's own method produced, by up to 2.8 percentage points:

  | Tier | Component | Paper | Its analysis output |
  |------|-----------|-------|---------------------|
  | raw | Street | 100.0 | 99.9 |
  | raw | Country | 63.5 | 65.5 |
  | raw | Postcode | 82.2 | 80.4 |
  | raw | Locality | 95.9 | 95.6 |
  | raw | Region | 76.3 | 73.5 |
  | silver | Locality | 96.8 | 96.0 |

  `stats` reports all three figures side by side rather than choosing one. The
  qualitative claims Table 3 supports — street universal, gold complete by
  construction, silver and raw frequently lacking country and postcode — hold
  under every one of the three.

## Why the data is copied at container start

The reproduction pipeline writes results back into its own inputs: results land
beside the cached predictions they were replayed from, and the sampler
materialises a table into the tier database on first use. Running that against
the baked image would mutate the artefact, and a partially failed run could
truncate the cache that makes offline reproduction possible.

The image is therefore immutable and mounted read-only, and the entrypoint
copies the tree once into the output mount. Inputs and outputs then sit side by
side on the host, and a botched run is repaired by deleting `out/work`.

- **The benchmark slices cannot be regenerated bit-identically.** DuckDB's
  `USING SAMPLE reservoir(N ROWS) REPEATABLE(seed)` is reproducible within a
  version, not across versions, and the DuckDB version used to cut the slices
  is not recorded anywhere. Redrawing with the pinned 1.4.4 gives a
  self-consistent but different sample — 28 of 500 records in common. Thread
  count is not the cause: in 1.4.4 the sample is identical at 1 thread and at
  8, so the pin documented under *Determinism* turns out not to be
  load-bearing for this version. A test asserts it, so if a future DuckDB makes
  sampling thread-sensitive the pin becomes load-bearing again and the test
  says so.

  `messy-streets sample` therefore checks provenance instead of regeneration:
  every record in every shipped slice must resolve to a row in the tier
  database with a consistent geohash. 14,964 of 15,000 do.

- **Nine addresses appear in a slice but not in the released gold tier.** The
  slices are shipped verbatim — they are what the experiments ran against — but
  the tier was edited afterwards by the disjointness repair (pipeline stage 9),
  which deletes cross-tier overlaps and inserts replacements. Two of the nine
  are still present in the tier's own `deleted` table, which is what that
  repair leaves behind. Declared in `data/expected/slice-provenance.json` so
  the check reports them as known and still fails if the set changes.

## What was removed before release

The tier databases in the research tree carry four tables beyond the released
addresses: `discarded` — every rejected candidate with the reason, including
**180 records the PII judge removed** — and `backup`, `deleted` and
`replacements`, the artefacts of the disjointness repair. Shipping them would
have published precisely the records the privacy filter took out, each labelled
with why it was flagged.

The shipped databases contain the `addresses` table and nothing else.
`tools/strip_tiers.py` rebuilds them that way, and a test asserts that no other
table is reachable. Nothing in the artefact needed them: `sample` and the
stage-9 repair script query `addresses` only.

## Requirements

- A container runtime — Docker or podman. Nothing else. The image builds
  natively on `linux/amd64` and `linux/arm64`; every dependency ships a
  prebuilt wheel, so no compiler is involved on either.
- ~1 GB of disk for the image and the working copy.
- No GPU, no network, no accounts, for everything except L3.

Without a container runtime the artefact also installs and runs natively on
Python 3.12.3; see the README.

## Determinism

Three things are pinned inside the image because results depend on them:

- **DuckDB thread count** (`MS_DUCKDB_THREADS=1`). The benchmark sampler uses
  `USING SAMPLE reservoir(N ROWS) REPEATABLE(seed)`, whose result can depend on
  how work is scheduled across cores.
- **DuckDB version** (1.4.4, exactly). Sample reproducibility holds within a
  version and is not guaranteed across them.
- **Locale, timezone and hash seed** (`C.UTF-8`, `UTC`, `PYTHONHASHSEED=0`).
  The benchmark contains Cyrillic, CJK, Greek and Arabic records.

`messy-streets doctor` reports all three.

## Licences

Code is MIT (`LICENSE`). Data carries the terms of its three origins
(`LICENSE-DATA`), stated per field rather than in aggregate:

| Origin | Records | Terms |
|--------|---------|-------|
| OpenStreetMap, via `aux.existence` where `source` is `osd` | 7,842 | ODbL 1.0, attribution required |
| OpenAddresses, via `aux.existence` where `source` is `oa` | 12,158 | per-source; `oa_source` retained on each record |
| Web Data Commons, the address records themselves | 30,000 | research use, verbatim |

OSM way identifiers are retained rather than stripped, so any record's
provenance can be traced back to the way it was matched against. The ODbL
notice appears in `LICENSE-DATA`, in `README.md`, and in the `license` and
`creditText` fields of `croissant.json`, so a machine reading only the metadata
still sees the obligation.

A request confirming this arrangement was put to the OpenStreetMap Foundation
Licensing Working Group on 20 August 2026. No answer yet; `LICENSE-DATA` says
so, and will be updated if their answer calls for a change.

## Defects found while building the artefact

Six, all on the offline-replay path — a mode the source tree was never
actually run in. None change what the pipeline computes when running live.
Each is recorded in `VENDOR.md` with its rationale.

Three are in `error_bars.py`, the command that produces the paper's tables:
it never passed `assert_cache` down to the table builder, so the rebuild
constructed a geocoder client for every row and died on the missing API key;
and it read `self.timeout` and `self.batch`, attributes that do not exist. The
latter means the rebuild-from-scratch path had never executed — the published
error-bars tables were assembled from per-run results that already existed on
disk.

One is in `build_table.py`: `json.dumps` used but not imported.

The remaining two are the replay-cache defect described below.

## The replay-cache defect

Offline replay did not originally work for observations where a geocoder
returned no candidate. Such observations are recorded with a null prediction
and `has_prediction: false`, and the replay cache was seeded only from
observations that had a prediction — so reproducing them raised rather than
returning the recorded "no candidate". For Nominatim on the gold tier that is
38 of 100 observations, and it is precisely the paper's headline finding.

Two patches fix it: seed the cache from every observation that completed
without an exception, and derive `has_prediction` from the cached value rather
than assuming a cache hit implies a prediction. Both are recorded in
`VENDOR.md`. Neither changes what the pipeline computes when running live;
they only affect replay, which is a mode the source tree was never run in.

A third patch supplies a missing `json.dumps` import in `build_table.py`.

## Evaluation walkthrough

Nothing below needs a network connection, an account, or a GPU.

### 1. Does this machine work? (~5 s)

```sh
./messy-streets doctor
```

Checks the host first — container runtime, image digest, mount, architecture —
then, inside, the dependency pins and 8,324 data checksums. Any failure names
the thing that failed. `--json` output is what to paste if it does.

### 2. Does anything reproduce? (~20 s)

```sh
./messy-streets smoke
```

Rebuilds run 1 of the ten behind Table 4 — twelve geocoders, 100 addresses, 48
cells — from predictions recorded when the experiments ran. Expect
`REPRODUCED — 48 of 48 cells match`.

### 3. The paper's result tables (~4 min)

```sh
./messy-streets tables
```

Rebuilds the five error-bars tables behind Tables 4 and 5 and compares every
published cell — mean *and* error bar — against the LaTeX that was `\input`
into the paper. Expect `REPRODUCED — 78 of 80 published cells match exactly`
plus the two declared Pelias deviations described above.

### 4. The dataset tables (~10 s each)

```sh
./messy-streets pipeline show 3     # Table 2: 9 of 9 cells
./messy-streets stats               # Table 3: recomputed, and it disagrees
```

Table 2 verifies exactly. Table 3 does not, for the reasons under *Known
deviations* — `stats` prints the released, analysed and published figures side
by side rather than choosing one.

### 5. The data itself

```sh
./messy-streets inspect --tier gold -n 5
./messy-streets inspect --tier silver --missing country -n 5
./messy-streets sample
./messy-streets pipeline
```

`inspect` shows addresses with the reference each was verified against.
`sample` checks every shipped benchmark slice back to the tier database it was
drawn from. `pipeline` lists the fifteen construction stages.

### Expected exit codes

| Command | Expected |
|---------|----------|
| `doctor`, `smoke`, `tables`, `stats`, `sample`, `pipeline`, `inspect` | 0 |
| `geocode` without `--i-supply-my-own-keys` | 0, having queried nothing |

A `1` is a mismatch against a published number. A `2` is an environment or data
problem — run `doctor`. A `3` means the layer is not available here.

### What a reviewer cannot do

Re-run the construction pipeline (stages 1–10 need 106 GB of reference data and
a 35B judge model on four GPUs), or reproduce the live geocoder numbers (the
services have moved). Both are documented rather than hidden: `pipeline show
<n>` describes each stage and what it would take, and `geocode` measures drift
against the recorded predictions instead of pretending to reproduce them.
