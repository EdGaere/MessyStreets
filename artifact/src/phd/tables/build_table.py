"""
build_table.py: Build a table that collects data from 1 or more experiments

SETUP
# [credential removed when vendoring; supply your own via the environment — see README]

export OLLAMA_HOST=127.0.0.1:9302

START OLLAMA SERVER
export OLLAMA_HOST=127.0.0.1:11434

export OLLAMA_MAX_LOADED=1
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_NUM_THREADS=8
export CUDA_VISIBLE_DEVICES=0,1,2,3

ollama serve

NOTES
- batch status can be viewed here: 
    - https://platform.openai.com/batches
    - https://console.anthropic.com/workspaces/default/batches

CHANGE LOG
edward | 2024-08-17

BACKLOG
-- flag error_bars that computes variance about the base run using the different runs available

USAGE
# basic use
python3 build_table.py datetime_v2/computation_tasks_2 --auto-run --overwrite --try-cache

# batch experiments for APIs supporting batch processing
python3 build_table.py address_v2/address_country_1_istr_gemini --batch --auto-run --overwrite --try-cache

DANGER ZONE
# re-run using existing cache (if available) or existing results in all_results.json (if available)
python3 build_table.py datetime_v2/natural_context_tasks_1_anthropic_latest_1 --batch --auto-run --overwrite --try-cache --re-run-all --assert-cache
"""
from json import dumps
from random import randint
from os import path, environ, makedirs
from sqlite3 import connect

from typing import Dict, Tuple, List, Optional


from numpy import nan
from pandas import DataFrame
from tabulate import tabulate

from serentec.utils.check_isinstance import check_isinstance
from serentec.utils.file.check_isfile import check_isfile
from serentec.utils.json.load_json import LoadJSON
from serentec.utils.parse_function_args import parse_function_args

from phd.experiments.run_experiment import RunExperiment
from phd.experiments.run_experiment_batch import RunExperimentBatch

# logging
from serentec.utils.logger import logger_dl
module_logger = logger_dl.getChild("BuildTable")

