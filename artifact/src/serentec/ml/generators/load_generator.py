# -*- coding: utf-8 -*-

"""
load_generator.py: load a data generator module from file and expose functions of the generators

base: train.py

CHANGE LOG
edward | 2021-06-04 | init

edward | 2023-03-07 | evaluate the signature of the generator function so that we can skip optional arguments not supported
this avoids the exception "got an unexpected keyword argument"
example: argument 'remove_random_component_probability' is only supported by 3 generators at the moment

BACKLOG

USAGE
python3 load_generator.py dates/datetime/generate16.20.py iso8601 10
python3 load_generator.py numbers/float/generate3.py standard_number 10

"""

# system
from datetime import date, datetime, time, timedelta
import importlib 
from inspect import signature
from os import path, environ
from typing import Any, List, Set, Dict, Tuple, Optional, Union, Iterable, Iterator

# serentec
from serentec.exceptions import Error, FileNotFound

# serentec machine learning
from serentec.ml.config import Config as MLConfig
from serentec.ml.training_pair import TrainingPair

class LoadGenerator:

    # training configuration
    def __init__(self, generator_name : str, base_path : str = None, debug : bool = False, debug2 : bool = False, **kwargs):

        """
        :param generator_name: name of the model to be loaded, e.g datetime/generate4.py

            generator_path in MLConfig() will be automatically pre-pended;
            currently generator_path is serentec/ml/generators 
            so you only need to specifcy the path within generator_path

        :param base_path: default path for generators is serentec/ml/generators (self.config.generator_path) but can be overriden

        :param debug: set debug flag of the loaded class

        :param kwargs: optional arguments for the generstor's constructor
        """
        self.debug = debug
        self.config = MLConfig()

        self.base_path = self.config.generator_path if base_path is None else base_path

        # resolve special tokens in base path
        if r"{PYTHONPATH}" in self.base_path:
            pythonpath = environ["PYTHONPATH"]
            self.base_path = self.base_path.replace(r"{PYTHONPATH}", pythonpath)

        model_filename = path.join(self.base_path, generator_name)

        
        if not path.isfile(model_filename):
            raise FileNotFound(f"model '{model_filename}' not found")

        self.model_filename = model_filename

        module_spec = importlib.util.spec_from_file_location('generator', model_filename)
        assert module_spec is not None
        generator_module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(generator_module)

        # create instance of the class
        self.generator = generator_module.Generate(**kwargs)
        self.generator_name = generator_name
        self.generator.debug = debug
        self.generator.debug2 = debug2

        # add edward | 2023-03-07 | evaluate the signature of the generator function so that we can skip optional arguments not supported
        # this avoids the exception "got an unexpected keyword argument"
        # example: argument 'remove_random_component_probability' is only supported by 3 generators at the moment
        self.generator_signature = signature(self.generator.generate)
        self.generator_filter_keys = [param.name for param in self.generator_signature.parameters.values() if param.kind == param.POSITIONAL_OR_KEYWORD]

        if self.debug:
            print(f"generator {generator_name} supports the following arguments : {self.generator_filter_keys}")

        # expose properties
        self.model_name = self.generator.model_name

   
    # BACKLOG: we need **kwargs here
    def generate(self
                , output : str
                , num_observations : int
                , locale_schema : str = None
                , store_visible_components : bool = False
                , filters : List = None # e.g. ["jaccard_1 < 0.43"]
                
                # datetimes
                , start_date : Any = None 
                , end_date : Any = None 
                , schemas : List[str] = None
                , date_schemas : List[str] = None
                , time_schemas : List[str] = None
                , month_schema : str = None
                , remove_random_component_probability : float = None # NOTE: was .05 default but this is unsafe, ablation should be explicitly set
                , incremental : bool = False
                , same_month : int = 0
                , microseconds : bool = False
                , add_timezone : bool = False
                , year_tokens : List[str] = None
                , weekday_tokens : List[str] = None

                # file ingestion
                , input_file : str = None # pre-generated dump file or PhD benchmark
                , first_n_bytes : int = None
                , peek : int = None
                , window_start : str = None
                , byte_encoding : str = None
                , text_encoding : str = None
                , filetype : str = None
                , compression : str = None
                , line_terminator : str = None
                , sep : str = None
                , stop_on_error : bool = False
                , round_trip : bool = False
                , max_rows : int = None
                , generator_name : str = None # sub-generator to load, e.g for compression generator that uses a sub-generator such as csv
                , num_files_per_archive : int = None

                # NER arguments
                , balanced : bool = False
                , batch_size : int = None
                , batch_delimiter : str = None

                # INT/FLOAT arguments
                , lower_bound : int = None
                , upper_bound : int = None
                , custom_decimal_character : str = None

                # PhD Tasks
                , input_length : int = None

                # addresses
                , databases : List = None
                , seed : int = None
                , require_minimum_fields : bool = True
                , toggle_source : bool = False
                , add_source : bool = False
                , use_cache : bool = True

                # units
                , unit_schema : str = None

                ) -> Iterator[ Tuple[ TrainingPair, Any] ]:

        """ pass through to the date generators generate() method

        :param locale_schema: optional; schema to be used for locales
            - "all" : (default); all loacles
            - "mini.1" : mini subset in Serentec Config (["en_US", "en_GB", "de_DE", "fr_CH", "sv_SE", "es_ES", "no_NO", "it_IT", "nl_NL", "pt_PT"])

         :return: function is a generator -> an iterator of 2-tuples
            1. TrainingPairs (namedtuple)
            2. the input data (any Python object)

        """

        # some checks and type fixing
        if seed is not None and isinstance(seed, str):
            assert seed.isdigit()
            seed = int(seed)

        
        # put all the optional arguments into a dict
        # BACKLOG: we need **kwargs here
        kwargs = { "start_date" : start_date
                  , "end_date" : end_date
                  , "schemas" : schemas
                  , "date_schemas" : date_schemas
                  , "time_schemas" : time_schemas
                  , "month_schema" : month_schema
                  , "locale_schema" : locale_schema
                  , "store_visible_components" : store_visible_components
                  , "filters" : filters
                  , "remove_random_component_probability" : remove_random_component_probability
                  , "first_n_bytes" : first_n_bytes
                  , "peek" : peek
                  , "window_start" : window_start
                  , "byte_encoding" : byte_encoding
                  , "text_encoding" : text_encoding
                  , "filetype" : filetype
                  , "compression" : compression
                  , "line_terminator" : line_terminator
                  , "sep" : sep
                  , "stop_on_error" : stop_on_error
                  , "round_trip" : round_trip
                  , "max_rows" : max_rows
                  , "generator_name" : generator_name
                  , "num_files_per_archive" : num_files_per_archive
                  , "incremental" : incremental
                  , "same_month" : same_month
                  , "microseconds" : microseconds
                  , "add_timezone" : add_timezone
                  , "year_tokens" : year_tokens
                  , "weekday_tokens" : weekday_tokens
                  , "balanced" : balanced
                  , "batch_size" : batch_size
                  , "batch_delimiter" : batch_delimiter
                  , "lower_bound" : lower_bound
                  , "upper_bound" : upper_bound
                  , "custom_decimal_character" : custom_decimal_character
                  , "input_length" : input_length
                  , "input_file" : input_file
                  , "databases" : databases
                  , "seed" : seed
                  , "require_minimum_fields" : require_minimum_fields
                  , "toggle_source" : toggle_source
                  , "add_source" : add_source
                  , "use_cache" : use_cache
                  , "unit_schema" : unit_schema
                  }
        
        #print(f"kwargs : {kwargs}")
        #print(f"debug exit")
        #exit(1)


        # filter out the arguments not supported by this generator
        filtered_kwargs = {filter_key:kwargs[filter_key] for filter_key in kwargs if filter_key in self.generator_filter_keys}

        if self.debug:
            print(f"kwargs : {kwargs}")
            print(f"filtered_kwargs : {filtered_kwargs}")
        
        # start_date=start_date
        # schemas=schemas
        # locale_schema=locale_schema
        # remove_random_component_probability=remove_random_component_probability
        return self.generator.generate(output=output
                                        , num_observations=num_observations
                                        , **filtered_kwargs
                                        )

    
    def get_custom_formatter(self):
        return self.generator.custom_formatter


