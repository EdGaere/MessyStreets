"""
run_experiment.py: Run an experiment

NOTES

CHANGE LOG
edward | 2024-08-17

BACKLOG

SETUP
# multiple ollama instances
export OLLAMA_HOST=82.130.119.17:9301,82.130.119.34:9301

USAGE

# paper 2: libposta based parsers
# NOTE: you need to override the models manually to switch between libpostal and senzing (see notes in /Users/gaeree/data/libpostal/libpostal/address_parser)
python3 run_experiment.py address/paper2-address-country-v1-libpostal/istr
python3 run_experiment.py address/paper2-address-country-v1-libpostal-senzing-1.0/istr
python3 run_experiment.py address/paper2-address-country-v1-libpostal-senzing-1.1/istr

# paper 2 specialised address parsers
python3 run_experiment.py address/paper2-address-country-v1-lstm/istr
python3 run_experiment.py address/paper2-address-country-v1-nominatim-istr
python3 run_experiment.py address/paper2-address-country-v1-google-geocoding-istr
python3 run_experiment.py address/paper2-address-country-v1-photon-istr
python3 run_experiment.py address/paper2-address-country-v3-google-geocoding/istr

# paper 2: geohash
python3 run_experiment.py address/paper2-address-wdc-geohash7-geoparsers-test/Nominatim-geohash7

# paper 2 deepparse: only runs on GPU => mtec-mis-gpu01
python3 run_experiment.py address/paper2-address-country-v1-deepparse/bpemb-attention/istr
python3 run_experiment.py address/paper2-address-country-v1-deepparse/bpemb/istr
python3 run_experiment.py address/paper2-address-country-v1-deepparse/fasttext-attention/istr
python3 run_experiment.py address/paper2-address-country-v1-deepparse/fasttext-light/istr

python3 run_experiment.py address/paper2-address-wdc-ft-tpu-train-A-qwen2.5_7b_it-N=10000-geohash1-run1


# fine-tuned models
python3 run_experiment.py address/paper2-address-country-v1-unsloth/paper2-address-country-1-unsloth-ft-1-qwen2.5-0.5b-fp-ft-13.S=100 --max-obs 1 --debug
python3 run_experiment.py datetime/reasoning_conversation_1.t+c/add.day.50/qwen2.5-3b --max-obs 1 --debug

python3 run_experiment.py datetime/a.3/qwen2.5-7b-ft-1.N=1M --max-obs 1 --stop-on-error --no-save
python3 run_experiment.py datetime/a.3/qwen2.5-7b-ft-1.N=0 --max-obs 1 --stop-on-error --no-save

# prompt chains
python3 run_experiment.py datetime/a.3.pc_1/gemma2-27b --max-obs 1 --stop-on-error --no-save
python3 run_experiment.py datetime/a.3.pc_1/deepseek-r1-1.5b --max-obs 1 --stop-on-error

# Qwen
python3 run_experiment.py datetime/a.2/qwen2.5-32b --overwrite --stop-on-error
python3 run_experiment.py datetime/a.3/qwen2-math-1.5b --overwrite

# NLEP
python3 run_experiment.py datetime/add.days.x/add.day.250.x.t+c/claude-3-5-sonnet --overwrite
python3 run_experiment.py datetime/add.days.x/add.day.100.x.nlep_1/mistral-codestral  --debug --debug2 --overwrite
python3 run_experiment.py datetime/iso8601/a.2.nlep_1/gpt-4.0 --debug --debug2

python3 run_experiment.py datetime/day.2/serentec/p1-AMD-Ryzen-5-3600-6-Core --overwrite
python3 run_experiment.py datetime/year.2/serentec/macbook-pro-intel-Core-i7 --overwrite
python3 run_experiment.py datetime/a.2/meta-llama-3.2-1b --overwrite
python3 run_experiment.py datetime/add.days.x.contains/add.day.1.x/gemini-1.5-flash-ft.1-1K --overwrite

# openAI
python3 run_experiment.py datetime/tests/test.1
python3 run_experiment.py clean_number/noise.1/gemma-7b-it
python3 run_experiment.py clean_number/noise.1/claude-3-5-sonnet

# tests
python3 run_experiment.py datetime/tests/test.1
python3 run_experiment.py datetime/tests/random.1
python3 run_experiment.py datetime/tests/random.2
python3 run_experiment.py datetime/tests/identity



"""
from datetime import datetime
from json import dumps
from hashlib import md5
from os import path, environ
from pathlib import Path
from random import randint
from shutil import copy2
from socket import gethostname
from time import perf_counter
from typing import Dict, Tuple, List, Union, Coroutine

