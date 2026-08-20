"""
load_model.py: load a model

NOTES

CHANGE LOG
edward | 2024-08-17

BACKLOG

USAGE
python3 load_model.py openai_chatgpt generic/gpt-o1-low --predict "what is 10 + 10?" --prompt "chat"
python3 load_model.py test_1 None
python3 load_model.py random_model random_10

# make a prediction
python3 load_model.py test_1 None --predict "8 pm 49 thursday fifth-ii-70"

# specify different configs
python3 load_model.py random_model random_10 --predict "8 pm 49 thursday fifth-ii-70"
python3 load_model.py random_model random_20 --predict "8 pm 49 thursday fifth-ii-70"

# serentec models
python3 load_model.py serentec datetime/datetime_to_day --debug --predict "fourth#may#8264, 6:24:16.886686 pm"

# live models
python3 load_model.py openai_chatgpt datetime_to_day/gpt-3.5-turbo --debug --predict "8 pm 49 thursday fifth-ii-70"
python3 load_model.py llama3_replicate datetime_to_day/meta-llama-3.1-405b-instruct --debug --predict "8 pm 49 thursday fifth-ii-70"
python3 load_model.py gemma_replicate datetime_to_day/gemma-7b-it --debug --predict "8 pm 49 thursday fifth-ii-70"
python3 load_model.py mixtral_replicate datetime_to_day/mixtral-8x7b-instruct-v0.1 --debug --predict "8 pm 49 thursday fifth-ii-70"
python3 load_model.py anthropic datetime_to_day/claude-3-opus --debug --predict "8 pm 49 thursday fifth-ii-70"

# different configs
python3 load_model.py llama_replicate datetime_to_second/meta-llama-2-70b-chat-lead --debug --predict "11:48:15 +0100,Thu 19 Oct 4845"

# ollama
python3 load_model.py gemma2_ollama datetime_to_iso8601_1/gemma2:27b --debug --predict "11:48:15 +0100,Thu 19 Oct 4845"
python3 load_model.py mistral_nemo_ollama datetime_to_iso8601_1/mistral-nemo-12b --debug --predict "11:48:15 +0100,Thu 19 Oct 4845"

"""

from importlib.util import spec_from_file_location, module_from_spec
from os import path, environ
from typing import Any, Optional, Tuple, Union, Dict, List
from uuid import UUID

from serentec.utils.check_isinstance import check_isinstance
from serentec.utils.json.load_json import LoadJSON

from phd.models.model_base import ModelBase

# logging
from serentec.utils.logger import logger_dl
module_logger = logger_dl.getChild("LoadModel")