if __name__ == '__main__':

    from argparse import ArgumentParser
    from bz2 import BZ2File
    from pickle import load 
    from tabulate import tabulate

    from pandas import DataFrame


    def main():

        # init command line arguments
        cmd_line_parser = ArgumentParser(description='LoadGenerator')
        cmd_line_parser.add_argument('generator_name', type=str, default=None, help="name of the generator, e.g dates/datetime/generate16.20.py")
        cmd_line_parser.add_argument('output', type=str, default=None, help="output name, e.g iso8601")
        cmd_line_parser.add_argument('num_observations', type=int, default=10, help="number of observations to generate, e.g 10")

        # benchmark run

        # arguments for the generator
        cmd_line_parser.add_argument('-S', '--schemas', type=str, help="comma separated list of schemas to use; e.g 'day-month-plain'", default=None)
        cmd_line_parser.add_argument('-s', '--start_date', type=str, help='start datetime in ISO format, e.g 2022-02-02T06:19:37', default=None)
        cmd_line_parser.add_argument('-l', '--locale_schema', type=str, help='locale schema; e.g en_US, mini.10, ...', default='en_US')
        cmd_line_parser.add_argument('-r', '--remove_random_component_probability', type=float, help='probability for removing a component at random', default=0.05)
            
        # flags
        cmd_line_parser.add_argument('--debug', default=False, dest='debug', action='store_true', help='debugging')
        
        args = cmd_line_parser.parse_args()


        # create instance of the class
        generator = LoadGenerator(generator_name=args.generator_name, debug=args.debug)

        for x in generator.generate(   output=args.output
                                , num_observations=args.num_observations
                                , start_date=args.start_date
                                , schemas=args.schemas
                                , locale_schema=args.locale_schema
                                , remove_random_component_probability=args.remove_random_component_probability
                    ):
            print(x)

        
       
    main()

   