class BuildTable:
    
    def __init__(self
                 , table_name : str
                 , run_number : int = None
                 , batch_mode : bool = False
                 , timeout_seconds : int = 60
                 , read_only : bool = False
                 , debug : bool = False
                 , debug2 : bool = False
                 ):

        """
        :param table_name: name of the table, e.g datetime/1

        :param run_number: number of the run; allows for versioning of runs and models
            - None: no run number, so data is stored to output.json, output.text and stats.hson
            - integer, e.g 1: create a new run, that can be stored alongside previous runs; can ultimately be used for error bars
                e.g if run_number is e.g 1 (integer), then output will be output.1.json, output.1.text and stats.1.hson

        :param batch_mode: run experiments in batch_mode; the model must the predict_batch method
            Results will be stored to /batch folder

        :param timeout_seconds: timeout for API calls, in seconds
        """

        self.debug = debug
        self.debug2 = debug2

        self.read_only = read_only

        self.table_name = table_name
        
        check_isinstance(run_number, int, none_ok=True)
        self.run_number = run_number
        self.run_number_suffix = "" if self.run_number is None else f".{self.run_number}"
        module_logger.debug(f"run_number : {self.run_number}")

        

        self.timeout_seconds = timeout_seconds
        module_logger.debug(f"Using a timeout of {timeout_seconds} seconds")

        self.experiments_path = path.join(environ["PYTHONPATH"], "phd", "experiments", "experiments")
        self.table_path = path.join(environ["PYTHONPATH"], "phd", "tables", "tables", table_name)

        # load table configuration
        config_filename = path.join(self.table_path, "table.hjson")
        module_logger.debug(f"table : {table_name} | config_filename : {config_filename}")
        self.config = LoadJSON().load(config_filename)
        module_logger.debug(f"table config : {dict(self.config)}")

        # batch processing
        self.batch_mode = batch_mode
        self.batch_suffix = ""
        if batch_mode:
            self.table_path = path.join(self.table_path, "batch")
            makedirs(self.table_path, exist_ok=True)
            self.batch_suffix = ".batch"

        # prepare output filenames
        self.output_rendered_filename = path.join(self.table_path, f"rendered{self.run_number_suffix}.json")
        self.output_data_filename = path.join(self.table_path, f"output{self.run_number_suffix}.json")
        self.output_latex_filename = path.join(self.table_path, f"output{self.run_number_suffix}.tex")
        self.output_stats_filename = path.join(self.table_path, f"stats{self.run_number_suffix}.json")
        self.output_sqlite_filename = path.join(self.table_path, f"results{self.run_number_suffix}.sqlite")
        module_logger.debug(f"outputs | data : {self.output_data_filename} | latex : {self.output_latex_filename} | stats : {self.output_stats_filename} | sqlite : {self.output_sqlite_filename}")

        # create sqlite database + tabke
        if not read_only:
            self.sqlite_db_connection = connect(self.output_sqlite_filename)
            assert self.sqlite_db_connection is not None
            module_logger.debug(f"Connected to sqlite | {self.output_sqlite_filename}")

            # save results to sqlite
            self.sqlite_cursor = self.sqlite_db_connection.cursor()

            # Create table
            # NOTE: keep track of names of columns for bulk insert; must be in the correct order
            # NOTE: run_id can be NULL if not specified (i.e. the main run)
            self.sqlite_columns = ["table_name", "run_id", "row_id", "column_id", "dt", "observation", "server", "input_payload", "input", "target", "prediction", "comparison", "correct", "probability", "cache", "cache_hash", "exception", "runtime_ms"]
            
            self.sqlite_cursor.execute("""CREATE TABLE IF NOT EXISTS results (
                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    table_name TEXT NOT NULL,
                                    run_id INT,
                                    row_id TEXT NOT NULL,
                                    column_id TEXT NOT NULL,
                                    dt DATETIME NOT NULL,
                                    observation INT NOT NULL,
                                    server TEXT NOT NULL,
                                    input_payload JSON,
                                    input TEXT NOT NULL,
                                    target TEXT NOT NULL,
                                    prediction TEXT,
                                    comparison JSON,
                                    correct BOOL NOT NULL,
                                    probability FLOAT,
                                    cache BOOL NOT NULL,
                                    cache_hash TEXT,
                                    exception TEXT,
                                    runtime_ms FLOAT)""")

        
            # clear table
            # NOTE: no TRUNCATE command in sqlite3
            self.sqlite_cursor.execute("DELETE FROM results")
            
            module_logger.debug(f"sqlite table created and truncated")




    async def run(self
                  , auto_run : bool = False
                  , re_run_all : bool = False
                  , try_cache : bool = False
                  , assert_cache : bool = False
                  , stop_on_error : bool = False
                  , re_run_rows : Optional[List[str]] = None
                  , skip_missing : bool = False
                  ) -> Tuple[Dict, DataFrame, Dict]:
        """
        Build the table.

        :param auto_run: if True, missing experiments are automatically run

        :param re_run_all: if True, all experiments are automatically run

        :paramn try_cache: try prompt cache if possible

        :param assert_cache: only use cache; try_cache must be True
            an exception is thrown if value cannot be retrieved from cache

        :param stop_on_error: stop on first error

        :param re_run_rows: optional; force re-runing specific rows only
            can be None

        :param skip_missing: optional; if True, skip missing experiments, set value to nan

        :return: 3-tuple
            1. data as a dict
            2. Pandas DataFrame
            3. dict with number of exceptions in cells that generated one or more exceptions
            
        """

        if skip_missing:
            if auto_run or re_run_all:
                raise ValueError(f"Cannot specify skip_missing and auto_run/re_run_all")

        row_ids : List[str] = []
        index : List[str] = []
        data : List[Dict] = [] # Pandas compatible
        rows : Dict[Dict] = {} # rows["row.id"] = {}

        # metric to be collected
        # NOTE: must be within section "stats" of the results.json of each experiment
        metric_name = self.config["table"]["metric"]

        exceptions = {}

        
        # iterate over each row of the table
        for row in self.config["rows"]:

            row_id = row["id"]

            # Force re-run this row?
            re_run_this_row = re_run_all is True or (re_run_rows is not None and row_id in re_run_rows)
            if re_run_this_row:
                module_logger.warning(f"Row '{row_id}' is flagged to be re-run")

            # NOTE: ignore row columns
            row_is_hidden = row.get("hidden", False)

            if row_is_hidden:
                module_logger.warning(f"Hiding row {row_id}")
                continue

            row_ids.append(row_id)

            row_label = row.get("label", row_id) # if no label, simply use column_id

            if row_label in index:
                raise ValueError(f"Duplicate row label '{row_label}' for row id '{row_id}'")


            # add to rows dict
            if row_id in rows:
                raise ValueError(f"Duplicate row id '{row_id}'")
            check_isinstance(row, dict)
            rows[row_id] = row
            

            # iterate over each column of the table
            """
            id : a.2
            label : ISO-8601
            data : datetime/{column}{row}
            """
            row_data = {}
            constant_columns = set()
            for column in self.config["columns"]:

                # NOTE: ignore hidden columns
                column_is_hidden = column.get("hidden", False)
                column_is_constant = column.get("constant", False)

                column_id = column["id"]
                column_label = column.get("label", column_id) # if no label, simply use column_id

                if not column_is_hidden:

                    if column_is_constant:
                        if column_label in constant_columns:
                            raise ValueError(f"Constant column '{column_id}' ({column_label}) specified more than once")
                        
                        # extract the constant value
                        if "key" not in column or column["key"] not in row:
                            raise ValueError(f"Could not resolve the constant key for row {row_id}")
                        _constant_value = str(row[column["key"]])
                        row_data[column_label] = float(_constant_value) if column.get("type") == "float" else _constant_value
                        constant_columns.add(column_label)

                    else:
                        # points to an experiment
                        data_template = column["data"] if "data" in column else column["experiment"] # better name
                        experiment_name = data_template.replace(r"{column}", str(column_id)).replace(r"{row}", str(row_id))

                        # NOTE: results filename is conditional on:
                        # 1. the current run number; which could be None => no suffix
                        # 2. if the model is run in batch mode; which could be None => no suffix
                        experiment_results_filename = path.join(self.experiments_path, experiment_name, f"results{self.run_number_suffix}{self.batch_suffix}.json")
                        experiment_all_results_filename = path.join(self.experiments_path, experiment_name, f"all_results{self.run_number_suffix}{self.batch_suffix}.json")

                        if self.debug:
                            module_logger.debug(f"experiment_results_filename : {experiment_results_filename}")
                            module_logger.debug(f"experiment_all_results_filename : {experiment_all_results_filename}")

                        experiment_exists = path.isfile(experiment_results_filename)

                        if self.debug:
                            module_logger.debug(f"experiment_exists : {experiment_exists} | re_run_this_row : {re_run_this_row} | skip_missing : {skip_missing}")

                        
                        do_run = False
                        results = None
                        all_results = None
                        
                        if re_run_this_row or not experiment_exists:
                            # experiment does not exist -> two options:
                            # 1. skip
                            # 2. auto-run
                            
                            if skip_missing:
                                # skip missing experiments => set to nan to allow calculations and sorting, then will be replaced with "N/A" at the end
                                do_run = False
                                row_data[column_label] = float('nan')                                
                                module_logger.debug(f"Experiment {experiment_name} is missing -> skipping | {experiment_results_filename}")
                            
                            elif auto_run:
                                # run experiment
                                do_run = True

                                module_logger.debug(f"Experiment {experiment_name} is missing -> running | {experiment_results_filename}")

                            elif self.batch_mode:
                                # try non-batch mode
                                experiment_results_filename = path.join(self.experiments_path, experiment_name, f"results{self.run_number_suffix}.json")
                                experiment_exists = path.isfile(experiment_results_filename)
                                if experiment_exists:
                                    module_logger.warning(f"Experiment {{experiment_name}} not found in batch mode, but non-batch version found => using non-batch version")

                            # BACKLOG: if not self.batch_mode => try batch mode

                            else:
                                # out of options -> fail
                                raise RuntimeError(f"Experiment {experiment_name} must be run neither skip nor auto-run options specified -> goodbye")
                            
                        # run experiment if necessary
                        if do_run:
                            if not experiment_exists:
                                module_logger.debug(f"Experiment {experiment_name} not found -> running it now...")
                            else:
                                module_logger.warning(f"Experiment {experiment_name} exists but re_run_this_row is True -> running it now (this will overwrite existing results)...")
                            
                            if not self.batch_mode:
                                run_experiment = RunExperiment(experiment_name
                                                            , run_number=self.run_number
                                                            , timeout_seconds=self.timeout_seconds
                                                            # do not load the model if we are using cache only; this also allows running GPU-bound models on the local dev
                                                            , load_model=not assert_cache
                                                            , debug=self.debug2
                                                            )
                            else:
                                run_experiment = RunExperimentBatch(experiment_name
                                                            , run_number=self.run_number
                                                            , timeout_seconds=self.timeout_seconds
                                                            , debug=self.debug2
                                                            )

                            
                            await run_experiment.run(try_cache=try_cache
                                                     , assert_cache=assert_cache
                                                     , stop_on_error=stop_on_error
                                                     )

                            # release memory, close connections, ...
                            if run_experiment.model is not None:
                                await run_experiment.model.close()

                                # NOTE: critical to delete the model after use, so that any globals such as DiskCache related to the model are released
                                del run_experiment.model

                            del run_experiment
                            module_logger.debug(f"Experiment deleted")
                
                        # load new or existing results file, or simply don't load
                        if path.isfile(experiment_results_filename):
                            results = LoadJSON().load(experiment_results_filename)

                        # load all results and append to sqlite table, or simply don't load
                        if path.isfile(experiment_all_results_filename):
                            all_results = LoadJSON().load(experiment_all_results_filename)

                        # create list of tuples for bulk insertion into sqlite
                        if not self.read_only:
                            all_results_tuples = []

                            if all_results is not None:
                                for observation_dict in all_results:
                                    # add constants
                                    observation_dict.update({
                                        "table_name" : self.table_name
                                            , "run_id" : self.run_number
                                            , "row_id" : row_id
                                            , "column_id" : column_id
                                    })

                                    # create iterable for each row for bulk insert
                                    column_values = []
                                    
                                    
                                    for sqlite_column in self.sqlite_columns:
                                        if sqlite_column not in observation_dict:
                                            # value missing
                                            column_values.append(None)
                                        else:
                                            # NOTE: sqlite3 requires JSON fields to be serialised
                                            if isinstance(observation_dict[sqlite_column], dict):
                                                column_values.append(dumps(observation_dict[sqlite_column]))
                                            else:
                                                column_values.append(observation_dict[sqlite_column])

                                    all_results_tuples.append(column_values)


                            # add table name, experiment name, row, col
                            sqlite_columns_str = ",".join(self.sqlite_columns)
                            sqlite_columns_placehoder_str = ",".join(["?" for _ in self.sqlite_columns])
                            self.sqlite_cursor.executemany(f"INSERT INTO results ({sqlite_columns_str}) VALUES ({sqlite_columns_placehoder_str})", all_results_tuples)
                            self.sqlite_db_connection.commit()
                            #module_logger.debug(f"Inserted {len(all_results_tuples)} rows to database")

                        # extract metric
                        if results is not None:
                            if "stats" not in results:
                                raise ValueError(f"experiment results does not contain a section 'stats' | {experiment_results_filename}")
                            
                            if metric_name in results["stats"]:
                                metric = results["stats"][metric_name]
                            
                            # HACK: compute average runtime if not available in legacy experiments
                            elif metric_name == 'avg_runtime_ms':
                                total_runtime_ms = results["runtime(ms)"]
                                num_observations = results["stats"]["num_observations"]
                                metric = total_runtime_ms / num_observations

                            else:
                                raise ValueError(f"metric '{metric_name}' not found in section 'stats'. Available metrics : {results['stats'].keys()}")

                            if self.debug:
                                module_logger.debug(f"metric : {metric}")

                            # keep track of exceptions
                            num_exceptions = results["stats"].get("num_exceptions", 0)
                            if num_exceptions > 0:
                                if row_label not in exceptions:
                                    exceptions[row_label] = {}

                                exceptions[row_label][column_label] = num_exceptions



                            row_data[column_label] = metric

                # end of column
                
            # skip empty rows with no experiment data
            if len(row_data) > 0:
                data.append(row_data)
                index.append(row_label)
   
        print(data)
        # close db connection
        if not self.read_only:
            self.sqlite_cursor.close()
            module_logger.debug(f"sqlite connection closed")
        
        # create DataFrame
        df_table = DataFrame(data, index=index)
        df_table.index.name = self.config["table"]["row_name"]

        # caculated fields
        if "calculated" in self.config["table"]:
            # NOTE: here we need to be careful and keep the table intact whilst adding calculated fields; else new calculated fields
            # will become part of the calculations as the calculations are added => only add them to the table once all are computed
            metric_columns = [c for c in df_table.columns if c not in constant_columns]

            new_metrics = {}
            for metric_name, metric_label in self.config["table"]["calculated"].items():
                try:
                    if metric_name == "mean":
                        new_metrics[metric_label] = df_table[metric_columns].mean(axis=1)
                    elif metric_name == "max":
                        new_metrics[metric_label] = df_table[metric_columns].max(axis=1)
                    elif metric_name == "min":
                        new_metrics[metric_label] = df_table[metric_columns].min(axis=1)
                    elif metric_name == "range":
                        new_metrics[metric_label] = df_table[metric_columns].max(axis=1) - df_table[metric_columns].min(axis=1)

                    elif metric_name == "sd":
                        new_metrics[metric_label] = df_table[metric_columns].std(axis=1, ddof=1).round(3)

                    elif metric_name == "sem":
                        new_metrics[metric_label] = df_table[metric_columns].sem(axis=1, ddof=1).round(3)
                    else:
                        raise NotImplementedError(f"Don't know how to handle the metric of type '{metric_name}'")
                except Exception as e:
                    module_logger.warning(f"failed to add calculated field '{metric_name}' | {e}")

            # add metrics
            for metric_name, metric_values in new_metrics.items():
                df_table[metric_name] = metric_values




        # static fields
        # BACKLOG: place static fields first
        if "static" in self.config["table"]:
            static_fields = self.config["table"]["static"]
            for static_field in static_fields:
                # collect values
                static_field_values = []
                for row_id in row_ids:
                    static_field_values.append(rows[row_id].get(static_field, None))

                df_table[static_field] = static_field_values


        # sort
        # { column : ISO-8601, ascending : False }
        if "sort" in self.config["table"] and self.config["table"]["sort"] is not None and "columns" in self.config["table"]["sort"]:
            try:
                sort_fields = self.config["table"]["sort"]["columns"]
                sort_ascending = self.config["table"]["sort"]["ascending"]
                
                df_table = df_table.sort_values(sort_fields, ascending=sort_ascending)
                module_logger.debug(f"Table sorted by column {sort_fields} with ascending = {sort_ascending}")
            except Exception as e:
                module_logger.warning(f"failed to sort table by columns '{sort_fields}' | {e}")
            


        # cleanup; render the missed values with N/A
        df_table = df_table.fillna(value="N/A")

        return data, df_table, exceptions



