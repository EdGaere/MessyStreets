"""
load_generators.py: Load N generators from a list, assigning a new target value for each generator according to a mapping

BASE
phd/phd/ner1/generate.py

NOTES
- datasets may not necessarily be balanced depending on the size of each generator's domain

SAMPLE INPUT
special/missing_data/missing_data1.py : NULL
dates/date/generate18.py : NA
dates/time/generate14.py : NA

SAMPLE OUTPUT
'#NA' => NULL
'93.11th.1' => NA
'19 pm' => NA
'january 5032' => NA
'2740/42' => NA
'46/04' => NA

CHANGE LOG
edward | 2023-06-08 | init

USAGE
python3 load_generators.py special/ner/configs/models3.list 10

# batch B inputs together into a single input
python3 load_generators.py noise_models_1.list 10 --batch_size 5

BACKLOG
- the term 'balanced' is ambiguous; it could refer to either:
    1. balanced generators (currently the case); each generator is represented equally
    2. balanced targets, i.e targets appear in equal proportion

"""

from collections import Counter, OrderedDict
import importlib
from os import path, makedirs
from typing import Tuple, Iterator, Union, List
from uuid import uuid4

# serentec: utils
from serentec.utils.check_isinstance import check_isinstance

# serentec: ml
from serentec.ml.training_pair import TrainingPair

# serentec: logging
from serentec.utils.logger import logger_dl
module_logger = logger_dl.getChild("LoadGenerators")

class LoadGenerators:
    def __init__(self
                 , model_list : Union[str, List[str], List[Tuple[str, str]]]
                 , debug : bool = False
                 , debug2 : bool = False
                 ):

        """

        :param model_list: 3 possibilities here
            1. models_list_filename: full path + filename with list of generators to load and their mapping; example
                dates/date/generate18.py : DATE
                dates/time/generate14.py : TIME
                dates/datetime/generate16.22.py : DATETIME
                ...
            
            2. a list of model names with mapping (same as filename but in list form)

            3. a list of model names only, with no mapping

        :param max_input_len: maximum size for any input sequence
            if None, inputs are not cropped
        
        """

        

        self.debug = debug 

        # NOTE: all generators should have an output named "model"
        self.default_target = "model"

        # load generators
        # NOTE: as model_name (named entity) is not unique, use store as a list of tuples
        self.generators = [] # List[Tuple]
        self.generator_names = {}
        classes = []

        # NOTE: adapt to different deployment options
        base_generator_paths = [
                                r"/Users/gaeree/SerenTec2/serentec/ml/generators" # laptop
                                , r"/home/edward/SerenTec/serentec/ml/generators" # A0
                                , r"/local/home/gaeree/SerenTec/serentec/ml/generators" # ETH GPU
                                ]
        
        base_generator_path = None
        for _path in base_generator_paths:
            if path.exists(_path):
                base_generator_path = _path
                break

        module_logger.debug(f"base_generator_path : {base_generator_path}")
        if base_generator_path is None:
            raise FileNotFoundError(f"Could not find a generator path from {base_generator_paths}")

        # generalise the input
        if isinstance(model_list, str):
            # nothing to do, list of models is already a filename
            if not path.isfile(model_list):
                raise FileNotFoundError(f"list of models not found in {model_list}")
            
            models_list_filename = model_list
        
        elif isinstance(model_list, list):
            output_list = [
                f"{model[0]} : {model[1]}" if isinstance(model, tuple) else f"{model} : NULL"
                    for model in model_list
            ]

            # write output list to file
            models_list_filename = path.join("/tmp", str(uuid4()))

            with open(models_list_filename, "w") as f_out:
                for line in output_list:
                    f_out.write(f"{line}\n")

            module_logger.debug(f"Using generated model list | {models_list_filename}")

        else:
            raise TypeError(f"Don't know how to handle model_list of type {type(model_list)} | {model_list}")

        # open file and read models
        with open(models_list_filename, "r") as models_file:

            while True:

                line = models_file.readline()

                if not line:
                    break
                
                # ignore blank lines and comments
                line = line.strip()
                
                if len(line) > 0 and not line.startswith("#"):

                    # expected format
                    # "dates/date/generate18.py : DATE"
                    generator_name = line.split(" : ")[0].strip()
                    label = line.split(" : ")[1].strip()

                    # check a generator does not appear twice
                    assert generator_name not in self.generator_names

                    # stats on the distribution
                    self.generator_names[generator_name] = label
                    classes.append(label)
                    

                    generator_path = path.join(base_generator_path, generator_name)
                    if self.debug:
                        module_logger.debug(f"loading {generator_path}...")

                    if not path.isfile(generator_path):
                        raise RuntimeError(f"generator {generator_name} not found {base_generator_path}")
            
                    module_spec = importlib.util.spec_from_file_location('generator', generator_path)
                    assert module_spec is not None
                    generator_module = importlib.util.module_from_spec(module_spec)
                    module_spec.loader.exec_module(generator_module)

                    # create instance of the class
                    generator = generator_module.Generate()
                    generator.debug = debug2

                    if self.debug:
                        module_logger.debug(f"\t{generator_name} => {label}")

                    # store model
                    # NOTE: as label (named entity) is not unique, use store as a list of tuples
                    self.generators.append((generator, label))

        self.num_generators = len(self.generators)
        module_logger.debug(f"loaded {self.num_generators} models")
        assert self.num_generators >= 1

        # count number of generators per class; required for creating a balanced dataset
        self.classes = dict(Counter(classes))

        if self.debug:
            module_logger.debug(f"class counts : {self.classes}")


   
    def generate(self
                    , num_observations : int
                    , balanced : bool = False
                    , batch_size : int = 1
                    , batch_delimiter : str = chr(3) # ETX
                    , max_input_len : int = None
                    , output : str = None
                    , **kwargs
                    ) -> Iterator[ Tuple[ TrainingPair, None] ]:
        """

        :param balanced: create a balanced dataset with the same number of observations per class
            default is False => same number of observations per generator

        :param output: which output to generate; 
            - if None (default), the label in the model list provided in the constructor is used
                dates/date/generate18.py : DATE
                dates/time/generate14.py : TIME
                dates/datetime/generate16.22.py : DATETIME

            - if not None, then the value of 'output' is passed to each generator and that value is used

        
        :param kwargs: any additional arguments for the underlyinggenerators

        """
        assert isinstance(batch_size, int)
        assert batch_size >= 1

        if batch_size > 1:
            assert isinstance(batch_delimiter, str)

        # determine output
        generator_output_name = self.default_target if output is None else output

        if self.debug:
            module_logger.debug(f"generator_output_name : {generator_output_name} | output argument : {output}")

        # compute number of observations per generator; at least 1
        if not balanced:
            # non-balanced dataset => compute number of observations per generator; at least 1
            num_observations_per_generator = max(int(num_observations / self.num_generators), 1)
            if self.debug:
                module_logger.debug(f"non-balanced dataset : num_observations_per_generator = {num_observations_per_generator}")
        else:
            num_observations_per_class = max(int(num_observations / len(self.classes)), 1)

            if self.debug:
                module_logger.debug(f"balanced dataset : num_observations_per_class = {num_observations_per_class}")

        for generator, generator_name in self.generators:

            if self.debug:
                module_logger.debug(f"\t{generator_name}..")

            if not balanced:
                num_observations_this_generator = num_observations_per_generator
            else:
                number_generators_this_class = self.classes[generator_name]
                num_observations_this_generator = max(int(num_observations_per_class / number_generators_this_class), 1)
                
                if self.debug:
                    module_logger.debug(f"number_generators_this_class : {number_generators_this_class}")

            if self.debug:
                module_logger.debug(f"num_observations_this_generator : {num_observations_this_generator}")

            if batch_size > 1:
                if self.debug:
                    module_logger.debug(f"Using batch size : {batch_size}")
            
            for training_pair_idx in range(num_observations_this_generator):

                # NOTE: some legacy generators yield more observations than specified in the call to generate()
                if training_pair_idx == num_observations_this_generator:
                    break

                # batched inputs: group N inputs together into a single observation
                batch_inputs = []

                for batch_idx, (training_pair, _) in enumerate(generator.generate(output=generator_output_name
                                                                , num_observations=batch_size
                                                                , **kwargs
                                                                ), start=0):

                    # NOTE: some legacy generators yield more observations than specified in the call to generate()
                    if batch_idx == batch_size:
                        break

                    # NOTE: clip the inputs to max length, else
                    # 1. inputs can exceeed the T5 spec
                    # 2. run out of memory on GPU when training
                    if not isinstance(training_pair.input, str):
                        raise ValueError(f"Invalid input; expecting string, found {type(training_pair.input)} |  {training_pair.input}")
                    _input = training_pair.input

                    if max_input_len is not None:
                        _input = training_pair.input[0:max_input_len]

                    if self.debug:
                        print(f"{generator_name} | pair : #{training_pair_idx} | batch : #{batch_idx} | {training_pair} => {_input}")

                    # NOTE: we can't successfully join on the batch_delimiter (e.g ETX character) if that character is already in the data to be joined
                    if batch_size > 1:
                        assert batch_delimiter not in _input

                    batch_inputs.append(_input)

                batch_inputs_str = batch_delimiter.join(batch_inputs)

                if self.debug:
                    print(f"batch_inputs | {len(batch_inputs)} | {batch_inputs_str}")

                # NOTE: if output is None, the output label is the tag assigned to the generator in models.list
                # else it's the output value of the generator
                output_value = generator_name if output is None else training_pair.output
                yield (TrainingPair(input=batch_inputs_str, output=output_value, locale=None, aux={"generator" : generator_name}), None)

                
                