# 3rd parety
from diskcache import Cache
from pandas import DataFrame
from tabulate import tabulate

# serentec
from serentec.utils.check_isinstance import check_isinstance
from serentec.utils.comparator import Comparator
from serentec.utils.json.load_json import LoadJSON
from serentec.ingestion.load_benchmark import LoadBenchmark
from serentec.utils.exception_info import exception_info

# phd
from phd.models.load_model import LoadModel
from phd.experiments.config import Config

# logging
from serentec.utils.logger import logger_dl
module_logger = logger_dl.getChild("RunExperiment")

class RunExperiment:
    
    def __init__(self
                 , experiment_name : str
                 , run_number : int = None
                 , timeout_seconds : int = 60
                 , load_model : bool = True
                 , debug : bool = False
                 , debug2 : bool = False
                 ):

        """
        :param experiment_name: name of the experiment, e.g datetime/test.1

        :param run_number: number of the run; allows for versioning of runs and models
            - None: no run number, so data is stored to output.json, output.text and stats.hson
            - integer, e.g 1: create a new run, that can be stored alongside previous runs; can ultimately be used for error bars
                e.g if run_number is e.g 1 (integer), then output will be output.1.json, output.1.text and stats.1.hson

        :param load_model: if False, model loading can be skipped, in very specific cases where previous results are to be used (see assert_cache)

        :param timeout_seconds: timeout for API calls, in seconds
        """

        self.debug = debug
        self.debug2 = debug2

        self.experiment_name = experiment_name
        self.run_number = run_number

        # load global configuration for all experiments
        self.global_config = Config()
        module_logger.debug(f"global experiment config loaded")

        self.experiment_folder = path.join(environ["PYTHONPATH"], "phd", "experiments", "experiments", experiment_name)
        module_logger.debug(f"experiment_folder : {self.experiment_folder}")
        if not Path(self.experiment_folder).exists():
            raise FileNotFoundError(f"Experiment {experiment_name} not found | {self.experiment_folder}")
        
        # load experiment configuration
        config_filename = path.join(self.experiment_folder, "experiment.hjson")
        module_logger.debug(f"experiment : {experiment_name} | config_filename : {config_filename}")
        self.config = LoadJSON().load(config_filename)
        module_logger.debug(f"this experiment config : {dict(self.config)}")

        run_number_suffix = "" if self.run_number is None else f".{self.run_number}"
        self.run_number_id = 0 if self.run_number is None else self.run_number

        self.output_filename = path.join(self.experiment_folder, f"results{run_number_suffix}.json")
        module_logger.debug(f"output_filename : {self.output_filename}")

        self.output_filename_all_results = path.join(self.experiment_folder, f"all_results{run_number_suffix}.json")
        module_logger.debug(f"output_filename_all_results : {self.output_filename_all_results}")

        # load model
        self.model_name = self.config["model"]["name"]
        self.model_config = self.config["model"]["config"]
        self.model_args = self.config["model"]["args"] if "args" in self.config["model"] else {}
        module_logger.debug(f"model_name : {self.model_name} | model_config : {self.model_config} ({type(self.model_config)}) | args : {self.model_args}")
        
        if load_model:
            self.model = LoadModel(model_name=self.model_name
                               , config=self.model_config
                               , timeout_seconds=timeout_seconds
                               , run_number=run_number
                               , **self.model_args
                               )
            
        else:
            module_logger.warning(f"Not loading model as load_model is False")
            self.model = None

        
        # load optional arguments for the prompt
        self.prompt_args = self.config["prompt"] if "prompt" in self.config else None
        module_logger.debug(f"prompt_args : {self.prompt_args}")

        # load benchmark
        # NOTE: omit "benchmark.json.gz", as it could be JSONL
        benchmark_filename = path.join(environ["PYTHONPATH"], "phd", "benchmarks", self.config["benchmark"]["name"])
        module_logger.debug(f"benchmark_filename : {benchmark_filename}")
        self.benchmark = LoadBenchmark(benchmark_filename)

        self.target_field_name = "target" # default field to use as target in the benchmark
        if "target" in self.config["benchmark"]:
            if self.config["benchmark"]["target"] != self.target_field_name:
                self.target_field_name = self.config["benchmark"]["target"]
                module_logger.debug(f"Overriding benchmark target field | '{self.target_field_name}'")
        
        # load LLM prompt template (if present); else set to None and let model use it's own template
        # e.g template : "number_denoise_1"
        self.prompt_template = None
        if "template" in self.config["model"]:
            self.prompt_template = self.config["model"]["template"]
            module_logger.debug(f"Prompt template specified | {self.prompt_template}")

        # create a comparator instance
        if "comparator" in self.config["benchmark"]:
            self.comparator_method = self.config["benchmark"]["comparator"]
        else:
            raise ValueError(f"No comparator found for experiment in {config_filename}")
        
        self.comparator = Comparator(self.comparator_method, return_details=True)
        module_logger.debug(f"Created comparator with method '{self.comparator_method}'")

        module_logger.info(f"benchmark loaded")

        # open local cache
        self.cache = Cache(self.global_config.cache_dir)
        self.cache.reset('size_limit', int(self.global_config.cache_max_size_gbytes * 1e9))
        
        module_logger.info(f"cache loaded : {self.global_config.cache_dir} | {self.global_config.cache_max_size_gbytes}Gb")

        # if all_results already exists, we can use the cached values as an alternative cache source
        # NOTE: they will only be used if experiment is run with try_cache=True
        if path.isfile(self.output_filename_all_results):
            module_logger.debug(f"Results already found for this experiment | Adding them to cache | {self.output_filename_all_results}")

            all_results = LoadJSON().load(self.output_filename_all_results)

            all_results_cached = 0
            for prior_result_idx, prior_result in enumerate(all_results):
                check_isinstance(prior_result, dict)
                
                # A null prediction is a recorded outcome (the geocoder returned
                # no candidate), not a missing one, so it belongs in the cache.
                # Only observations that raised are excluded.
                if prior_result.get("exception") is None:
                    cache_hash, prediction, probability = prior_result["cache_hash"], prior_result["prediction"], prior_result["probability"]
                    self.cache.set(cache_hash, (prediction, probability))
                    all_results_cached += 1

            module_logger.info(f"Added {all_results_cached} of {len(all_results)} prior results existing results to cache")


    async def run(self
                  , save : bool = True
                  , try_cache : bool = False
                  , assert_cache : bool = False
                  , max_obs : int = None
                  , stop_on_error : bool = False
                  ) -> Tuple[Dict, List[Dict], List[Dict], List[Dict]]:
        """
        
        :param save: save to file

        :paramn try_cache: try prompt cache if possible

        :param assert_cache: only use cache; try_cache must be True
            an exception is thrown if value cannot be retrieved from cache

        :param max_obs: if specified, only run this many observations
            if None, all observations are executed

        :param stop_on_error: stop on first error

        :return: 4-tuple; 
            1. dict with results
            2. list of correct predictions
            3. list of errors
            4. list with details of each observation
            
        """

        if assert_cache and not try_cache:
            raise ValueError(f"assert_cache requires try_cache to be True as well")
        
        module_logger.debug(f"try_cache : {try_cache} | assert_cache : {assert_cache}")

        # run
        num_observations = self.config["benchmark"]["num_obs"]
        randomise = self.config["benchmark"]["randomise"]
        benchmark_size = len(self.benchmark.data)

        if benchmark_size == 0:
            raise ValueError(f"Benchmark is empty")

        count_observations = 0
        count_exceptions = 0
        count_predictions = 0
        count_correct = 0

        correct = []
        errors = []
        all_results = []

        t0 = perf_counter()

        for observation_counter in range(num_observations):
            
            count_observations += 1
            observation_idx = observation_counter if not randomise else randint(0, benchmark_size-1)

            t0_observation = perf_counter()

            # adjusted timing: for timing, ignore the first observation because it can include the loading of the model on Ollama
            # which is lengthy and will significantly bias timing estimates
            if count_observations == 1:
                t0_adj = perf_counter()

            # observation
            # {'idx': 0, 'input': '5:48:05 pm mon 09-9-6480', 'target': '6480-09-09T17:48:05', 'noise': [None, None]}
            observation = self.benchmark.data[observation_idx]

            if self.debug:
                module_logger.debug(f"observation_idx : {observation_idx}")
                module_logger.debug(f"observation : {observation}")

            # process input/target pair
            # NOTE: the input can be either a string, in which case it is directly the input_sequence for the prompt
            # or the input can be a dict => must contain 'input_sequence' and any optional arguments for the prompt
            prompt_args = self.prompt_args.copy() if self.prompt_args is not None else {}
            observation_input = observation["input"]
            
            if isinstance(observation_input, str):
                # input is a string => it is directly the input_sequence
                input_sequence = observation_input
            
            elif isinstance(observation_input, dict):
                # input is a dict => must contain 'input_sequence' and any optional arguments for the prompt
                # e.g {"input_sequence" : input_str, "num_days" : num_days}
                if "input_sequence" not in observation_input:
                    raise KeyError(f"input for observation #{observation_idx} is a dict but does not contain 'input_sequence' | {observation_input}")
                
                input_sequence = observation_input["input_sequence"]
                
                # add all other fields to a dict for passing to the prompt generator
                prompt_args = {k : v for k, v in observation_input.items() if k != "input_sequence" }

            else:
                raise ValueError(f"Unhandled input with type {type(observation_input)} | {observation_input}")

            # use specified field from the benchmark
            if self.target_field_name not in observation:
                raise KeyError(f"Field '{self.target_field_name}' not found in observation | {observation}")

            target_sequence = observation[self.target_field_name]
            module_logger.debug(f"target_field_name : {self.target_field_name} | target_sequence : {target_sequence}")

            if self.debug:
                module_logger.debug(f"input_sequence : {input_sequence}")
                module_logger.debug(f"target_sequence : {target_sequence}")
                module_logger.debug(f"prompt_args : {prompt_args}")


            try:

                # cache; the key is the combination of the model configuration and the prompt template (name of the prompt)
                # NOTE: also need to add the run number, to avoid using cached values for different runs
                
                use_cache = False
                
                cache_key = f"{self.model_name}|{self.model_config}|{self.run_number_id}|{self.prompt_template}|{input_sequence}"

                # NOTE: also need to add the number an optional prompt_args specified, e.g. max_tokens
                # NOTE: sort by prompt arg, so that max_tokens=X and temperature=Y is equivalent to temperature=Y and max_tokens=X
                if self.prompt_args is not None:
                    for _k in sorted(self.prompt_args.keys()):
                        cache_key += f"|{_k}={self.prompt_args[_k]}"

                cache_hash = md5(cache_key.encode("UTF-8")).hexdigest()
                

                #module_logger.error(f"debug exit")
                #exit(1)
                

                observation_dict = {
                                "dt" : datetime.now().isoformat()
                                , "observation" : count_observations
                                , "server" : gethostname()
                                , "input_payload" : dumps(observation_input)
                               , "input" : input_sequence
                               , "target" : target_sequence
                               , "prediction" : None
                               , "comparison" : None
                               , "correct" : False
                               , "probability" : None
                               , "cache" : use_cache
                               , "cache_hash" : cache_hash
                               , "cache_key" : cache_key
                               , "prompt_args" : dumps(prompt_args)
                               , "exception" : None
                               , "runtime_ms" : None
                               
                               }

                if try_cache:
                    cache_exists = cache_hash in self.cache
                    module_logger.debug(f"Trying cache | exists : {cache_exists} | key : {cache_key} | hash : {cache_hash}")

                    if assert_cache and not cache_exists:
                        raise RuntimeError(f"Can't retrieve this value from cache | cache_key : {cache_key} | cache_hash : {cache_hash}")
                
                    use_cache = cache_exists

                    if self.debug2:
                        module_logger.debug(f"use_cache : {use_cache}")
                        module_logger.debug(f"cache_key : {cache_key}")
                        module_logger.debug(f"cache_hash : {cache_hash}")
                        module_logger.debug(f"cache_exists : {cache_exists}")

                if use_cache:
                    module_logger.debug(f"Cache hit | {cache_hash}")
                    prediction, probability = self.cache[cache_hash]
                    has_prediction = prediction is not None
                else:
                    
                    # cache miss => call LLM API
                    # NOTE: prediction can be None
                    prediction, probability = None, None
                    has_prediction = False
                    
                    try:
                        # check that a parameters was not specified more than once
                        if self.prompt_args is not None:
                            duplicate_prompt_arg_keys = set(prompt_args.keys()).intersection( set(self.prompt_args.keys()))
                            num_duplicate_prompt_arg_keys = len(duplicate_prompt_arg_keys)
                        
                            if num_duplicate_prompt_arg_keys > 0:

                                # attempt to remove duplicates by comparing values
                                duplicates_resolved = 0
                                for duplicate_prompt_arg_key in duplicate_prompt_arg_keys:
                                    if prompt_args[duplicate_prompt_arg_key] == self.prompt_args[duplicate_prompt_arg_key]:
                                        del prompt_args[duplicate_prompt_arg_key]
                                        duplicates_resolved += 1

                                if duplicates_resolved < num_duplicate_prompt_arg_keys:
                                    print(f"\n** prompt_args **")
                                    print([(k, v) for k, v in prompt_args.items()])
                                    print(f"\n** self.prompt_args **")
                                    print([(k, v) for k, v in self.prompt_args.items()])
                                    raise RuntimeError(f"Found {num_duplicate_prompt_arg_keys} duplicate parameter(s) in prompt args | {duplicate_prompt_arg_keys}")
                        
                        # NOTE: also need to pass prompt args constants (self.prompt_args)
                        prediction, probability = await self.model.predict(input_sequence=input_sequence
                                                                           , prompt_template=self.prompt_template
                                                                           , **(prompt_args if prompt_args is not None else {})
                                                                           , **(self.prompt_args if self.prompt_args is not None else {})
                                                                           )
                                                
                        has_prediction = prediction is not None
                    
                    except ValueError as e:
                        module_logger.warning(f"Value error : {e}")
                        observation_dict["exception"] = str(e)
                        
                        if stop_on_error:
                                exit(1)
                                        

                    # update cache (only if we obtained a prediction)
                    if prediction is not None:
                        self.cache.set(cache_hash, (prediction, probability))

                module_logger.debug(f"has_prediction : {has_prediction} | prediction : {prediction} | p={round(probability, 4) if probability is not None else None}")

                count_predictions += 1 if has_prediction else 0

                observation_dict["has_prediction"] = has_prediction
                observation_dict["prediction"] = prediction # raw prediction
                observation_dict["probability"] = probability
                observation_dict["cache"] = use_cache

                
                # use special utility class for comparing using the correct type; for example, "0.05" != "0.050" if string-wise comparson, but they are the same float-wise
                # check types are compatible
                #if type(prediction) != type(target_sequence):
                #    raise ValueError(f"Incompatible types | Prediction : {prediction} ({type(prediction)}) | Target : {target_sequence} ({type(target_sequence)})")

                #if prediction == target_sequence:
                try:
                    # NOTE: argument order is (needle, haystack)
                    if has_prediction:
                        comparison_results = self.comparator(target_sequence, prediction)
                        assert len(comparison_results) == 2
                        
                        is_correct, comparison_details = comparison_results
                        observation_dict["correct"] = is_correct
                        observation_dict["comparison"] = comparison_details

                        if is_correct:
                            count_correct += 1
                            correct.append(observation_dict)
                            module_logger.info(f"{self.model_name} | Config : {self.model_config} | Prediction : {prediction} | Prediction is correct")
                        else:
                            module_logger.debug(f"{self.model_name} | Config : {self.model_config} | Prediction : {prediction} | Target : {target_sequence} | Prediction is incorrect")
                            errors.append(observation_dict)
                    else:
                        module_logger.debug(f"{self.model_name} | Config : {self.model_config} | Prediction : {prediction} | Target : {target_sequence} | No prediction")
                        errors.append(observation_dict)
                
                except Exception as e:
                    module_logger.warning(f"exception : {e} | {exception_info(e)}")
                    if stop_on_error:
                        print("STOP_ON_ERROR")
                        exit(1)
                    observation_dict["exception"] = str(e)
                    errors.append(observation_dict)
            
            except Exception as e:
                module_logger.warning(f"exception : {e} | {exception_info(e)}")
                if stop_on_error:
                    print("STOP_ON_ERROR")
                    exit(1)

                
                count_exceptions += 1
                
                observation_dict["exception"] = str(e)
                errors.append(observation_dict)


            # add observation to list of observations
            observation_dict["runtime_ms"] = 1000.0 * (perf_counter() - t0_observation)
            
            all_results.append(observation_dict)

            if max_obs is not None and max_obs == count_observations:
                module_logger.error(f"debug break after {max_obs} observations")
                break 

        t1 = perf_counter()
        elapsed_milliseconds = 1000.0 * (t1 - t0)
        elapsed_milliseconds_adj = 1000.0 * (t1 - t0_adj)
        module_logger.info(f"Experiment {self.experiment_name} completed in {round(elapsed_milliseconds, 2)}ms | Adjusted time : {round(elapsed_milliseconds_adj, 2)}ms")

        # compute stats
        stats = {
            "num_observations" : num_observations,
            "actual_observations" : count_observations, 
            "exceptions" : count_exceptions,
            "predictions" : count_predictions,
            "correct" : count_correct,
            "accuracy" : (count_correct / count_observations) if count_observations else None, 
            "accuracy2" : (count_correct / count_predictions) if count_predictions else None,
            "avg_runtime_ms" : elapsed_milliseconds / num_observations, 
            "total_runtime_ms" : elapsed_milliseconds,
            "total_runtime_ms_adj" : elapsed_milliseconds_adj,
            "avg_runtime_ms_adj" : elapsed_milliseconds_adj / (num_observations-1)
        }

        # save results
        result = {
            "dt" : datetime.now().isoformat()
            , "server" : gethostname()
            , "model_instance_uuid" : str(self.model.get_model_instance_uuid()) if self.model is not None else None
            , "model_log_file" : self.model.get_model_logfile() if self.model is not None else None
            , "runtime(ms)" : elapsed_milliseconds
            , "script" : __file__

            # parameters
            , "experiment" : self.config

            # results
            , "stats" : stats
            , "correct" : correct
            , "errors" : errors
        }

        if save:
            # result summary
            with open(self.output_filename, "w", encoding='utf8') as json_file:
                json_file.write(dumps(result))
                module_logger.info(f"saved summary to {self.output_filename}")

            # all results
            with open(self.output_filename_all_results, "w", encoding='utf8') as json_file:
                json_file.write(dumps(all_results))
                module_logger.info(f"saved all results to {self.output_filename}")

            # copy logfile if available
            if self.model is not None:
                model_logfile = self.model.get_model_logfile()
                if model_logfile is not None:
                    src = Path(model_logfile)
                    dst = Path(self.experiment_folder) / "model.log"

                    copy2(src, dst)
                    module_logger.info(f"model's logfile saved to {dst}")


            
        else:
            module_logger.warning(f"Not saving | save is False")



        return stats, correct, errors, all_results


    

