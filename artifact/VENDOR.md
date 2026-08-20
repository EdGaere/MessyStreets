# Vendored dependency closure

Copied from the source tree by `tools/vendor.py`. Do not edit in place:
change the source and re-run, or the two silently diverge.

`python3 tools/vendor.py --source <tree> --check` reports drift.

Hashes are of the **source** file before credential scrubbing, so a
vendored copy can be traced back to the exact bytes that produced the
paper.

## slices 2-3 — smoke and tables: rebuild the paper's tables from cached predictions

| Module | Source sha256 | Lines scrubbed |
|--------|---------------|----------------|
| `phd/__init__.py` | `9eba61ad4e80ade8…` |  |
| `phd/experiments/__init__.py` | `9eba61ad4e80ade8…` |  |
| `phd/experiments/config.py` | `4432148ea8db5efd…` |  |
| `phd/experiments/run_experiment.py` | `94598b19f068e613…` |  |
| `phd/experiments/run_experiment_batch.py` | `84f4ef6f1281ed3b…` |  |
| `phd/models/__init__.py` | `9eba61ad4e80ade8…` |  |
| `phd/models/load_model.py` | `445df489a6065c51…` |  |
| `phd/models/model_base.py` | `c7ab9a7e6a9661d3…` |  |
| `phd/tables/build_table.py` | `ea43f85412c09e1e…` | 6 |
| `phd/tables/error_bars.py` | `a9874157a4a9181e…` |  |
| `serentec/__init__.py` | `e3b0c44298fc1c14…` |  |
| `serentec/exceptions.py` | `6c2543ec0b173e98…` |  |
| `serentec/ingestion/__init__.py` | `9eba61ad4e80ade8…` |  |
| `serentec/ingestion/load_benchmark.py` | `cec410501a7692b5…` |  |
| `serentec/ml/__init__.py` | `52029e2bb0c007ac…` |  |
| `serentec/ml/config.py` | `abd03b7f255dda27…` |  |
| `serentec/ml/llm/__init__.py` | `52029e2bb0c007ac…` |  |
| `serentec/ml/llm/prompts.py` | `d9d08acf6c486872…` |  |
| `serentec/ml/llm/responses.py` | `57a9d7ee4224735c…` |  |
| `serentec/utils/__init__.py` | `9eba61ad4e80ade8…` |  |
| `serentec/utils/check_isinstance.py` | `f16211c2f0e6495a…` |  |
| `serentec/utils/comparator.py` | `115127c3db213d4e…` |  |
| `serentec/utils/exception_info.py` | `53cbc7769084cba3…` |  |
| `serentec/utils/file/__init__.py` | `52029e2bb0c007ac…` |  |
| `serentec/utils/file/check_isfile.py` | `5fc453c27e469211…` |  |
| `serentec/utils/interpreters/__init__.py` | `9eba61ad4e80ade8…` |  |
| `serentec/utils/interpreters/python_interpreter.py` | `2776c1f51c211d4c…` |  |
| `serentec/utils/json/__init__.py` | `36963a03fe681b16…` |  |
| `serentec/utils/json/load_json.py` | `5c2cde2ea556590b…` |  |
| `serentec/utils/logger.py` | `f89c73809ff81a9a…` |  |
| `serentec/utils/optional_abstractmethod.py` | `4b35230711e95b0a…` |  |
| `serentec/utils/parse_function_args.py` | `ac6da2213c635944…` |  |
| `serentec/utils/timeout.py` | `8f5a390d1e43139f…` |  |

## slice 4 — stats and inspect: dataset-level figures from the released tiers

| Module | Source sha256 | Lines scrubbed |
|--------|---------------|----------------|
| `serentec/utils/strings/__init__.py` | `52029e2bb0c007ac…` |  |
| `serentec/utils/strings/dominant_script.py` | `de7086b31b1709d7…` |  |

## slice 7 — geocode: the twelve geocoder wrappers

| Module | Source sha256 | Lines scrubbed |
|--------|---------------|----------------|
| `phd/models/models/__init__.py` | `9eba61ad4e80ade8…` |  |
| `phd/models/models/arcgis/model.py` | `b9757346e81ad91b…` |  |
| `phd/models/models/azure_maps/model.py` | `4fa722f9abbfdf4a…` | 1 |
| `phd/models/models/geoapify/model.py` | `8814052870b9edb6…` | 1 |
| `phd/models/models/google-geocoding/model.py` | `46f2957d25e01a5f…` | 1 |
| `phd/models/models/here/model.py` | `c890ca65cd9b840a…` | 1 |
| `phd/models/models/mapbox/model.py` | `2ac91454fe25a5a0…` | 1 |
| `phd/models/models/nominatim/model.py` | `edc174783dcf9724…` |  |
| `phd/models/models/opencage/model.py` | `e221b020f28832be…` | 1 |
| `phd/models/models/openmapquest/model.py` | `e2b579f13d515dc3…` | 1 |
| `phd/models/models/pelias/model.py` | `5e88a3430b17c1a5…` | 1 |
| `phd/models/models/photon/model.py` | `0605cdbb4aac9019…` |  |
| `phd/models/models/tomtom/model.py` | `eeac97a6714a4022…` | 1 |
| `serentec/backend/__init__.py` | `9eba61ad4e80ade8…` |  |
| `serentec/backend/cache/__init__.py` | `9eba61ad4e80ade8…` |  |
| `serentec/backend/cache/disk_cache/__init__.py` | `5f95bc871e5156ed…` |  |
| `serentec/backend/cache/disk_cache/adisk_cache.py` | `08c1741856a783f1…` |  |
| `serentec/backend/cache/disk_cache/disk_cache.py` | `b9a84372f526cd07…` |  |

