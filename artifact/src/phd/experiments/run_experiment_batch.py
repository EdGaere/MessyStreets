"""
run_experiment_batch.py: Run an experiment, evaluating all observations in a single batch

BASE
run_experiment.py

NOTES

CHANGE LOG
edward | 2025-11-02

BACKLOG

SETUP
# multiple ollama instances
export OLLAMA_HOST=82.130.119.17:9301,82.130.119.34:9301

USAGE

# fine-tuned models
python3 run_experiment_batch.py address/paper2-address-country-v1-unsloth/paper2-address-country-1-unsloth-ft-1-qwen2.5-0.5b-fp-ft-13.S=100-batch --max-obs 1 --debug

# paper 2 specialised address parsers
python3 run_experiment_batch.py address/paper2-address-country-v1-lstm/istr
python3 run_experiment_batch.py address/paper2-address-country-v1-libpostal/istr
python3 run_experiment_batch.py address/paper2-address-country-v1-deepparse/istr/bpemb-attention



"""
from datetime import datetime
from json import dumps, loads
from hashlib import md5
from os import path, environ
from random import randint
from socket import gethostname
from time import perf_counter
from typing import Dict, Tuple, List, Union, Coroutine, Any

# 3rd parety
from diskcache import Cache
from pandas import DataFrame
from tabulate import tabulate

# serentec
from serentec.utils.check_isinstance import check_isinstance
from serentec.utils.comparator import Comparator
from serentec.utils.json.load_json import LoadJSON
from serentec.ingestion.load_benchmark import LoadBenchmark
from serentec.ml.llm.prompts import Prompts

# phd
from phd.models.load_model import LoadModel
from phd.experiments.config import Config

# logging
from serentec.utils.logger import logger_dl
module_logger = logger_dl.getChild("RunExperimentBatch")

