# Deferred until every slice is built

> All eight slices are built. Item 1 is the only one that still blocks
> anything, and it is about the research machine rather than this repository.

Three items block publication but not progress. They are parked here
deliberately: each is either external-latency or a decision that does not
change what gets built, and none of them make the remaining slices easier if
done first. Address them once slices 1–8 are complete.

## 1. Rotate credentials

**17 distinct credentials across 44 locations** in the source tree at `~/phd`,
plus the SMTP password in `~/SerenTec/serentec/config.py`. Rotate at the
provider first, then delete — all sit in module docstrings and READMEs, and
nothing imports them.

| Credential | Occurrences | First location |
|---|---|---|
| `ANTHROPIC_API_KEY` | 4 | `phd/models/models/anthropic/model.py:5` |
| `AZURE_MAPS_API_KEY` | 2 | `phd/models/models/azure_maps/model.py:17` |
| `GEMINI_API_KEY` | 5 | `phd/models/models/google-gemini-finetune/model.py:5` |
| `GEOAPIFY_MAPS_API_KEY` | 1 | `phd/models/models/geoapify/model.py:17` |
| `GEOCODE_EARTH_API_KEY` | 1 | `phd/models/models/pelias/model.py:27` |
| `GOOGLE_MAPS_API_KEY` | 1 | `phd/models/models/google-geocoding/model.py:15` |
| `HERE_API_KEY` | 1 | `phd/models/models/here/model.py:17` |
| `HF_TOKEN` | 4 | `phd/models/models/transformers_inference/model.py:14` |
| `MAPBOX_API_KEY` | 1 | `phd/models/models/mapbox/model.py:17` |
| `MAPQUEST_API_KEY` | 1 | `phd/models/models/openmapquest/model.py:9` |
| `MISTRAL_API_KEY` | 5 | `phd/models/models/mistral/model.py:8` |
| `OLLAMA_API_KEY` | 2 | `phd/models/models/ollama-cloud/model.py:21` |
| `OPENAI_API_KEY` | 6 | `phd/models/models/_openai_chatgpt_batch/model.py:9` |
| `OPENCAGE_API_KEY` | 1 | `phd/models/models/opencage/model.py:17` |
| `REPLICATE_API_TOKEN` | 7 | `phd/models/models/gemma_replicate/model.py:6` |
| `TOMTOM_API_KEY` | 1 | `phd/models/models/tomtom/model.py:17` |
| `XAI_API_KEY` | 1 | `phd/models/models/grok/model.py:15` |

Nine of these are the geocoder keys this artefact can use. Once rotated, put
the new values straight into the credentials file without them passing through
a shell history or a file you might commit:

```sh
./messy-streets credentials --set here mapbox tomtom
```

**Not a risk to this repository.** `tools/vendor.py` strips credentials
mechanically on the way in, and `tests/test_credentials.py` now sweeps every
tracked file on every test run. The exposure is on the research machine, and it
exists whether or not the artefact is ever published.

## 2. Licensing — decided, one answer outstanding

**Done.** Code is MIT (`LICENSE`). Data terms are stated per origin in
`LICENSE-DATA`, with the ODbL notice and OpenStreetMap attribution carried into
`README.md` and into the `license` and `creditText` fields of `croissant.json`.

**Outstanding:** a request was sent to the OSMF Licensing Working Group on
20 August 2026 asking whether the arrangement is compliant as described — full
attribution, explicit ODbL notice, way identifiers retained. The draft is at
`phd/publications/messy_streets/OSM_Request.md`. If their answer calls for a
change, `LICENSE-DATA` is the file to change, and the Croissant metadata is
regenerated with `python3 tools/croissant.py`.

Nothing blocks release on this; the notice is in place and states its own
status.

## 3. SerenTec: vendor or refactor

25 modules, ~4,000 lines, currently vendored. Not a rights question — SerenTec
is the author's own library — so this is a choice between two positions:

Vendoring ships the code that actually produced the paper, which is the
stronger reproducibility claim and is what the artefact does today. Refactoring
against the standard library publishes less, but puts new and untested code
between the artefact and the paper's numbers.

The only external consideration is commercial: if SerenTec is intended as a
company name, publishing under a permissive licence puts 25 of its modules in
the open permanently. What is actually vendored is unremarkable — logging, JSON
loading, a string comparator, a script classifier — but it is a one-way door.

Deferred deliberately: the vendored path works and the decision is reversible
until the push.

---

# Smaller open items

These do not block publication, but they are promises made and not yet kept.

## Continent shares in `stats`

Slice 4 deferred the Biases paragraph's continent figures to slice 5, on the
grounds that the paper resolves them through `normalise_country` in the dataset
generator, which slice 5 vendors. Slice 5 came and went without them, and the
reason is worth writing down: `normalise_country` reads
`self.country_suffix_regex` and `self.COUNTRY_OVERRIDES`, both built in
`Generate.__init__` alongside database connections and a data directory. Using
it standalone means either constructing the full generator or lifting those two
attributes out — neither is a one-liner, and substituting country_converter's
plain fuzzy matching gives visibly different answers (America 50.7% against the
published 49%, plus an Africa share the paper does not mention).

Script shares reproduce and are reported. Continent shares are simply absent,
which `messy-streets stats` says out loud.
