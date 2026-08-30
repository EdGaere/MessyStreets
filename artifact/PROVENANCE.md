# Provenance

How the numbers in this artefact relate to the numbers in the paper, where
those two have more than one lineage, and which one supersedes which.

## Table 3 — component existence

Table 3 has had two sets of values. They differ because they were computed over
different data, not because either was wrong when it was computed.

**Pre-release draft.** Early values were computed on an earlier tier snapshot,
before the disjointness repair (pipeline stage 9) rewrote the tiers, and in one
case from a 1,000-record pre-release database rather than the released 10,000.
Those values differed from the released tiers in 10 of 15 cells, by up to
2.8 percentage points.

**Camera-ready.** The published table reports values computed over all 10,000
records of each released tier. `messy-streets stats` recomputes them and matches
all fifteen cells exactly.

The camera-ready supersedes the draft. The draft values are recorded here so
the history is not lost:

| Component | Tier | Pre-release draft | Camera-ready | Δ pp |
|---|---|---|---|---|
| Street | gold | 100.0 | 100.0 | — |
| Street | silver | 100.0 | 100.0 | — |
| Street | raw | 100.0 | 100.0 | — |
| Country | gold | 100.0 | 100.0 | — |
| Country | silver | 65.8 | 64.8 | 1.0 |
| Country | raw | 63.5 | 64.5 | 1.0 |
| Postcode | gold | 100.0 | 100.0 | — |
| Postcode | silver | 83.5 | 85.3 | 1.8 |
| Postcode | raw | 82.2 | 82.4 | 0.2 |
| Locality | gold | 98.6 | 98.7 | 0.1 |
| Locality | silver | 96.8 | 97.6 | 0.8 |
| Locality | raw | 95.9 | 96.0 | 0.1 |
| Region | gold | 69.2 | 69.9 | 0.7 |
| Region | silver | 71.7 | 73.2 | 1.5 |
| Region | raw | 76.3 | 73.5 | 2.8 |

## Table 3 — the analysis lineage

`data/expected/table3.json` also carries `analysis_output`: the figures the
paper's own analysis scripts emitted, a third lineage distinct from both the
draft and the released tiers. Those differ from the camera-ready in 10 of 15
cells, by up to 2.0 percentage points, and are retained under `disagreements`.

This is not a reproduction failure. `messy-streets stats` reproduces the
published table exactly; the analysis outputs are a separate historical record,
kept so the difference stays visible rather than being quietly dropped.

## Tables 2, 4 and 5 — camera-ready trimming

The camera-ready was trimmed to four pages after the June submission. Two
changes alter the *shape* of a table without altering any measurement:

- **Table 2** merges four coordinate-filter rows (missing latitude, missing
  longitude, out-of-range, non-numeric) into one row, `Invalid or missing
  coordinates`, 1,413,843. The components still sum to the published total and
  each is still recorded in `data/pipeline/wdc-filter-stats.json`.
- **Table 4** shows seven of the twelve evaluated geocoders. Here v7, TomTom v2,
  Geoapify, Mapbox v5 and Azure Maps were removed for space; none is discussed
  in the body and none held a best or worst value. Their measurements are
  unchanged and remain in `data/expected/table4.json`.

The artefact's references for Tables 2 and 4 still describe the twelve-geocoder,
seven-row-cascade form as submitted in June. Aligning them to the camera-ready
shape is deliberately not done here: it is a decision about what the artefact
should attest to, not a mechanical refresh.

## Measurement drift

Geocoder results in the paper were measured in June 2026; live re-runs will
differ as providers update their services and data.

No value in `data/expected/` is produced by a live query. Every block is
recomputed from the released tiers or replayed from predictions recorded in
June, so the whole verification suite runs air-gapped. The only verb that
touches a geocoder is `geocode`, which reports drift against those recorded
predictions and never writes a published value.