if __name__ == '__main__':

    from argparse import ArgumentParser
    from asyncio import run
    from datetime import datetime
    from json import dumps
    from os import remove
    from socket import gethostname
    from time import perf_counter
    
    async def amain():
        parser = ArgumentParser(description='Build a table')
        parser.add_argument('table', type=str, help='name of the table, e.g datetime/test.1')

        # building new versions of the table with different hyper-parameters        
        parser.add_argument('--run', default=None, type=int, help='create a new run, that can be stored alongside previous runs; can ultimately be used for error bars')
        parser.add_argument('--batch', default=False, dest='batch', action='store_true', help="run experiments in batch_mode; the model must the predict_batch method")

                
        parser.add_argument('--skip', default=False, dest='skip_missing', action='store_true', help='if True, missing experiments are skipped')
        parser.add_argument('--auto-run', default=False, dest='auto_run', action='store_true', help='if True, missing experiments are automatically run')
        parser.add_argument('--auto_run', default=False, dest='auto_run', action='store_true', help='if True, missing experiments are automatically run')
        parser.add_argument('--re-run-all', default=False, dest='re_run_all', action='store_true', help='if True, all experiments are automatically run, even if they exist. Cache will be used if try-cache is specified')
        parser.add_argument('--re_run_all', default=False, dest='re_run_all', action='store_true', help='if True, all experiments are automatically run, even if they exist. Cache will be used if try-cache is specified')
        parser.add_argument('--overwrite', default=False, dest='overwrite', action='store_true', help='Overwrite existing table if already exists, but leave experiments unchanged')
        parser.add_argument('--try-cache', default=False, dest='try_cache', action='store_true', help='try using prompt cache')
        parser.add_argument('--try_cache', default=False, dest='try_cache', action='store_true', help='try using prompt cache')
        parser.add_argument('--assert-cache', default=False, dest='assert_cache', action='store_true', help='ensures only cache values are used')
        parser.add_argument('--timeout', default=300, type=int, help='timeout for api calls, in seconds')
        parser.add_argument('--re-run', default=None, type=str, dest='re_run_rows', nargs="*", help='(re-)run specific rows only; provide a space separated list of rows, e.g qwen2.5-coder-32b  codellama-7b-python')

        parser.add_argument('--debug', default=False, dest='debug', action='store_true', help='debugging')
        parser.add_argument('--debug2', default=False, dest='debug2', action='store_true', help='debugging')
        parser.add_argument('--stop-on-error', default=False, dest='stop_on_error', action='store_true', help='stop on first error')
        parser.add_argument('--stop_on_error', default=False, dest='stop_on_error', action='store_true', help='stop on first error')
        
        args = parser.parse_args()

        if args.skip_missing:
            if args.auto_run or args.re_run_all:
                raise ValueError(f"Arguments skip and auto_run/re_run_all are exclusive")
        
        build_table = BuildTable(args.table
                                 , timeout_seconds=args.timeout
                                 , run_number=args.run
                                 , batch_mode=args.batch
                                 , read_only=args.skip_missing      
                                 , debug=args.debug
                                 , debug2=args.debug2
                                 )

        # check not already run
        save = True
        if path.isfile(build_table.output_data_filename):
            if args.overwrite:
                module_logger.warning(f"Table already built... re-running")

            else:
                module_logger.warning(f"Table at {build_table.output_data_filename} already exists. Either delete it or specify overwrite flag. Table will be run but not saved")
                save = False

        if args.re_run_rows is not None:
            module_logger.debug(f"Force re-running {len(args.re_run_rows)} rows : {args.re_run_rows}")

        # BACKLOG: handle existing sqlite table
        """
        if path.isfile(build_table.output_sqlite_filename):
            if args.overwrite:
                remove(build_table.output_sqlite_filename)
                module_logger.debug(f"existing sqlite database deleted | {build_table.output_data_filename}")
            else:
                module_logger.warning(f"sqlite database already exists. Either delete it or specify overwrite flag. new table will be run but not saved")
                save = False
        """

        # create table
        t0 = perf_counter()
        data, df_table, exceptions = await build_table.run(auto_run=args.auto_run
                                               , re_run_all=args.re_run_all
                                               , try_cache=args.try_cache
                                               , assert_cache=args.assert_cache
                                               , stop_on_error=args.stop_on_error
                                               , re_run_rows=args.re_run_rows
                                               , skip_missing=args.skip_missing
                                               )
        t1 = perf_counter()

        # show table
        print(tabulate(df_table, headers="keys", tablefmt="orgtbl"))

        if not save:
            module_logger.warning(f"Table already exists and no overwrite flag => goodbye")
            exit(1)

        # save raw data
        with open(build_table.output_data_filename, "w", encoding='utf8') as json_file:
            json_file.write(dumps(data))
            module_logger.info(f"saved data to {build_table.output_data_filename}")

        # save rendered dataframe as displayed
        df_table.to_json(build_table.output_rendered_filename)
        module_logger.info(f"saved rendered version to {build_table.output_rendered_filename}")

        # write to latex
        # special formats: 
        # t1 : thousand separator with 1 decimal
        # t2 : thousand separator with 2 decimals
        # p0 : percentage with no decimals
        # p1 : percentage with 1 decimal
        # mathrm : percentage with 1 decimal in math font
        float_format = build_table.config["format"]["float"]
        
        if float_format == r"t1":
            float_format = lambda x: f"{x:,.1f}"
        elif float_format == r"t2":
            float_format = lambda x: f"{x:,.2f}"
        elif float_format == "p0":
            float_format = lambda x: f"{x * 100:.0f}"
        elif float_format == "p1":
            float_format = lambda x: f"{x * 100:.1f}"
        elif float_format == "mathrm":
            float_format = lambda x: f"$\\mathrm{{{x * 100:.1f}}}$"
        
        elif float_format.startswith("red"):
            # conditional rendering in red of values below a threshold
            # example red(x) : conditional rendering in red of values below a threshold; threshold in decimals [0;1]
            float_format_args = parse_function_args(float_format)
            color_threshold = float_format_args[0]
            assert color_threshold >= 0.0 and color_threshold <= 1.0
            module_logger.debug(f"color_threshold : {color_threshold}")
            

            def format_cell(x):
                s = f"$\\mathrm{{{x * 100:.1f}}}$"
                if x < color_threshold:
                    s = f"\\cellcolor{{red!15}}{s}"
                return s
            
            float_format = format_cell

        elif float_format.startswith("heatmap"):
            # e.g. heatmap(red, green)
            float_format_args = parse_function_args(float_format)
            color_from = float_format_args[0]
            color_to = float_format_args[1]

            def format_cell(x):
                val = x * 100
                s = f"$\\mathrm{{{val:.1f}}}$"
                # Interpolate from start color (0%) to end color (100%)
                color_from_pct = int((1 - x) * 30)   # 30 = max intensity
                color_to_pct = int(x * 30)
                s = f"\\cellcolor{{{color_from}!{color_from_pct}!{color_to}!{color_to_pct}}}{s}"
                return s
            
            float_format = format_cell



        
        module_logger.debug(f"Number format examples | 0.99 => {float_format(0.99)} | 99.0 => {float_format(99.0)}" )

        # format options
        format_options = {
            "float_format" : float_format
            , "bold_rows" : build_table.config["format"].get("bold_rows", False)
            , "caption" : build_table.config["format"].get("caption", None)
            , "label" : build_table.config["format"].get("label", None)
        }

        module_logger.debug(f"format_options : {format_options}")
        # add \tiny command to start of the table
        #df_table.to_latex(build_table.output_latex_filename, **format_options)
        table_tex_str = df_table.to_latex(**format_options)
        table_tex_str = table_tex_str.replace(r'\begin{table}', r'\begin{table}[ht!]' + '\n\\tiny')
        
        with open(build_table.output_latex_filename, "w") as latex_file:
            latex_file.write(table_tex_str)

        module_logger.info(f"latex table rendered | {build_table.output_latex_filename}")

        # save stats
        elapsed_milliseconds = 1000.0 * (t1 - t0)

        stats = {
            "dt" : datetime.now().isoformat()
            , "server" : gethostname()
            , "runtime(ms)" : elapsed_milliseconds
            , "script" : __file__

            # parameters
            , "arguments" : vars(args)

            # exceptions
            , "exceptions" : exceptions

        }

        with open(build_table.output_stats_filename, "w", encoding='utf8') as json_file:
            json_file.write(dumps(stats))
            module_logger.info(f"saved summary to {build_table.output_stats_filename}")
            
        if len(exceptions) > 0:
            module_logger.warning(f"{len(exceptions)} rows generated exceptions")

    run(amain())