class LoadModel(ModelBase):

    def __init__(self
                 , model_name : str
                 , config : Optional[Union[str, Dict]] = None
                 , run_number : int = None
                 , timeout_seconds : int = 60
                 , debug : bool = False
                 , debug2 : bool = False
                 , **kwargs
                 ):
        """
        load model with the specified config

        :param model_name: name of the model

        :param run_number: number of the run; allows for versioning of runs and models
            - None: no run number, so data is stored to output.json, output.text and stats.hson
            - integer, e.g 1: create a new run, that can be stored alongside previous runs; can ultimately be used for error bars
                e.g if run_number is e.g 1 (integer), then output will be output.1.json, output.1.text and stats.1.hson

        :param timeout_seconds: timeout for API calls, in seconds

        :param config: optional; either:
            1. a string with the name of the config file for the model (located in the configs folder of the model's path )
            2. a dict with the config itself


        :param kwargs: any optional kwargs for the model
        """

        check_isinstance(model_name, str)

        self.debug = debug
        self.model_name = model_name
        self.run_number = run_number

        self.model_args = kwargs
        check_isinstance(self.model_args, dict, none_ok=True)

        if self.debug:
            module_logger.debug(f"model_args : {self.model_args}")
        
        self.model_path = path.join(environ["PYTHONPATH"], "phd", "models", "models", model_name)
        self.model_filename = path.join(self.model_path, "model.py")
        if self.debug:
            module_logger.debug(f"loading model from {self.model_filename}...")
        if not path.isfile(self.model_filename):
            raise FileNotFoundError(f"Model not found for model '{model_name}' : {self.model_filename}")

        # load config
        self.config = None

        if config is not None:
            if isinstance(config, str):
                self.config_filename = path.join(self.model_path, "configs", f"{config}.hjson")
                module_logger.debug(f"loading config from {self.config_filename}...")
                if not path.isfile(self.config_filename):
                    raise FileNotFoundError(f"Config not found for model '{model_name}' : {self.config_filename}")
                
                self.config = LoadJSON().load(self.config_filename)

            elif isinstance(config, dict):
                self.config = config
            
            else:
                raise TypeError(f"Don't know how to handle a config of type '{type(config)}' | {config}")

            
            if self.debug:
                module_logger.info(f"Config loaded : {config}")
        else:
            module_logger.warning("No config for this model")

        # load model
        model_spec = spec_from_file_location('Model', self.model_filename)
        self.model_module = module_from_spec(model_spec)
        model_spec.loader.exec_module(self.model_module)

        # create instance of the class
        self.model = self.model_module.Model(self.config
                                             , timeout_seconds=timeout_seconds
                                             , run_number=self.run_number
                                             , debug=debug
                                             , debug2=debug2
                                             , **kwargs
                                             )
        
        self.supports_batch_prediction = hasattr(self.model, "predict_batch")

        if self.debug:
            module_logger.info(f"Model loaded : {model_name} | supports_batch_prediction : {self.supports_batch_prediction}")

        

    def get_model_instance_uuid(self) -> UUID:
        return self.model.get_model_instance_uuid()

    def get_model_logfile(self) -> Optional[str]:
        return self.model.get_model_logfile()
    
    async def close(self):
        await self.model.close()

    
    async def predict_batch(self
                            , input_sequences : List[str]
                            , prompt_template : Optional[str] = None
                            , prompt_args : Optional[List[Dict]] = None
                            , **kwargs) -> Tuple[ List[Optional[Any]], List[Optional[float]] ]:
        """
        Batch prediction.

        :param prompt_template: optional; use this prompt template
            if not specified, the default template defined at init is used (self.prompt_template)

        :param prompt_args: optional list of arguments for each prompt

        :param **kwargs: any additional arguments for the prompt or the model

        Returns 2 lists:
            1. predictions (should be cast to the correct type, e.g str, int, ... )
                can be None if the model returned no prediction
            2. probabilities
        """

        module_logger.debug(f"predict_batch | batch size : {len(input_sequences)} | prompt_template : {prompt_template} | kwargs : {kwargs}")

        if not self.supports_batch_prediction:
            raise NotImplementedError(f"Model {self.model_filename} does not support predict_batch")
        
        _output_sequences, probabilities = await self.model.predict_batch(input_sequences=input_sequences
                                                                          , prompt_template=prompt_template
                                                                          , prompt_args=prompt_args
                                                                          , **kwargs
                                                                          )

        # performing minimal cleaning if string
        # NOTE: _output_sequence can be None
        output_sequences = []

        for _output_sequence in _output_sequences:
            if isinstance(_output_sequence, str):
                output_sequences.append(_output_sequence.replace('\n', '').replace(r"```", "").strip())
            else:
                output_sequences.append(_output_sequence)

        return output_sequences, probabilities


    async def predict(self, prompt_template : Optional[str] = None, **kwargs) -> Tuple[Optional[Any], float]:
        """
        Make a single prediction

        :param prompt_template: optional; use this prompt template
            if not specified, the default template defined at init is used (self.prompt_template)

        :param **kwargs: any additional arguments for the prompt template

        Retruns a 2-tuple; 
            1. prediction (should be cast to the correct type, e.g str, int, ... )
            2. probability
        """
        
        if self.debug:
            module_logger.debug(f"predict | prompt_template : {prompt_template} | kwargs : {kwargs}")

        _output_sequence, probability = await self.model.predict(prompt_template=prompt_template
                                                                 , **kwargs
                                                                 )

        if self.debug:
            module_logger.debug(f"{_output_sequence} | p={round(probability, 2) if probability is not None else None}")

        # performing minimal cleaning if string
        # NOTE: _output_sequence can be None
        if isinstance(_output_sequence, str):
            output_sequence = _output_sequence.replace('\n', '').replace(r"```", "").strip()
        else:
            output_sequence = _output_sequence #.replace('\n', '').replace(r"```", "").strip()

        return output_sequence, probability


if __name__ == '__main__':

    from argparse import ArgumentParser
    from asyncio import run
    
    async def amain():
        parser = ArgumentParser(description='Loads an model')
        parser.add_argument('model', type=str, help='name of the model')
        parser.add_argument('config', type=str, help='name of the config')

        parser.add_argument('--predict', default=None, type=str, help='input sequence')
        parser.add_argument('--prompt_template', default=None, type=str, help="use this prompt instead of the default 'chat' prompt")

        parser.add_argument('--debug', default=False, dest='debug', action='store_true', help='debugging')
        parser.add_argument('--debug2', default=False, dest='debug2', action='store_true', help='debugging')
        
        args = parser.parse_args()

        # harmonise to Python types
        if args.config == "None":
            args.config = None

        load_model = LoadModel(args.model, args.config, debug=args.debug, debug2=args.debug2)

        if args.predict is not None:
            if args.prompt_template is not None:
                output_sequence, probability = await load_model.predict(input_sequence=args.predict, prompt_template=args.prompt_template)
            else:
                output_sequence, probability = await load_model.predict(input_sequence=args.predict)
            print(f"output_sequence : {output_sequence}")
            print(f"p : {round(probability, 4) if probability is not None else None}")

        await load_model.close()

    run(amain())