## slice 5 — sample: regenerate the benchmark slices from the tier databases

| Module | Source sha256 | Lines scrubbed |
|--------|---------------|----------------|
| `phd/benchmarks/__init__.py` | `9eba61ad4e80ade8…` |  |
| `phd/benchmarks/create_benchmark.py` | `ff97e2d2bc308040…` |  |
| `phd/datasets/__init__.py` | `9eba61ad4e80ade8…` |  |
| `phd/datasets/address/__init__.py` | `9eba61ad4e80ade8…` |  |
| `phd/datasets/address/messy_streets/v0/generators/v2.py` | `2ccb6ae7c5fd699e…` |  |
| `phd/datasets/address/messy_streets/v0/generators/v3.py` | `708cfa3a34f9ace5…` |  |
| `serentec/config.py` | `04f70665bb665187…` |  |
| `serentec/ml/generators/__init__.py` | `9eba61ad4e80ade8…` |  |
| `serentec/ml/generators/load_generator.py` | `0a588d488bad0bca…` |  |
| `serentec/ml/generators/load_generators.py` | `e8905cc1befd72bb…` |  |
| `serentec/ml/training_pair.py` | `ff536065d863e5f7…` |  |
| `serentec/utils/analysis/descriptive_stats.py` | `a99d1a9de57f21fb…` |  |
| `serentec/utils/analysis/histogram.py` | `f12bb48a628eeac8…` |  |
| `serentec/utils/strings/insert_noise.py` | `4028441f96948473…` |  |
| `serentec/utils/strings/lexical_similarity.py` | `a1b8e3703759f30b…` |  |

## Patches applied

Modifications to the vendored copy, defined in `tools/patches.py`.
None change what the pipeline computes.

### `phd/experiments/run_experiment.py` — Replay cache must include observations with no prediction

A geocoder returning no candidate is a result, not a failure — it is precisely what Candidate Return Rate measures, and it is the paper's headline finding for the open-source geocoders. But such observations are recorded with has_prediction=False and were never seeded into the replay cache, so offline reproduction raised on them. For Nominatim on the gold tier that is 38 of 100 observations. Seed every prior result that completed without an exception; an exception is a genuine failure and stays out.

### `phd/experiments/run_experiment.py` — A cache hit does not imply a prediction was made

Follows from the patch above. With null predictions now cached, hardcoding has_prediction=True on a cache hit would count every no-candidate result as a candidate and inflate Candidate Return Rate to 100% for every geocoder. Derive it from the value instead.

### `phd/tables/build_table.py` — Missing json.dumps import

`dumps` is used in three places — serialising dict fields for the SQLite export, and writing output.json and stats.json — but is never imported, so the module raises NameError as soon as an observation carries a dict field. Every observation does: `comparison` is {lhs, rhs}. A plain missing import, fixed rather than worked around.

### `phd/tables/error_bars.py` — Offline replay flag reaches the table builder

error_bars.py is the top-level command that produces the paper's tables, but it accepted only try_cache and re_run_all and never passed assert_cache down to BuildTable.run(). Without it the rebuild constructs a geocoder client for every row and dies on the missing API key — so the one command that matters could not run offline at all. Adding the parameter and threading it through is the whole fix.

### `phd/tables/error_bars.py` — ... and is honoured when the sub-table is built

The second half of the patch above: pass it on to BuildTable.run().

### `phd/tables/error_bars.py` — Two attribute names that never existed

`self.timeout` and `self.batch` are read when constructing the sub-table builder; the attributes are named `self.timeout_seconds` and `self.batch_mode`. Both raise AttributeError. They sit on the path that rebuilds a sub-table from scratch, which means that path has never run: the paper's error-bars tables were assembled from per-run rendered.json files that already existed, and the end-to-end rebuild the artefact needs was untested code.

### `phd/tables/error_bars.py` — Invalid escape sequence in the cell formatter

`\pm` inside a non-raw f-string is an invalid escape sequence. It happens to produce the right LaTeX today, but Python emits a SyntaxWarning on every run and the sequence becomes an error in a future version. Made explicit rather than left to luck.

### `phd/experiments/config.py` — Prediction cache location is configurable, and not shared

The cache directory was hardcoded to /tmp/cache on Linux and the module raised on any platform that was not Darwin or Linux. A fixed path under /tmp is also shared between concurrent runs and survives between them, which for a reproduction artefact means one run can silently answer from another run's cache.

### `phd/experiments/config.py` — Import path used by the patch above

`path` is referenced by the cache-directory fallback.

