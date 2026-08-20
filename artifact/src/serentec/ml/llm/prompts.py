# -*- coding: utf-8 -*-

"""
prompts.py: utility for rendering prompts for LLMs

BASE
None

CHANGE LOG
edward | 2023-07-11 | init

BACKLOG

USAGE
python3 prompts.py is_english "The cat danced on the mat"
python3 prompts.py translate_to_english "Le chat dance sur le tapis"
python3 prompts.py is_abusive_language "I HATE EVERY SINGLE ONE OF YOU###"

python3 prompts.py creative_summary_20 "For the first time in over a hundred years, a former American president had to testify under oath on the witness stand in a trial against himself. Donald Trump seemed to enjoy his appearance in a New York court on Monday more than he feared it."

python3 prompts.py extract_origin_destination_json "I am flying from Geneva to Athens"

# data chat
python3 prompts.py extract_user_intentions "I need exchange EUR/USD data" --system_prompt "databot"
python3 prompts.py extract_user_intentions "I need exchange rate data from the European Central Bank" --system_prompt "databot"

# phd prompts
python3 prompts.py iso8601_add_day_50_nlep_4 "9999-12-31T23:59:59" --config /Users/gaeree/phd/phd/configs/prompts.json


"""

# system
from datetime import date, datetime, time, timedelta
from json import loads
from inspect import signature
from os import path
from re import search
from typing import Any, List, Set, Dict, Tuple, Optional, Union, Iterable, Iterator

# serentec
from serentec.exceptions import Error, FileNotFound
from serentec.utils.check_isinstance import check_isinstance
from serentec.utils.file.check_isfile import check_isfile

# serentec machine learning
from serentec.ml.config import Config as MLConfig

# serentec: logging
from serentec.utils.logger import logger_dl
module_logger = logger_dl.getChild("Prompts")

