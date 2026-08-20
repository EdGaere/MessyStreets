"""
create_benchmark.py: Create a benchmark

NOTES

CREATED
edward | 2024-08-17

USAGE
python3 create_benchmark.py datetime/a.3
python3 create_benchmark.py datetime/a3.iso8601.add.day.250.x

# CREATE RANGE
# NOTE: existing benchmarks are not overwritten
for precision in `seq 1 1 10`; do 
    for run in `seq 1 1 10`; do 
        config="address/address.wdc.${run}.geohash${precision}"
        output="${config}/benchmark.json.gz"
        # skip existing runs
        if [ -e $output ]; then 
            continue
        fi
        # run
        echo "precision : $precision | run : $run | $config"
        python3 create_benchmark.py "$config"
    done
done
"""

if __name__ == '__main__':

    from argparse import ArgumentParser
    from datetime import datetime, timedelta
    import gzip
    from json import dumps
    from os import path
    from random import choice, shuffle, seed
    from socket import gethostname
    from time import perf_counter

    # data
    from dpath import get, search
    from pandas import DataFrame
    from tabulate import tabulate
    from tqdm import tqdm # progress bar

    # serentec
    from serentec.utils.check_isinstance import check_isinstance
    from serentec.ml.generators.load_generator import LoadGenerator
    from serentec.ml.generators.load_generators import LoadGenerators
    from serentec.utils.strings.insert_noise import InsertNoise
    from serentec.utils.json.load_json import LoadJSON
    from serentec.ingestion.load_benchmark import LoadBenchmark
    from serentec.utils.comparator import Comparator


    # logging
    from serentec.utils.logger import logger_dl
    module_logger = logger_dl.getChild("CreateBenchmark")
    
    def main():
        parser = ArgumentParser(description='Run the model on N static observations in the benchmarks/ folder')
        parser.add_argument('config', default=None, type=str, help='name of the generator, without the /ml/generators path; e.g numbers/float/generate6.py')

        parser.add_argument('--overwrite', default=False, dest='overwrite', action='store_true', help='overwrite existing benchmark')
        parser.add_argument('--stop_on_overlap', default=False, dest='stop_on_overlap', action='store_true', help='stop on first detected overlap')

        parser.add_argument('--stop_on_error', default=False, dest='stop_on_error', action='store_true', help='debugging')
        parser.add_argument('--stop-on-error', default=False, dest='stop_on_error', action='store_true', help='debugging')
        parser.add_argument('--debug', default=False, dest='debug', action='store_true', help='debugging')
        parser.add_argument('--debug2', default=False, dest='debug2', action='store_true', help='debugging')
        parser.add_argument('--debug3', default=False, dest='debug3', action='store_true', help='debugging')
        
        args = parser.parse_args()

        # load config
        load_json = LoadJSON()
        config_filename = path.join(args.config, "config.hjson")
        module_logger.debug(f"config_filename : {config_filename}")
        
        config = load_json.load(config_filename)
        module_logger.debug(f"configuration read")

        output_jsonl = config.get("jsonl", False)

        t0 = perf_counter()

        # determine output file (compressed json)
        output_file = path.join(args.config, "benchmark.jsonl.gz") if output_jsonl else path.join(args.config, "benchmark.json.gz")
        module_logger.debug(f"output_file : {output_file} | output_jsonl : {output_jsonl}")
        
        if path.isfile(output_file):
            module_logger.warning(f"benchmark file {output_file} already exists")
            if not args.overwrite:
                raise RuntimeError(f"Benchmark {output_file} already exists => use option --overwrite to overwrite")

        # randomisation options
        # NOTE: this needs to occur before loading the generator(s) to ensure the seed, if specified, is set globally across the process
        _randomise = config.get("randomise")

        if _randomise is None:
            randomise = False
        
        elif isinstance(_randomise, bool):
            randomise = _randomise

        elif isinstance(_randomise, dict):
            randomise = _randomise["value"]
            randomise_seed = _randomise["seed"]

            # set random seed; use random.seed which sets the global seed across the entire process, also inside the generator
            seed(randomise_seed)
            module_logger.debug(f"Setting random seed to {randomise_seed}")

        else:
            raise ValueError(f"Unhandled value for 'randomise' in config | {_randomise}")
     
        # osbervation identifier field
        osbervation_identifier_field = None
        if config.get("id") is not None:
            osbervation_identifier_field = config["id"]

        module_logger.debug(f"osbervation_identifier_field : {osbervation_identifier_field}")

        # skip duplicate outputs
        # NOTE: by default lexical duplicates of the inputs are discarded
        skip_duplicate_ouputs = False

        if config.get("skip_duplicate_ouputs", False):
            skip_duplicate_ouputs = True

            module_logger.debug(f"skip_duplicate_ouputs : {skip_duplicate_ouputs}")

        # max_input_sequence_length; None => no limit
        max_input_sequence_length = config.get("max_input_sequence_length")
        module_logger.debug(f"max_input_sequence_length : {max_input_sequence_length}")

        # load generator
        if "generator" in config:
            """
            generate can either be:

            1) generator : "address/schema_org/generators/schema_org_v2.py"

            2) generator : {
        
                    base_path : /Users/gaeree/phd/phd/datasets

                    name : "address/schema_org/generators/schema_org_v2.py"
                }
            """
            generator_config = config["generator"]

            if isinstance(generator_config, str):
                generator = LoadGenerator(config["generator"], debug=args.debug2, debug2=args.debug3)
            
            elif isinstance(generator_config, dict):
                generator_base_path = generator_config["base_path"]
                module_logger.debug(f"generator_base_path : {generator_base_path}")
                
                generator = LoadGenerator(generator_config["name"]
                                          , base_path=generator_base_path
                                          , debug=args.debug2
                                          , debug2=args.debug3
                                          )

            else:
                raise ValueError(f"Unhandled generator config '{generator_config}'")
            
            module_logger.debug(f"single generator loaded : {config['generator']}")
        
        elif "generators" in config:
            generator = LoadGenerators(config["generators"], debug=args.debug2, debug2=args.debug3)
            module_logger.debug(f"multiple generators loaded | {generator.num_generators} generators")

        else:
            raise ValueError(f"could not find keys 'generator' or 'generators' in config")

        # optional arguments for the generator
        generator_args = {}
        if "same_month" in config:
            generator_args["same_month"] = config["same_month"]            

        if "locale_schema" in config:
            generator_args["locale_schema"] = config["locale_schema"]

        if "month_schema" in config:
            generator_args["month_schema"] = config["month_schema"]

        if "schemas" in config:
            schemas = config["schemas"]
            generator_args["schemas"] = schemas
            module_logger.debug(f"Settings schemas to {schemas}")

        if "kwargs" in config:
            generator_args.update(config["kwargs"])
        
            
        module_logger.debug(f"{len(generator_args)} generator arguments")

        for arg_idx, (k, v) in enumerate(generator_args.items()):
            module_logger.debug(f"Argument {arg_idx+1} of {len(generator_args)} | {k} | {v}")

        # noise insertion
        insert_noise = None
        if config.get('noise') is not None:
            insert_noise = InsertNoise(config['noise']['level'], p_noise=config['noise']['prob'])

        num_observations = config['num_obs']

        # handling of null
        skip_missing_data = False
        skip_null_value = None
        raise_on_missing_data = False
        if "missing_data" in config and isinstance(config["missing_data"], dict):
            skip_missing_data = config["missing_data"]["skip"]
            skip_null_value = config["missing_data"]["value"]
            raise_on_missing_data = config["missing_data"].get("raise", False)

            if skip_missing_data is True:
                module_logger.warning(f"Skipping missing data | {skip_null_value}")

        # exclusions
        exclusions = []
        # exclusions allows specifiying another benchmark and ensuring no overlap; this is necessary when creating FT datasets to avoid contamination
        
        # NOTE: create a set of unique values to exclude for fast exclusion
        exclusion_values = set()
        fast_exclusion = None
        fast_exclusion_exclusion_compare_field_name = None

        if "exclusions" in config:
            fast_exclusion = True
            
            for exclusion_idx, exclusion_config in enumerate(config["exclusions"]):
                """
                each config is a dict
                {
                    benchmark : "datetime/iso8601.add.day.50.x"

                    comparator : iso8601-datepart

                    # optional
                    field : input
                }
                """

                module_logger.debug(f"Adding exclusion #{exclusion_idx+1} | {exclusion_config}")

                exclusion_comparator_type = exclusion_config["comparator"]
                # NOTE: auto-discover the appropriate file type (JSON, JSONL, ...)
                #exclusion_benchmark = LoadBenchmark(exclusion_config["benchmark"] + "/benchmark.json.gz")
                exclusion_benchmark = LoadBenchmark(exclusion_config["benchmark"])
                exclusion_comparator = Comparator(exclusion_comparator_type)
                # NOTE: exclusion could be on another value than the input field; for example the obbservation id
                exclusion_field = exclusion_config.get("field", "input")

                # NOTE: allow dpath notations, e.g "input/input_dt"
                #exclusion_values_this_benchmark = [observation[exclusion_field] for observation in exclusion_benchmark.data]
                exclusion_values_this_benchmark = [get(observation, exclusion_field) for observation in exclusion_benchmark.data]
                exclusion_values.update(exclusion_values_this_benchmark)

                exclusions.append({
                    "config" : exclusion_config
                    , "field" : exclusion_field
                    , "inputs" : exclusion_values_this_benchmark
                    , "comparator" : exclusion_comparator
                })

                # fast exclusion can only be used if the comparator is string
                if exclusion_comparator_type != "str":
                    if fast_exclusion:
                        module_logger.warning(f"Fast exclusion not possible as exclusion #{exclusion_idx} has comparator '{exclusion_comparator_type}'")
                        fast_exclusion = False

                # fast exclusion can only be used if all the exclusions are on the same field
                if fast_exclusion_exclusion_compare_field_name is None:
                    fast_exclusion_exclusion_compare_field_name = exclusion_field
                else:
                    if exclusion_field != fast_exclusion_exclusion_compare_field_name:
                        module_logger.warning(f"Fast exclusion not possible as exclusion #{exclusion_idx} has comparator field '{exclusion_field}' | Another comparator has field '{fast_exclusion_exclusion_compare_field_name}'")
                        fast_exclusion = False


            module_logger.info(f"{len(exclusions)} exclusion(s) found | Unique values to be excluded : {len(exclusion_values)}")

            if fast_exclusion:
                module_logger.info(f"Fast exclusion is possible on field '{fast_exclusion_exclusion_compare_field_name}'")

        else:
            module_logger.warning(f"No exclusions found")

        # generate observations in the benchmark format
        # BACKLOG: add more options, in particular day-month formats
        # BACKLOG: if this generates OOM, resolve to DiskBackedList (https://claude.ai/chat/79b5a76c-7e82-420d-b07c-27ba0f13408a)
        data = []

        # METHODOLOGY: prevent duplicates on the inputs; exact string match
        all_inputs = set()

        # METHODOLOGY: optional; prevent duplicates based on targets
        all_outputs = set()
        
        batch_size = config.get("batch_size", 100) # generate in batches due to exclusions
        observation_idx = 0
        overlap_count = 0
        null_counter = 0
        skip_counter = 0
        lexical_input_duplicates_discarded = 0
        target_outputs_discarded = 0

        # balanced dataset
        balanced_config = config.get("balanced")
        balanced_constraint = balanced_config.get("active") if balanced_config is not None else False
        balanced_constraint_field = balanced_config.get("field") if balanced_config is not None else None
        module_logger.debug(f"balanced_constraint : {balanced_constraint} | balanced_constraint_field : {balanced_constraint_field}")

        progress_bar = tqdm(total=num_observations)

        # optional; copy the aux field from the input, directly provides information in the benchmark for easier debugging/analysis
        save_aux = config.get("save_aux", False)

        if args.debug:
            module_logger.debug(f"save_aux : {save_aux}")

        # generate data in batches until the number of required observations has been achieved; this approach is necessary because
        # we may exclude certain observations due to overlap (exclusions), so in total more observations that than the required number need to be generated
        # NOTE: oversample if we need a balanced dataset, so we can deterministically draw required labels without affecting ordering
        while len(data) < (num_observations + (1.2 * num_observations if balanced_constraint else 0)):


            generator_function = generator.generate(output=config['output']
                                                    , num_observations=batch_size
                                                    , stop_on_error=args.stop_on_error
                                                    , **generator_args
                                                    )
            
            for observation, _ in generator_function:

                if args.debug:
                    module_logger.debug(f"Trial observation #{observation_idx+1} of {num_observations} | {observation}")

                
                # NOTE: some observations have no output, e.g if the component is missing
                # for example, the component "year" is missing in the string "fri eight.july.,5 am"
                # in such cases, ignore the 
                if observation.output is None:
                    if args.debug:
                        module_logger.warning(f"Ignorning observation #{observation_idx} with None output | {observation}")
                    continue
                
                # optionaly skip missing data or raise an exception
                if observation.output == skip_null_value:
                    if raise_on_missing_data:
                        raise ValueError(f"Missing data detected | observation #{observation_idx} | {observation}")
                    
                    elif skip_missing_data:
                        skip_counter += 1
                        if args.debug:
                            module_logger.warning(f"Ignorning observation #{observation_idx} with missing data output 'observation.output' | {observation}")
                        continue

                # insert noise
                # NOTE: if noise is disabled, insert_noise() simply returns the input string
                if insert_noise is not None:
                    input_with_noise, noise_details = insert_noise.insert_noise(observation.input, return_details=True)
                else:
                    input_with_noise, noise_details = observation.input, None


                # standardise the input, as some inputs are dicts; e.g.
                raw_input_value = input_with_noise
                """
                {
                    "input_sequence" : input_str
                        , "num_days" : 250
                        , "input_fs_1" : input_str_1
                        , "target_fs_1" : (input_dt_1 + timedelta(days=250)).isoformat()
                        , "input_fs_2" : input_str_2
                        , "target_fs_2" : (input_dt_2 + timedelta(days=250)).isoformat()
                }
                """
                if isinstance(input_with_noise, str):
                    pass

                elif isinstance(input_with_noise, dict):
                    input_with_noise = input_with_noise["input_sequence"]

                else:
                    raise TypeError(f"Unhandled type {type(input_with_noise)} for input '{input_with_noise}'")

                # skip lexical duplicates based in unputs
                if input_with_noise in all_inputs:
                    lexical_input_duplicates_discarded += 1
                    if args.debug:
                            module_logger.warning(f"Ingoring duplicate input #{lexical_input_duplicates_discarded} | Observation #{observation_idx+1} | {input_with_noise}")
                    continue

                # skip duplciate labels based on the output of each observation
                if skip_duplicate_ouputs:
                    if observation.output in all_outputs:                       
                        target_outputs_discarded += 1
                        if args.debug:
                            module_logger.warning(f"Ingoring duplicate observation #{target_outputs_discarded} for target '{observation.output} | Observation #{observation_idx+1} ")
                        continue

                    all_outputs.add(observation.output)


                all_inputs.add(input_with_noise)
                
                # check for any overlaps
                overlap_found = False

                if fast_exclusion is None:
                    # nothing to compare
                    overlap_found = False
                elif fast_exclusion:
                    
                    # determine what to compare
                    if fast_exclusion_exclusion_compare_field_name == "input":
                        exclusion_compare_value = input_with_noise
                    
                    else:
                        try:
                            if fast_exclusion_exclusion_compare_field_name.startswith(r"input/"):
                                # NOTE: allow dpath notation anywhere inside the input dict , e.g. "input/input_dt"
                                _exclusion_key = fast_exclusion_exclusion_compare_field_name.replace(r"input/", "")
                                exclusion_compare_value = get(observation.input, _exclusion_key)
                                
                            else:
                                # legacy assumes field is in the aux section
                                exclusion_compare_value = observation.aux[fast_exclusion_exclusion_compare_field_name]
                        except:
                            # fallback
                            exclusion_compare_value = input_with_noise
                        
                    assert exclusion_compare_value is not None
                    check_isinstance(exclusion_compare_value, str)

                    overlap_found = exclusion_compare_value in exclusion_values
                else:
                    for exclusion in exclusions:
                        comparator = exclusion["comparator"]
                        exclusion_inputs = exclusion["inputs"]

                        # NOTE: the comparison could be be performed on other fields than input_with_noise
                        exclusion_compare_field_name = exclusion["field"]
                        if exclusion_compare_field_name == "input":
                            exclusion_compare_value = input_with_noise

                        # look for path, e.g. input/input_sequence
                        elif exclusion_compare_field_name.startswith(r"input/"):
                            _exclusion_key = exclusion_compare_field_name.replace(r"input/", "")
                            exclusion_compare_value = get(observation.input, _exclusion_key)

                        else:
                            exclusion_compare_value = observation.aux[exclusion_compare_field_name]

                        for exclusion_input in exclusion_inputs:
                            if comparator(exclusion_input, exclusion_compare_value):
                                # overlap detected
                                overlap_found = True
                                exclusion_config = exclusion["config"]
                                exclusion_benchmark = exclusion["config"]["benchmark"]
                                exclusion_comparator = exclusion["config"]["comparator"]

                                if args.debug:
                                    module_logger.warning(f"Overlap detected | Ignorning observation #{observation_idx} | '{input_with_noise}' overlaps '{exclusion_input}' from {exclusion_benchmark} | {exclusion_comparator}")
                                
                                if args.stop_on_overlap:
                                    module_logger.error(f"stop_on_overlap")
                                    exit(1)
                                
                                # no need to iterate further, this observation needs to be disgarded
                                continue

                        if overlap_found:
                            # no need to iterate further, this observation needs to be disgarded
                            continue

                
                if overlap_found:
                    overlap_count += 1
                else:
                    # add observation to the index
                    observation_idx += 1

                    progress_bar.update(1)

                    output_dict = {"idx" : observation_idx
                                , "input" : raw_input_value
                                , "target" : observation.output
                                , "noise" : noise_details # the inserted noise, as a string, or None
                                }
                    
                    
                    # METHODOLOGY: limit on input sequence length
                    if max_input_sequence_length is not None:
                        if len(input_with_noise) > max_input_sequence_length:
                            module_logger.warning(f"Excluding observation with length {len(input_with_noise) } > {max_input_sequence_length} | {input_with_noise}")
                            continue

                    # osbervation_identifier_field
                    if osbervation_identifier_field is not None:
                        if observation.aux is None or osbervation_identifier_field not in observation.aux:
                            raise ValueError(f"osbervation_identifier_field set ({osbervation_identifier_field}) but aux is not available")
                        osbervation_identifier = get(observation.aux, osbervation_identifier_field)

                        if osbervation_identifier is None:
                            raise ValueError(f"osbervation_identifier ({osbervation_identifier_field}) found but value is None")
                        
                        output_dict["id"] = osbervation_identifier

                    if save_aux is not None:
                        output_dict["aux"] = observation.aux

                    data.append(output_dict)
                    
                    null_counter += 1 if observation.output == "NULL" else 0

                
                if len(data) == num_observations:
                    break

        progress_bar.close()

        # enforce balance dataset
        if balanced_constraint:
            module_logger.info("Constructing balanced benchmark")
            # get all values for balanced constraint
            all_labels = set([get(o, balanced_constraint_field) for o in data])
            num_labels = len(all_labels)
            target_obs_per_label = num_observations // num_labels
            module_logger.debug(f"Found {num_labels} labels | target_obs_per_label : {target_obs_per_label} | {all_labels}")
            
            # get required vakules from data => balanced_data
            # NOTE: ordering is preserved for reproducibiity
            counts = {}
            balanced_data = []
            for obs in data:
                label = get(obs, balanced_constraint_field)
                counts[label] = counts.get(label, 0) + 1
                if counts[label] <= target_obs_per_label:
                    # NOTE: renumber the values, 1 based; and don't change the original
                    obs = obs.copy()
                    obs["idx"] = len(balanced_data) + 1 
                    balanced_data.append(obs)

                # early exit
                if all(counts.get(l, 0) >= target_obs_per_label for l in all_labels):
                    break

            # copy balanced dataset back into main dataset
            data = balanced_data
            if len(data) != num_observations:
                raise RuntimeError(f"Expected {num_observations} observations after balancing | Generated : {len(data)}")

        
        t1 = perf_counter()
        module_logger.info(f"Benchmark contains {len(data)} observations")

        if null_counter > 0:
            module_logger.warning(f"Benchmark contains {null_counter} observations with target 'NULL'")

        if skip_counter > 0:
            module_logger.warning(f"Skipped {skip_counter} observations with target '{skip_null_value}'")
        else:
            module_logger.info(f"No values were skipped with value '{skip_null_value}'")

        if len(exclusions):
            module_logger.info(f"{overlap_count} overlaps excluded | {round(100.0 * overlap_count / num_observations, 2)}%")

        if lexical_input_duplicates_discarded > 0:
            module_logger.warning(f"{lexical_input_duplicates_discarded} lexical duplicates based in input discarded")

        if target_outputs_discarded > 0:
            module_logger.warning(f"{target_outputs_discarded} target duplicates based in field '{osbervation_identifier_field}' discarded")

            
           
        if randomise:
            # shuffle is inplace using Fisher-Yates and needs only O(1) extra memory.
            module_logger.debug(f"randomising order...")
            shuffle(data)
            module_logger.debug("randomised")

        # NOTE: because some observations are removed (e.g when target is None), we may not have generated enough observations
        if len(data) < num_observations:
            raise RuntimeError(f"Not enough observations generated | Expected : {num_observations} | Generated : {len(data)}")

        elapsed_seconds = t1 - t0
        elapsed_time_str = str(timedelta(seconds=elapsed_seconds))

        # save compressed JSON
        output = {
            "meta" : {
                "dt" : datetime.now().isoformat()
                , "server" : gethostname()
                , "runtime(hms)" : elapsed_time_str
                , "script" : __file__
                , "output" : output_file
                , "config" : config
                , "arguments" : vars(args)
            }
            , "data" : data
        }
        
        module_logger.debug(f"saving to to {output_file}...")

        
        # save to JSON / JSONL
        if output_jsonl:

            with gzip.open(output_file, "wt", encoding="utf-8") as f:
                for item in tqdm(data, total=len(data), unit=" obs", desc="Writing"):
                    # METHODOLOGY: preserve unicode, else strings will contain corrupt unicode characters : "\u6c38\u660c\u8def..Kangshan..People's Republic of China"
                    f.write(dumps(item, ensure_ascii=False))
                    f.write("\n")

            # meta data
            metadata_output_file = path.join(args.config, "benchmark.meta.json")
            with open(metadata_output_file, "w", encoding="utf-8") as f:
                f.write(dumps(output["meta"], indent=2))

            module_logger.debug(f"Saved JSONL to {output_file} and metadata {metadata_output_file}")

        else:
            # NOTE: as the data can get large, we can't JSON serialise the entire file into memory => write directly to the file serialising each row
            # this JSON streaming pattern would fit nicely with the DiskBackedList if necessary, although the latter is probably no longer necesasry
            # see: https://claude.ai/chat/79b5a76c-7e82-420d-b07c-27ba0f13408a
            with gzip.open(output_file, "wt", encoding="utf-8") as f:
                f.write('{"meta": ')
                f.write(dumps(output["meta"]))
                f.write(', "data": [\n')
                for i, item in enumerate(tqdm(data, total=len(data), unit=" obs", desc="Writing")):
                    if i > 0:
                        f.write(",\n")
                    # METHODOLOGY: preserve unicode, else strings will contain corrupt unicode characters : "\u6c38\u660c\u8def..Kangshan..People's Republic of China"
                    f.write(dumps(item, ensure_ascii=False))
                f.write("\n]}")

            module_logger.debug(f"Saved JSON to {output_file}")


        # preview
        print(f"\n-- Preview --")

        # prepare data preview = input + flattened visible components
        preview = []

        for _ in range(20):
            observation = choice(data)
            columns = {"observation" : observation["idx"], "input" : observation["input"], "noise" : observation["noise"], "target" : observation["target"]}
            preview.append(columns)
        
        df = DataFrame(preview, dtype=str )

        # NOTE: do *not* use tabulate to disaply the data as it will modify the formatting of numbers arbitrarily
        print(df.head(n=10))

        print()
        print(df.tail(n=10))

        module_logger.info(f"Num observations : {num_observations} | Runtime : {elapsed_time_str} | {output_file}")

        
        


       


    main()