if __name__ == '__main__':

    from argparse import ArgumentParser
    from datetime import datetime, timedelta
    from json import dumps
    from socket import gethostname
    from pickle import dump
    from time import perf_counter

    def main():
        parser = ArgumentParser(description='Generate training and test datasets')
        parser.add_argument('models_list_filename', default=None, type=str, help='list of models in configs/, e.g models.list')
        parser.add_argument('num_observations', default=None, type=int, help='number of observations to generate')
       
        # generation parameters
        parser.add_argument('-m', "--max_input_len", default=512, type=int, help='maximum size for any input sequence *before* batching')
        parser.add_argument('-b', "--batch_size", default=1, type=int, help='number of observations per input, ETX delimited')
        parser.add_argument('-d', "--batch_delimiter", default=chr(3), type=str, help='batch delimiter; default is ETC')
        parser.add_argument('--balanced', default=False, dest='balanced', action='store_true', help='create balanced dataset per class')
        
        parser.add_argument('--debug', default=False, dest='debug', action='store_true', help='debugging')
        parser.add_argument('--debug2', default=False, dest='debug2', action='store_true', help='debugging')
        
        args = parser.parse_args()


        generator = LoadGenerators(models_list_filename=args.models_list_filename
                                    , debug=args.debug
                                    , max_input_len=args.max_input_len
                                    )
        
        for _input, _label in generator.generate(args.num_observations
                                                , balanced=args.balanced
                                                , batch_size=args.batch_size
                                                , batch_delimiter=args.batch_delimiter
                                                ):
            print(f"'{_input}' => {_label}")

      


    main()