class Prompts:

    # training configuration
    def __init__(self
        , config_file : str = r"configs/prompts.json"
        , debug : bool = False
        ):

        """
       
        """

        self.debug = debug

        check_isfile(config_file)
        self.config_file = config_file
        
        with open(config_file, "r", encoding='utf8') as json_file:
            all_fields = loads(json_file.read())
            assert isinstance(all_fields, dict)
            
            self.templates = all_fields["templates"]
            assert isinstance(self.templates, dict)
    
            self.system_prompts = all_fields["system_prompts"]
            assert isinstance(self.templates, dict)

            self.models = all_fields["models"]
            assert isinstance(self.templates, dict)
        

        module_logger.debug(f"Loaded {len(self.templates)} prompt templates from {config_file}")

   
    def generate(self, template_name : str, system_prompt_name : Optional[str] = None, **kwargs) -> Tuple[str, Dict]:
        """

        Generate the prompt.

        :param template_name: name of the template in the prompts.json file, e.g "is_english"

        :param system_prompt_name:  optional; name of the system prompt to use
            if specified, overrides the default system prompt that is associated with template_name
            NOTE: this is the name of the system prompt, not the name of a template

        :param kwargs: optional; parameters to be used to create the prompt. Two possibilities how the parameter is used:

            1. if the argument is in the required_parameters of the prompt, then it is used to create the input sequence
                e.g if the prompt requires 'input_sequence', then you would pass input_sequence='some text to be inserted into the prompt'
            
            2. if the argument is not in the required_parameters, it is added to the prompt parameters, along side temperature, max_tokens, etc

        :return: 2-tuple
            1. user prompt 
            2. dict of additional elements for the request:
                - system_prompt
                - max_tokens
                - jsonschema
                - ...

        """

        check_isinstance(template_name, str)

        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found in templates ({self.config_file})")

        # retrieve template specifications
        template_info = self.templates[template_name]

        # system prompt; precedence rules
        # 1. use argument
        # 2. use system prompt specified in the template
        # 3. use default prompt
        # NOTE: some models like T5/FLAN do not appear to have a system prompt
        system_prompt = None

        if system_prompt_name is not None:
            module_logger.debug(f"Overriding system prompt using argument value | {system_prompt_name}")

            if system_prompt_name not in self.system_prompts:
                raise ValueError(f"Override system prompt '{system_prompt_name}' not found in system prompts ({self.config_file})")
            
            system_prompt = self.system_prompts[system_prompt_name]

        elif "system_prompt" not in template_info:
            system_prompt_name = None
            # NOTE/BACKLOG: T5-FLAN models don't appear to have system prompts
            module_logger.warning(f"Prompt template '{template_name}' does not have a system prompt specified ({self.config_file})")
            
        else:
            # use system prompt specified in the prompt template
            system_prompt_name = template_info["system_prompt"]

            if system_prompt_name is not None:
                if system_prompt_name not in self.system_prompts:
                    raise ValueError(f"System prompt '{system_prompt_name}' not found in system prompts ({self.config_file})")
        
                system_prompt = self.system_prompts[system_prompt_name]

        if self.debug:
            module_logger.debug(f"System prompt | Name : {system_prompt_name} | {system_prompt}")

        
        # user prompt        
        required_parameters = template_info["parameters"]
        template = template_info["template"]
        max_tokens = template_info.get("max_tokens", None)
        jsonschema = template_info.get("jsonschema", None)
        temperature = template_info.get("temperature", None)
        return_type = template_info.get("return_type", None)
        top_p = template_info.get("top_p", None)
        description = template_info.get("description", None)

        functions = template_info.get("functions", None)
        function_call = template_info.get("function_call", None)

        # check parameters are supplied as arguments to this function
        replace_dict = {}
        for required_parameter in required_parameters:
            if required_parameter not in kwargs:
                raise ValueError(f"required parameter '{required_parameter}' not provided but is required for template '{template_name}' | Provided : {kwargs.keys()}")
            
            
            # check the required parameter is in the template
            # e.g "Here is some text from a user : \"{input_sequence}\". Is the text writte
            token = r"{" + required_parameter + r"}"
            if token not in template:
                raise ValueError(f"required parameter '{required_parameter}' was specified but not found in the template {template_name} : {template}")
            
            required_parameter_value = kwargs[required_parameter]
            if required_parameter_value is None:
                raise ValueError(f"required parameter '{required_parameter}' was specified but with value None")
            
            replace_dict[token] = str(required_parameter_value)

        # render the prompt
        output = template

        for k, v in replace_dict.items():
            output = output.replace(k, v)

        # check there are no unresolved parameter placeholders in the prompt
        # NOTE: there could be genuine curly braces in the input sequence, so raise a warning only e.g. 石{塔}巷;彰化縣;Taiwan, Province of China
        if search(r"\{[^}]+\}", output):
            module_logger.warning(f"Possibly unresolved placeholder in prompt: {output}")

        # return aux information (settings for the prompt)
        aux = {
            "system_prompt" : system_prompt
            , "jsonschema" : jsonschema
            , "max_tokens" : max_tokens
            , "temperature" : temperature
            , "return_type" : return_type
            , "functions" : functions
            , "function_call" : function_call
            , "top_p" : top_p
            , "description" : description
        }

        # add any meta parameters provided in kwargs that were not part of the prompt
        for parameter_name, parameter_value in kwargs.items():
            if parameter_name not in required_parameters:
                
                if parameter_value in aux:
                    _prev_parameter_value = aux[parameter_name]
                    module_logger.warning(f"Overriding default prompt parameter | {parameter_name} | {_prev_parameter_value} -> {parameter_value}")
                else:
                    if self.debug:
                        module_logger.debug(f"Adding prompt parameter | {parameter_name} | {parameter_value}")

                aux[parameter_name] = parameter_value

        
        return output, aux

if __name__ == '__main__':

    from argparse import ArgumentParser
  
    def main():

        # init command line arguments
        cmd_line_parser = ArgumentParser(description='Prompts')
        cmd_line_parser.add_argument('template_name', type=str, default=None, help="is_english")
        cmd_line_parser.add_argument('input_sequence', type=str, default=None, help="The cat danced on the mat")
      
        # arguments for the generator
        cmd_line_parser.add_argument('--config', type=str, default=r"configs/prompts.json", help="prompt templates")
             
        # flags
        cmd_line_parser.add_argument('--debug', default=False, dest='debug', action='store_true', help='debugging')
        
        args = cmd_line_parser.parse_args()


        # create instance of the class
        prompts = Prompts(config_file=args.config, debug=args.debug)

        prompt, aux = prompts.generate(args.template_name, input_sequence=args.input_sequence)
        print(prompt)

        if args.debug:
            for k, v in aux.items():
                print(k, v)
        
       
    main()

   