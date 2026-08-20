"""
error_bars.py: Build error bars table, aggregated from N sub-tables

CREATED
edward | 2026-01-28

BACKLOG

USAGE
# paper 2 : geocorders
python3 error_bars.py address_wdc_1/paper2-address-wdc-geohash-geoparsers-p1to10-error-bars # --auto-run --overwrite --try-cache
python3 error_bars.py address_wdc_1/paper2-address-wdc-geohash1-openllm-error-bars
"""

from random import randint
from os import path, environ, makedirs
from sqlite3 import connect

from typing import Dict, Tuple, List, Optional


from numpy import nan, mean, std, sqrt
from pandas import DataFrame, read_json, concat, isna
from tabulate import tabulate

from serentec.utils.check_isinstance import check_isinstance
from serentec.utils.file.check_isfile import check_isfile
from serentec.utils.json.load_json import LoadJSON

from phd.tables.build_table import BuildTable

# logging
from serentec.utils.logger import logger_dl
module_logger = logger_dl.getChild("ErrorBars")

class ErrorBars:
    
    def __init__(self, table_name : str, batch_mode : bool = False, timeout_seconds : int = 60, debug : bool = False, debug2 : bool = False):

        """
        :param table_name: name of the table, e.g address_wdc_1/paper2-address-wdc-geohash-geoparsers-p1to10-error-bars

        :param batch_mode: run experiments in batch_mode; the model must the predict_batch method
            Results will be stored to /batch folder

        :param timeout_seconds: timeout for API calls, in seconds
        """

        self.debug = debug
        self.debug2 = debug2

        self.table_name = table_name
        
        self.run_number = None
        self.run_number_suffix = "" if self.run_number is None else f".{self.run_number}"
        module_logger.debug(f"run_number : {self.run_number}")


        self.timeout_seconds = timeout_seconds
        module_logger.debug(f"Using a timeout of {timeout_seconds} seconds")

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

        # BACKLOG: concatenate the sql tables


    async def run(self
                  , auto_run : bool = False
                  , re_run_all : bool = False
                  , try_cache : bool = False
                  , assert_cache : bool = False
                  , stop_on_error : bool = False
                  , skip_missing : bool = False
                  ) -> Tuple[List[DataFrame], List[Dict]]:
        """
        Build the table

        :param auto_run: if True, missing experiments are automatically run

        :param re_run_all: if True, all experiments are automatically run

        :paramn try_cache: try prompt cache if possible

        :param stop_on_error: stop on first error

        :param skip_missing: optional; if True, skip missing experiments, set value to nan

        :return: 2-tuple
            1. list of the underlying dataframes
            2. list of dicts with number of exceptions in cells that generated one or more exceptions
            
        """

        if skip_missing:
            if auto_run or re_run_all:
                raise ValueError(f"Cannot specify skip_missing and auto_run/re_run_all")

        dfs : List[DataFrame] = []

        exceptions = []

        # iterate over each row of the table
        table_names = self.config["tables"]
        module_logger.info(f"Building error bars from {len(table_names)} tables")

        for table_idx, table_name in enumerate(table_names):

            module_logger.info(f"Table {table_idx+1} of {len(table_names)} | {table_name}")

            do_run = False

            table_path = path.join(environ["PYTHONPATH"], "phd", "tables", "tables", table_name)
            if self.batch_mode:
                table_path = path.join(self.table_path, "batch")

            table_filename = path.join(table_path, f"rendered{self.run_number_suffix}.json")
            table_exists = path.isfile(table_filename)

            # force re-run this table?
            re_run_this_table = re_run_all is True

            if re_run_this_table or not table_exists:            
                if skip_missing:
                    # skip missing tables
                    do_run = False
                    
                    module_logger.debug(f"Table {table_name} is missing -> skipping | {table_filename}")
                
                elif auto_run:
                    # run experiment
                    do_run = True

                    module_logger.debug(f"Table {table_name} is missing -> running | {table_filename}")

                else:
                    # out of options -> fail
                    raise RuntimeError(f"Table {table_name} must be run neither skip nor auto-run options specified -> goodbye")
                
            # run experiment if necessary
            if do_run:
                if not table_exists:
                    module_logger.debug(f"Table {table_filename} not found -> running it now...")
                else:
                    module_logger.warning(f"Table {table_filename} exists but re_run_this_row is True -> running it now (this will overwrite existing results)...")
                
                build_table = BuildTable(table_name
                                 , timeout_seconds=self.timeout_seconds
                                 , run_number=self.run_number
                                 , batch_mode=self.batch_mode
                                 , debug=self.debug
                                 , debug2=self.debug2
                                 )
                
                _, _auto_run_df_table, _auto_run_exceptions = await build_table.run(auto_run=auto_run
                                               , re_run_all=re_run_all
                                               , try_cache=try_cache
                                               , assert_cache=assert_cache
                                               , stop_on_error=stop_on_error
                                               , skip_missing=skip_missing
                                               )
                
                exceptions.append(_auto_run_exceptions)
                
                _auto_run_df_table.to_json(table_filename)
                module_logger.debug(f"Table {table_name} rebuilt | saved rendered version to {table_filename}")

                # BACKLOG: save additonal formats like latex, data, etc

            module_logger.debug(f"Table {table_name} | Exists : {table_exists} | Run : {do_run}")

            # load dataframe
            df_table = read_json(table_filename)
            df_table.replace("N/A", float('nan'), inplace=True) # replace N/A values set in the build_table.py script
            dfs.append(df_table)

            if self.debug:
                print(tabulate(df_table, headers="keys", tablefmt="orgtbl"))
            
        module_logger.info(f"All tables read")

        return dfs, exceptions

    async def render(self, tables : List[DataFrame]) -> Tuple[DataFrame, str]:
        """
        Render final dataframe and camera-ready latex
        
        SOURCE
        https://claude.ai/chat/c3f2db1f-c800-48aa-8eb5-5ede3577084b

        :return: 2-tuple
            1. final dataframe with mean across tables
            2. latex string
        
        """
        
        # Stack all dataframes and compute statistics
        stacked = concat(tables, keys=range(len(tables)))
        means = stacked.groupby(level=1).mean() # dataframe with the means
        stds = stacked.groupby(level=1).std(ddof=1) # std deviation
        sems = stds / sqrt(len(tables)) # SEM = SD / √n

        # Find best value per row (excluding Mean column for comparison)
        # BACKLOG: need to account for other summary metrics like Min and Max that could have different names
        data_cols = [c for c in means.columns if c != 'Mean']
        best_per_col = means[data_cols].idxmax(axis=0)
        
        # Format as "mean ± se" strings
        default_num_decimals = self.config["format"]["decimals"]
        def format_cell(row_idx, col, m, s, decimals=default_num_decimals, highlight_best : bool = False):
            # METHODOLOGY: NeurIPS prefers 2 SDs
            # "The authors should preferably report a 2-sigma error bar than state that they have a 96\% CI, if the hypothesis of Normality of errors is not verified."
            #inner = f"{100*m:.{decimals}f}_{{{{\pm {100*2*s:.{decimals}f}}}}}"                
            inner = f"\\mathrm{{{100*m:.{decimals}f}}}_{{{{\\pm {100*2*s:.{decimals}f}}}}}"
            is_best = col in data_cols and best_per_col[col] == row_idx
            if highlight_best and is_best:
                return f"$\\mathbf{{{inner}}}$"
            return f"${inner}$"
        
        df_table = DataFrame(
            [[format_cell(idx, col, means.loc[idx, col], sems.loc[idx, col])
            for col in means.columns]
            for idx in means.index]
            , index=means.index
            , columns=means.columns
        )


        # sort
        if "sort" in self.config["table"] and self.config["table"]["sort"] is not None and "columns" in self.config["table"]["sort"]:
            try:
                sort_fields = self.config["table"]["sort"]["columns"]
                sort_ascending = self.config["table"]["sort"]["ascending"]

                # Sort by Mean column descending (before formatting)
                #sort_order = means[sort_fields].sort_values(ascending=sort_ascending).index
                means = means.sort_values(by=sort_fields, ascending=sort_ascending)
                stds = stds.loc[means.index]
                        
                #df_table = df_table.sort_values(sort_fields, ascending=sort_ascending)
                df_table = df_table.loc[means.index]

                module_logger.debug(f"Table sorted by column {sort_fields} with ascending = {sort_ascending}")
            except Exception as e:
                module_logger.warning(f"Failed to sort table by columns '{sort_fields}' | {e}")
        

        caption = self.config["format"].get("caption", None)
        label = self.config["format"].get("label", None)

        df_table = df_table.fillna(value="N/A")
        

        # Generate LaTeX
        def to_booktabs_latex(df, column_format=None):
            if column_format is None:
                column_format = 'l' + 'r' * len(df.columns)
            
            lines = [
                r'\begin{tabular}{' + column_format + '}'
                , r'\toprule'
                # escape underscores in column titles
                , ' & '.join([''] + [str(c).replace('_', r'\_') for c in df.columns]) + r' \\'
                , r'\midrule'
            ]
            for idx, row in df.iterrows():
                # escape underscores in row values
                #lines.append(str(idx) + ' & ' + ' & '.join(row.values) + r' \\')
                #lines.append(str(idx).replace('_', r'\_') + ' & ' + ' & '.join(v.replace('_', r'\_') for v in row.values) + r' \\')
                lines.append(str(idx).replace('_', r'\_') + ' & ' + ' & '.join(v for v in row.values) + r' \\')
            lines += [r'\bottomrule', r'\end{tabular}']
            
            return '\n'.join(lines)

        tabular_str = to_booktabs_latex(df_table)
        
        # fit table to page
        tabular_str = r"\resizebox{\textwidth}{!}{%" + "\n" + tabular_str + r"}"

        # create table with caption and label
        latex_table = f"""\\begin{{table}}[ht!]
            \\centering
            \\caption{{{caption}}}
            \\label{{{label}}}
            
            {tabular_str}
            
            \\end{{table}}"""


        return means, latex_table