class RunExperimentBatch:
    
    def __init__(self
                 , experiment_name : str
                 , run_number : int = None
                 , timeout_seconds : int = 60
                 , debug : bool = False
                 , debug2 : bool = False
                 ):

        """
        :param experiment_name: name of the experiment, e.g datetime/test.1

        :param run_number: number of the run; allows for versioning of runs and models
            - None: no run number, so data is stored to output.json, output.text and stats.hson
            - integer, e.g 1: create a new run, that can be stored alongside previous runs; can ultimately be used for error bars
                e.g if run_number is e.g 1 (integer), then output will be output.1.json, output.1.text and stats.1.hson

        :param timeout_seconds: timeout for API calls, in seconds
        """

        self.debug = debug
        self.debug2 = debug2

        self.experiment_name = experiment_name
        self.run_number = run_number

        # load global configuration for all experiments
        self.global_config = Config()
        module_logger.debug(f"global experiment config loaded")
        
        # load experiment configuration
        config_filename = path.join(environ["PYTHONPATH"], "phd", "experiments", "experiments", experiment_name, "experiment.hjson")
        module_logger.debug(f"experiment : {experiment_name} | config_filename : {config_filename}")
        self.config = LoadJSON().load(config_filename)
        module_logger.debug(f"this experiment config : {dict(self.config)}")

        run_number_suffix = "" if self.run_number is None else f".{self.run_number}"
        self.run_number_id = 0 if self.run_number is None else self.run_number

        self.output_filename = path.join(environ["PYTHONPATH"], "phd", "experiments", "experiments", experiment_name, f"results{run_number_suffix}.batch.json")
        module_logger.debug(f"output_filename : {self.output_filename}")

        self.output_filename_all_results = path.join(environ["PYTHONPATH"], "phd", "experiments", "experiments", experiment_name, f"all_results{run_number_suffix}.batch.json")
        module_logger.debug(f"output_filename_all_results : {self.output_filename_all_results}")

        # load model
        self.model_name = self.config["model"]["name"]
        self.model_config = self.config["model"]["config"]
        self.model_args = self.config["model"]["args"] if "args" in self.config["model"] else {}
        module_logger.debug(f"model_name : {self.model_name} | model_config : {self.model_config} ({type(self.model_config)}) | args : {self.model_args}")
        
        self.model = LoadModel(model_name=self.model_name
                               , config=self.model_config
                               , timeout_seconds=timeout_seconds
                               , run_number=run_number
                               , **self.model_args
                               )

        
        # load optional arguments for the prompt
        self.prompt_args = self.config["prompt"] if "prompt" in self.config else None
        module_logger.debug(f"prompt_args : {self.prompt_args}")

        # load benchmark
        benchmark_filename = path.join(environ["PYTHONPATH"], "phd", "benchmarks", self.config["benchmark"]["name"], "benchmark.json.gz")
        module_logger.debug(f"benchmark_filename : {benchmark_filename}")
        self.benchmark = LoadBenchmark(benchmark_filename)
        
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
                
                has_prediction = prior_result.get("has_prediction", False)
                if has_prediction:
                    cache_hash, prediction, probability = prior_result["cache_hash"], prior_result["prediction"], prior_result["probability"]
                    self.cache.set(cache_hash, (prediction, probability))
                    all_results_cached += 1

            module_logger.info(f"Added {all_results_cached} of {len(all_results)} prior results existing results to cache")


        # load prompts file
        prompts_filename = path.join( environ["PYTHONPATH"], "phd", "configs", "prompts.json")
        module_logger.debug(f"prompts_filename : {prompts_filename}")

        module_logger.debug(f"loading prompts from {prompts_filename}...")
        self.prompts = Prompts(prompts_filename, debug=debug2)

        # defaults
        self.default_model_args = {"max_tokens" : 1000, "temperature" : 0.0}



    async def run(self
                  , save : bool = True
                  , try_cache : bool = False
                  , assert_cache : bool = False
                  , max_obs : int = None
                  , stop_on_error : bool = False
                  ) -> Tuple[Dict, List[Dict], List[Dict], List[Dict]]:
        """
        
        :param save: save to file

        :param try_cache: try prompt cache if possible

        :param assert_cache: only use cache; try_cache must be True
            an exception is thrown if value cannot be retrieved from cache

        :param max_obs: not supported in batch mode

                :param stop_on_error: stop on first error

        :return: 4-tuple; 
            1. dict with results
            2. list of correct predictions
            3. list of errors
            4. list with details of each observation
            
        """

        if max_obs is not None:
            raise NotImplementedError(f"max_obs is not supported in batch mode | must be None")
        
        if assert_cache and not try_cache:
            raise ValueError(f"assert_cache requires try_cache to be True as well")
                
        module_logger.debug(f"try_cache : {try_cache} | assert_cache : {assert_cache}")
        
        # model arguments
        model_args = self.default_model_args.copy()
        module_logger.debug(f"model_args (default) : {model_args}")

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
        
        # batch processing => collect all input sequences to be processed
        observations : List[Dict] = []
        all_prompt_args : List[Dict] = [] # arguments for the prompt for each observation
        batch_input_sequences_idx : List[int] = []

        predictions, probabilities = [], []

        # create observation dict for all observations; use cache if possible
        for observation_counter in range(num_observations):
            
            count_observations += 1
            observation_idx = observation_counter if not randomise else randint(0, benchmark_size-1)

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
                
                # override default prompt_args
                # this is necessary for prompts that require additional inputs, e.g. example_1, example_2, etc
                for k, v in observation_input.items():
                    if k != "input_sequence":
                        prompt_args[k] = v

                print(f"prompt_args : {prompt_args}")

            else:
                raise ValueError(f"Unhandled input with type {type(observation_input)} | {observation_input}")

            target_sequence = observation["target"]

            if self.debug:
                module_logger.debug(f"input_sequence : {input_sequence}")
                module_logger.debug(f"target_sequence : {target_sequence}")
                module_logger.debug(f"prompt_args : {prompt_args}")

            # cache; the key is the combination of the model configuration and the prompt template (name of the prompt)
            # NOTE: also need to add the run number, to avoid using cached values for different runs
            use_cache = False
            
            cache_key = f"{self.model_name}|{self.model_config}|{self.run_number_id}|{self.prompt_template}|{input_sequence}"

            # NOTE: also need to add the number an optional prompt_args specified, e.g. max_tokens
            # NOTE: sort by prompt arg, so that max_tokens=X and temperature=Y is equivalent to temperature=Y and max_tokens=X
            if prompt_args is not None:
                for _k in sorted(prompt_args.keys()):
                    cache_key += f"|{_k}={prompt_args[_k]}"

            cache_hash = md5(cache_key.encode("UTF-8")).hexdigest()
            module_logger.debug(f"observation idx : {observation_idx} | cache_hash : {cache_hash} | cache_key : {cache_key}")

            # HACK: infer model-level arguments from the prompt-level arguments
            prompt_args_to_remove = {}
            for k, v in prompt_args.items():
                if k in model_args:
                    # remove argument from prompt argument
                    prompt_args_to_remove[k] = v
                                
            # remove argument from prompt argument + # update model argument
            for k, v in prompt_args_to_remove.items():
                del prompt_args[k]
                # check consistent model arguments across all observations, since in batch prediction we can only set the model arguments once
                if k in model_args:
                    # NOTE: the first observation can have a different value than the default
                    if observation_counter > 0 and model_args[k] != v:
                        raise ValueError(f"new value for model_args '{k}' is '{v}' | must match previous value '{model_args[k]}'")
                
                model_args[k] = v


            # save observation
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

                observation_dict["has_prediction"] = True
                observation_dict["prediction"] = prediction
                observation_dict["probability"] = probability
                observation_dict["cache"] = use_cache
            
            else:
                module_logger.debug(f"Cache miss => batch proessing | {cache_hash}")

                # store the position in this experiment (observation_counter), not the position in the entire benchmark (observation_idx)
                # so we can put the result of the batch processing back into the correct position of the observations
                batch_input_sequences_idx.append(observation_counter) 

            observations.append(observation_dict)
            print(f"final prompt_args : {prompt_args}")
            all_prompt_args.append(prompt_args)


        # compute batch inferences (if any)
        assert len(observations) == num_observations

        if self.debug2:
            print("\n-- observations --")
            for observation_counter in range(num_observations): 
                print(observation_counter, observations[observation_counter])
                
        if len(batch_input_sequences_idx) > 0:
            module_logger.debug(f"{len(batch_input_sequences_idx)} items required for batch processing")
            
            # render all the prompts together with their arguments
            batch_inputs = [observations[batch_input_sequence_idx]["input"] for batch_input_sequence_idx in batch_input_sequences_idx]

            t0_batch = perf_counter()
            predictions, probabilities = await self.model.predict_batch(input_sequences=batch_inputs
                                                                , prompt_template=self.prompt_template
                                                                , prompt_args=all_prompt_args
                                                                , **model_args
                                                            )
            

            t1_batch = perf_counter()
            batch_elapsed_ms = 1000. * (t1_batch - t0_batch)
            batch_elapsed_ms_per_obs = batch_elapsed_ms / len(batch_inputs)

            if self.debug2:
                module_logger.debug(f"{len(predictions)} predictions generated using batch inference in {round(batch_elapsed_ms, 2)}ms")

                for prediction_idx, (prediction, probability) in enumerate(zip(predictions, probabilities)):
                    module_logger.debug(f"{prediction_idx} | prediction : {prediction} | probability : {probability}")
         
        else:
            module_logger.info(f"All predictions can be used from cache")

        # if batch prediction were made, place batch results back into the list of observations
        if len(predictions) > 0:
            assert len(predictions) == len(probabilities)
            for batch_input_sequences_id, prediction, probability in zip(batch_input_sequences_idx, predictions, probabilities):

                has_prediction = prediction is not None

                # update cache (only if we obtained a prediction)
                if has_prediction:
                    self.cache.set(cache_hash, (prediction, probability))

                if self.debug:
                    module_logger.debug(f"batch_input_sequences_id : {batch_input_sequences_id} | prediction : {prediction} | p={round(probability, 4) if probability is not None else None}")

                observation_dict = observations[batch_input_sequences_id]

                count_predictions += 1 if has_prediction else 0

                observation_dict["has_prediction"] = True
                observation_dict["prediction"] = prediction # raw prediction
                observation_dict["probability"] = probability
                observation_dict["cache"] = False
                observation_dict["runtime_ms"] = batch_elapsed_ms_per_obs

                observations[batch_input_sequences_id] = observation_dict

      
        # evaluate all results
        for observation_dict in observations: 

            has_prediction = observation_dict["prediction"] is not None
            prediction = observation_dict["prediction"]
            target_sequence = observation_dict["target"]

            

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
                observation_dict["exception"] = str(e)
                errors.append(observation_dict)
            
            
            all_results.append(observation_dict)


        t1 = perf_counter()
        elapsed_milliseconds = 1000.0 * (t1 - t0)
        module_logger.info(f"Experiment {self.experiment_name} completed in {round(elapsed_milliseconds, 2)}ms")

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
            "total_runtime_ms_adj" : elapsed_milliseconds,
            "avg_runtime_ms_adj" : elapsed_milliseconds / num_observations, 
        }

        # save results
        result = {
            "dt" : datetime.now().isoformat()
            , "server" : gethostname()
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

            
        else:
            module_logger.warning(f"Not saving | save is False")
            

        return stats, correct, errors, all_results


    

if __name__ == '__main__':

    from argparse import ArgumentParser
    from asyncio import run
    
    async def amain():
        parser = ArgumentParser(description='Run an experiment in batch mode')
        parser.add_argument('experiment', type=str, help='name of the experiment, e.g datetime/test.1')
        
        parser.add_argument('--overwrite', default=False, dest='overwrite', action='store_true', help='overwrite existing benchmark')
        parser.add_argument('--try-cache', default=False, dest='try_cache', action='store_true', help='try using prompt cache ')
        parser.add_argument('--timeout', default=60, type=int, help='timeout for api calls, in seconds')
        parser.add_argument('--stop-on-error', default=False, dest='stop_on_error', action='store_true', help='stop on API error')

        parser.add_argument('--no-save', dest='save', default=True,  action='store_false', help='do not save results')
        
        parser.add_argument('--debug', default=False, dest='debug', action='store_true', help='debugging')
        parser.add_argument('--debug2', default=False, dest='debug2', action='store_true', help='debugging')
        
        args = parser.parse_args()
        
        experiment = RunExperimentBatch(args.experiment, timeout_seconds=args.timeout, debug=args.debug, debug2=args.debug2)

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
                                                      , stop_on_error=args.stop_on_error
                                                      )
       

        print(f"\n-- stats --")
        for k, v in stats.items():
            print(f"{k} : {v}")

        num_observations = stats["num_observations"]

        print(f"\n-- {len(correct)} of {num_observations}  correct --")
        if len(correct):
            df_correct = DataFrame(correct)
            print(tabulate(df_correct.head(n=5), headers="keys", tablefmt="orgtbl"))
        else:
            print("no correct")

        print(f"\n-- {len(errors)} of {num_observations} errors --")
        if len(errors):
            df_errors = DataFrame(errors, dtype=str)
            #print(tabulate(df_errors, headers="keys", tablefmt="orgtbl"))
            print(df_errors.head(n=5))
        else:
            print("no errors")

            
        await experiment.model.close()

    run(amain())



