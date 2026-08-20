# -*- coding: utf-8 -*-

"""
responses.py: utility for translating LLM responses to Python variables

BASE
None

CHANGE LOG
edward | 2023-07-21 | init

BACKLOG
- implement RestrictedPython

USAGE
python3 responses.py "True." true_false
python3 responses.py "True." bool
python3 responses.py "bla bla bla" str

"""

# system
from contextlib import redirect_stdout
from csv import reader
from datetime import date, datetime, time, timedelta
from io import StringIO
from json import loads
from inspect import signature
from os import path
from string import digits
from typing import Any, List, Set, Dict, Tuple, Optional, Union, Iterable, Iterator

# 3rd party
#from RestrictedPython import compile_restricted, safe_globals, PrintCollector # execution of Python in a trusted environment

# serentec
from serentec.exceptions import Error, FileNotFound
from serentec.utils.check_isinstance import check_isinstance
from serentec.utils.file.check_isfile import check_isfile
from serentec.utils.interpreters.python_interpreter import PythonInterpeter

# serentec machine learning
from serentec.ml.config import Config as MLConfig

# serentec: logging
from serentec.utils.logger import logger_dl
module_logger = logger_dl.getChild("Responses")

class Responses:

    def __init__(self, debug : bool = False, debug2 : bool = False):

        self.debug = debug
        self.debug2 = debug2
        
        # Python interpreter, for executing Python code in a secured environment, using RestrictedPython
        self.python_interpreter = PythonInterpeter(restricted=False, debug=debug2)

        # set an upper bound on time to execute the Python code
        self.python_execution_timeout_seconds = 60 

        if self.debug:
            module_logger.debug(f"Read | python_execution_timeout_seconds : {self.python_execution_timeout_seconds}")

        # list of tokens to be removed from any answer
        self.remove_tokens = ["<think>", "</think>"]
   
    def translate(self, raw_answer : str, return_type : str, lookup_dict : dict = None) -> Any:
        """

        Generate the prompt.

        :param raw_answer: raw response from the LLM, string

        :param return_type: target type to transform to:
            - json -> Dict
            - bool -> bool
            - true_false -> str("True" or "False")
            - str -> str

        :return: Python variable

        """

        check_isinstance(raw_answer, str)
        check_isinstance(return_type, str)

        answer = None

        # pre-cleaning
        tokens_removed = 0
        for remove_token in self.remove_tokens:
            if remove_token in raw_answer:
                raw_answer = raw_answer.replace(remove_token, "").strip()
                tokens_removed += 1

        if self.debug and tokens_removed > 0:
            module_logger.debug(f"Removed {tokens_removed} tokens | raw answer after removal : '{raw_answer}'")


        if return_type == "json":
            answer = loads(raw_answer)
      
        # some cleaning
        elif return_type in ("bool", "boolean"):
            raw_answer = raw_answer.lower().strip()
            if raw_answer in ("yes", "yes.", "true", "true."):
                answer = True
            elif raw_answer in ("no", "no.",  "false", "false."):
                answer = False
            
            else:
                raise ValueError(f"Don't know how to cast raw answer '{raw_answer}' to bool")
        
        elif return_type == "true_false":
            raw_answer = raw_answer.lower().strip()
            if raw_answer in ("yes", "yes.", "true", "true."):
                return "True"
            elif raw_answer in ("no", "no.",  "false", "false."):
                return "False"
            else:
                raise ValueError(f"Don't know how to cast raw answer '{raw_answer}' to true_false")
        
        elif return_type == "csv":

            # split but preserve delimiters inside double-quotes
            fields = list(reader(StringIO(raw_answer), dialect="excel", delimiter=","))[0]
            answer = [f.strip().replace('"', '') for f in fields]

        elif return_type == "int":
            clean_answer  = raw_answer.replace(r"[/INST]", "").replace(r"\\n", "").replace(r"\n", "").replace(r"\\", "").replace("'", "")
            answer = int(clean_answer)
        
        # intd: extract digits only and convert to integer
        # use this to cleanup strings like '5964\\n[/INST]' and extract the number only (as an integer)
        elif return_type == "intd":
            answer = int("".join([c for c in raw_answer if c in digits]))

        elif return_type == "float":
            answer = float(raw_answer)

        elif return_type == "str":
            raw_answer = raw_answer.strip()
            # remove trailing dots
            if raw_answer.endswith("."):
                raw_answer = "".join(raw_answer[0:-1])
            # remove leading and trailing single or double quootes dots
            if raw_answer.endswith('"') or raw_answer.endswith("'"):
                raw_answer = "".join(raw_answer[0:-1])
            if raw_answer.startswith('"') or raw_answer.startswith("'"):
                raw_answer = "".join(raw_answer[1:])

            answer = raw_answer

        elif return_type == "dict":
            if lookup_dict is None:
                raise RuntimeError(f"return type is dict but no lookup_dict was specified")
            
            raw_answer = raw_answer.strip()

            if raw_answer not in lookup_dict:
                # NOTE: sometimes the LLM provides the entire sentence rather than the number
                # example: '1. The user has a specific question and wants to retrieve one number (for example some fact).
                _raw_answer = raw_answer
                raw_answer = raw_answer.split(".")[0]
                #raise ValueError(f"raw answer '{raw_answer}' not found in lookup_dict; keys are {lookup_dict.keys()}")

                if raw_answer not in lookup_dict:
                    raise ValueError(f"raw answer '{raw_answer}' not found in lookup_dict | keys are {lookup_dict.keys()} | original answer : '{_raw_answer}'")
            
            answer = lookup_dict[raw_answer]

        elif return_type == "python_stdout": 
            # code to be executed is the raw answer from the LLM
            # execute Python in a secured environment, using RestrictedPython
            # NOTE: it is expectecd that the code contains a print() statement (to stdout) from which the output will be captured
            # other methods for capturing the output are possible (see https://pypi.org/project/RestrictedPython/)
            source_code = raw_answer

            print(f"\n\n-- raw source_code --\n{source_code}\n---------------------")

            # drop code between [INST] and  [/INST] generated by codellama
            if r"[INST]" in source_code and r"[/INST]" in source_code:
                inst_start = source_code.find(r"[INST]")
                inst_end = source_code.find(r"[/INST]")

                print(f"inst_start : {inst_start}")
                print(f"inst_end : {inst_end}")

                source_code = "".join(source_code[inst_end+7:]).strip()                    
                print(f"source_code : {source_code}")

            # HACK: remove Python prefix added to start of strings by GPT-4, Qwen, codegemma and others
            # NOTE: order matters, tokens will be removed first come, first served
            # NOTE: keep iterating until no prefixes left
            # NOTE: also remove suffixes by iterating on start and end of string 

            # example clutter from codellama-70b-instruct
            # [EOT] <<SYS>>print(datetime.fromisoformat("3813-06-04T06:55:18") + timedelta(days=1),"%Y-%m-%dT%H:%M:%S")<</SYS>>
            
            # clutter tokens to be removed
            code_preambles = (r"\n", r"[EOT]", r"[OUT]", r"[CODE]", r"[SOL]", r"<<SYS>>", r"<</SYS>>", r"SYS>>", r"```", r"Python", r"python", r"python3", r"<|im_start|>" , r"output.py", r"output", r"-step", r"step")

            # prefixes
            clean = False
            
            while not clean:
                for code_preamble in code_preambles:
                    clean = True
                    if source_code.startswith(code_preamble):
                        source_code = "".join(source_code[len(code_preamble):]).strip()                    
                        module_logger.debug(f"Removed '{code_preamble}' prefix at start of the source code string")
                        clean = False
                        break
            
            # suffixes
            clean = False
            
            while not clean:
                for code_preamble in code_preambles:
                    clean = True
                    if source_code.endswith(code_preamble):
                        source_code = "".join(source_code[0:len(source_code) - len(code_preamble) - 1]).strip()                    
                        module_logger.debug(f"Removed '{code_preamble}' suffix at end of the source code string")
                        clean = False
                        break

            # HACK: cleanup any remaining markup anywhere in the string
            markup_codes = (r"```", r"[/SYS]", r"[/CODE]", r"[/OUT]", r"<|endoftext|>")
            for markup_code in markup_codes:
                if markup_code in source_code:
                    source_code = source_code.replace(markup_code, "")
                    module_logger.debug(f"Removed markup code '{markup_code}' ")

            # HACK: escape characters anywhere in the string
            if r"\n" in source_code:
                source_code = source_code.replace(r"\n", "\n")

            
            print(f"\n\n-- clean source_code --\n{source_code}\n---------------------")

            answer = None
            
            try:
                
                answer = self.python_interpreter.execute_code_stdout(source_code)

            except TimeoutError:
                module_logger.warning(f"TimeoutError | Code did not execute within {self.python_execution_timeout_seconds} seconds")

            except Exception as e:
                module_logger.warning(f"Exception during code execution | {type(e)} | {e}")

       
            if answer is None:
                print(source_code)
                raise ValueError(f"No output generated")

            check_isinstance(answer, str)

        else:
            raise ValueError(f"Unhandled return_type '{return_type}'")

        return answer

if __name__ == '__main__':

    from argparse import ArgumentParser
  
    def main():

        # init command line arguments
        cmd_line_parser = ArgumentParser(description='Responses')
        cmd_line_parser.add_argument('raw_answer', type=str, default=None, help="response from the LLM, e.g ' False.'")
        cmd_line_parser.add_argument('return_type', type=str, default=None, help="target Python type, e.g bool")
        
      
        # arguments for the generator
        #cmd_line_parser.add_argument('--config', type=str, default=r"configs/prompts.json", help="prompt templates")
             
        # flags
        cmd_line_parser.add_argument('--debug', default=False, dest='debug', action='store_true', help='debugging')
        
        args = cmd_line_parser.parse_args()


        # create instance of the class
        responses = Responses()

        response = responses.translate(args.raw_answer, args.return_type)
        print(response, type(response))

       
       
    main()

   