if __name__ == '__main__':

    from argparse import ArgumentParser
    from asyncio import run
    from datetime import datetime
    from json import dumps
    from os import remove
    from socket import gethostname
    from time import perf_counter
    
    async def amain():
        parser = ArgumentParser(description='Build error bars table')
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
        parser.add_argument('--timeout', default=300, type=int, help='timeout for api calls, in seconds')

        parser.add_argument('--debug', default=False, dest='debug', action='store_true', help='debugging')
        parser.add_argument('--debug2', default=False, dest='debug2', action='store_true', help='debugging')
        parser.add_argument('--stop-on-error', default=False, dest='stop_on_error', action='store_true', help='stop on first error')
        parser.add_argument('--stop_on_error', default=False, dest='stop_on_error', action='store_true', help='stop on first error')
        
        args = parser.parse_args()

        if args.skip_missing:
            if args.auto_run or args.re_run_all:
                raise ValueError(f"Arguments skip and auto_run/re_run_all are exclusive")
        
        build_table = ErrorBars(args.table
                                 , timeout_seconds=args.timeout
                                 , batch_mode=args.batch
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

        # create table
        t0 = perf_counter()
        dfs, exceptions = await build_table.run(auto_run=args.auto_run
                                               , re_run_all=args.re_run_all
                                               , try_cache=args.try_cache
                                               , stop_on_error=args.stop_on_error
                                               , skip_missing=args.skip_missing
                                               )
        t1 = perf_counter()

        # render latex table
        output_df, output_latex = await build_table.render(dfs)
        print(tabulate(output_df, headers="keys", tablefmt="orgtbl"))

        if not save:
            module_logger.warning(f"Table already exists and no overwrite flag => goodbye")
            exit(1)

        # save rendered dataframe as displayed
        output_df.to_json(build_table.output_rendered_filename)
        module_logger.info(f"Saved rendered version to {build_table.output_rendered_filename}")

        # save latex
        with open(build_table.output_latex_filename, "w") as latex_file:
            latex_file.write(output_latex)

        module_logger.info(f"LaTex table rendered | {build_table.output_latex_filename}")

        # save raw data
        with open(build_table.output_data_filename, "w", encoding='utf8') as json_file:
            json_file.write(dumps([df.to_records() for df in dfs], default=str))
            module_logger.info(f"saved data to {build_table.output_data_filename}")
        
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



