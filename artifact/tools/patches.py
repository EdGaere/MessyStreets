"""Modifications applied to the vendored closure, and why.

Every patch is an exact find-and-replace with enough context to be unambiguous.
Applying one fails loudly if the source text is not found exactly once, so a
change upstream cannot silently pass through unpatched.

Nothing here changes what the pipeline computes. Each patch either removes a
dependency on the machine the paper was produced on, or fixes a defect that
only shows up when replaying results offline — which is the mode the source
tree was never actually run in.
"""

from typing import List, NamedTuple


class Patch(NamedTuple):
    module: str
    title: str
    why: str
    old: str
    new: str
    # When set, everything from `old` through the first following occurrence of
    # `until` (inclusive) is replaced. Lets a patch excise a block without
    # quoting its contents -- necessary when the contents are a credential,
    # which must not end up in this file either.
    until: str = ""


PATCHES: List[Patch] = [

    Patch(
        module="phd/experiments/run_experiment.py",
        title="Replay cache must include observations with no prediction",
        why=(
            "A geocoder returning no candidate is a result, not a failure — it is "
            "precisely what Candidate Return Rate measures, and it is the paper's "
            "headline finding for the open-source geocoders. But such observations "
            "are recorded with has_prediction=False and were never seeded into the "
            "replay cache, so offline reproduction raised on them. For Nominatim on "
            "the gold tier that is 38 of 100 observations. Seed every prior result "
            "that completed without an exception; an exception is a genuine failure "
            "and stays out."
        ),
        old="""                has_prediction = prior_result.get("has_prediction", False)
                if has_prediction:
                    cache_hash, prediction, probability = prior_result["cache_hash"], prior_result["prediction"], prior_result["probability"]
                    self.cache.set(cache_hash, (prediction, probability))
                    all_results_cached += 1""",
        new="""                # A null prediction is a recorded outcome (the geocoder returned
                # no candidate), not a missing one, so it belongs in the cache.
                # Only observations that raised are excluded.
                if prior_result.get("exception") is None:
                    cache_hash, prediction, probability = prior_result["cache_hash"], prior_result["prediction"], prior_result["probability"]
                    self.cache.set(cache_hash, (prediction, probability))
                    all_results_cached += 1""",
    ),

    Patch(
        module="phd/experiments/run_experiment.py",
        title="A cache hit does not imply a prediction was made",
        why=(
            "Follows from the patch above. With null predictions now cached, "
            "hardcoding has_prediction=True on a cache hit would count every "
            "no-candidate result as a candidate and inflate Candidate Return Rate "
            "to 100% for every geocoder. Derive it from the value instead."
        ),
        old="""                    prediction, probability = self.cache[cache_hash]
                    has_prediction = True""",
        new="""                    prediction, probability = self.cache[cache_hash]
                    has_prediction = prediction is not None""",
    ),

    Patch(
        module="phd/tables/build_table.py",
        title="Missing json.dumps import",
        why=(
            "`dumps` is used in three places — serialising dict fields for the "
            "SQLite export, and writing output.json and stats.json — but is never "
            "imported, so the module raises NameError as soon as an observation "
            "carries a dict field. Every observation does: `comparison` is "
            "{lhs, rhs}. A plain missing import, fixed rather than worked around."
        ),
        old="""from random import randint
from os import path, environ, makedirs
from sqlite3 import connect""",
        new="""from json import dumps
from random import randint
from os import path, environ, makedirs
from sqlite3 import connect""",
    ),

    Patch(
        module="phd/tables/error_bars.py",
        title="Offline replay flag reaches the table builder",
        why=(
            "error_bars.py is the top-level command that produces the paper's "
            "tables, but it accepted only try_cache and re_run_all and never "
            "passed assert_cache down to BuildTable.run(). Without it the rebuild "
            "constructs a geocoder client for every row and dies on the missing "
            "API key — so the one command that matters could not run offline at "
            "all. Adding the parameter and threading it through is the whole fix."
        ),
        old="""    async def run(self
                  , auto_run : bool = False
                  , re_run_all : bool = False
                  , try_cache : bool = False
                  , stop_on_error : bool = False
                  , skip_missing : bool = False
                  ) -> Tuple[List[DataFrame], List[Dict]]:""",
        new="""    async def run(self
                  , auto_run : bool = False
                  , re_run_all : bool = False
                  , try_cache : bool = False
                  , assert_cache : bool = False
                  , stop_on_error : bool = False
                  , skip_missing : bool = False
                  ) -> Tuple[List[DataFrame], List[Dict]]:""",
    ),

    Patch(
        module="phd/tables/error_bars.py",
        title="... and is honoured when the sub-table is built",
        why="The second half of the patch above: pass it on to BuildTable.run().",
        old="""                _, _auto_run_df_table, _auto_run_exceptions = await build_table.run(auto_run=auto_run
                                               , re_run_all=re_run_all
                                               , try_cache=try_cache
                                               , stop_on_error=stop_on_error
                                               , skip_missing=skip_missing
                                               )""",
        new="""                _, _auto_run_df_table, _auto_run_exceptions = await build_table.run(auto_run=auto_run
                                               , re_run_all=re_run_all
                                               , try_cache=try_cache
                                               , assert_cache=assert_cache
                                               , stop_on_error=stop_on_error
                                               , skip_missing=skip_missing
                                               )""",
    ),

    Patch(
        module="phd/tables/error_bars.py",
        title="Two attribute names that never existed",
        why=(
            "`self.timeout` and `self.batch` are read when constructing the "
            "sub-table builder; the attributes are named `self.timeout_seconds` "
            "and `self.batch_mode`. Both raise AttributeError. They sit on the "
            "path that rebuilds a sub-table from scratch, which means that path "
            "has never run: the paper's error-bars tables were assembled from "
            "per-run rendered.json files that already existed, and the "
            "end-to-end rebuild the artefact needs was untested code."
        ),
        old="""                build_table = BuildTable(table_name
                                 , timeout_seconds=self.timeout
                                 , run_number=self.run_number
                                 , batch_mode=self.batch
                                 , debug=self.debug
                                 , debug2=self.debug2
                                 )""",
        new="""                build_table = BuildTable(table_name
                                 , timeout_seconds=self.timeout_seconds
                                 , run_number=self.run_number
                                 , batch_mode=self.batch_mode
                                 , debug=self.debug
                                 , debug2=self.debug2
                                 )""",
    ),

    Patch(
        module="phd/tables/error_bars.py",
        title="Invalid escape sequence in the cell formatter",
        why=(
            "`\\pm` inside a non-raw f-string is an invalid escape sequence. It "
            "happens to produce the right LaTeX today, but Python emits a "
            "SyntaxWarning on every run and the sequence becomes an error in a "
            "future version. Made explicit rather than left to luck."
        ),
        old='            inner = f"\\\\mathrm{{{100*m:.{decimals}f}}}_{{{{\\pm {100*2*s:.{decimals}f}}}}}"',
        new='            inner = f"\\\\mathrm{{{100*m:.{decimals}f}}}_{{{{\\\\pm {100*2*s:.{decimals}f}}}}}"',
    ),

    Patch(
        module="phd/experiments/config.py",
        title="Prediction cache location is configurable, and not shared",
        why=(
            "The cache directory was hardcoded to /tmp/cache on Linux and the module "
            "raised on any platform that was not Darwin or Linux. A fixed path under "
            "/tmp is also shared between concurrent runs and survives between them, "
            "which for a reproduction artefact means one run can silently answer from "
            "another run's cache."
        ),
        old="""        # prompt cache
        if system() == r'Darwin':
            self.cache_dir = r"/users/gaeree/data/cache/phd/prompts.cache"
        elif system() == r'Linux':
            self.cache_dir = r"/tmp/cache"
        else:
            raise RuntimeError(f"System not supported | {system()}")""",
        new="""        # prompt cache
        # MS_CACHE_DIR is set by the artefact to a per-run directory, so replays
        # cannot answer from a cache left behind by a previous run.
        from os import environ
        from tempfile import gettempdir

        cache_dir = environ.get("MS_CACHE_DIR")
        if cache_dir:
            self.cache_dir = cache_dir
        elif system() == r'Darwin':
            self.cache_dir = r"/users/gaeree/data/cache/phd/prompts.cache"
        elif system() == r'Linux':
            self.cache_dir = r"/tmp/cache"
        else:
            self.cache_dir = path.join(gettempdir(), "messy-streets-cache")""",
    ),

    Patch(
        module="phd/experiments/config.py",
        title="Import path used by the patch above",
        why="`path` is referenced by the cache-directory fallback.",
        old="from os import makedirs",
        new="from os import makedirs, path",
    ),
]