if __name__ == '__main__':

    from argparse import ArgumentParser
    from asyncio import run
    
    async def amain():
        parser = ArgumentParser(description='Run an experiment')
        parser.add_argument('experiment', type=str, help='name of the experiment, e.g datetime/test.1')
        
        parser.add_argument('--overwrite', default=False, dest='overwrite', action='store_true', help='overwrite existing benchmark')
        parser.add_argument('--try-cache', default=False, dest='try_cache', action='store_true', help='try using prompt cache ')
        parser.add_argument('--timeout', default=60, type=int, help='timeout for api calls, in seconds')
        parser.add_argument('--stop-on-error', default=False, dest='stop_on_error', action='store_true', help='stop on API error')

        parser.add_argument('--max-obs', default=None, type=int, help='maximum number of observations to process')
        parser.add_argument('--no-save', dest='save', default=True,  action='store_false', help='do not save results')
        
        parser.add_argument('--debug', default=False, dest='debug', action='store_true', help='debugging')
        parser.add_argument('--debug2', default=False, dest='debug2', action='store_true', help='debugging')
        
        args = parser.parse_args()
        
        experiment = RunExperiment(args.experiment, timeout_seconds=args.timeout, debug=args.debug)

        # check not already run
        if args.save and path.isfile(experiment.output_filename):
            if args.overwrite:
                module_logger.warning(f"Experiment already run... re-running")
            else:
                module_logger.error(f"Experiment already exists. Either delete it or specify overwrite flag")
                exit(1)


        # run benchmark
        stats, correct, errors, _ = await experiment.run(save=args.save
                                                      , try_cache=args.try_cache
                                                      , max_obs=args.max_obs
                                                      , stop_on_error=args.stop_on_error
                                                      )
       

        print(f"\n-- stats --")
        for k, v in stats.items():
            print(f"{k} : {v}")

        print(f"\n-- correct --")
        if len(correct):
            df_correct = DataFrame(correct)
            print(tabulate(df_correct, headers="keys", tablefmt="orgtbl"))
        else:
            print("no data")

        print(f"\n-- errors --")
        if len(errors):
            df_errors = DataFrame(errors, dtype=str)
            #print(tabulate(df_errors, headers="keys", tablefmt="orgtbl"))
            print(df_errors)
        else:
            print("no data")

            
        await experiment.model.close()

    run(amain())



