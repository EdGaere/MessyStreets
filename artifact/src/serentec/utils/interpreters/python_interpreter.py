# -*- coding: utf-8 -*-
"""
python_interpreter.py: class for executing Python code, if possible in a restricted environment

NOTES
- a default timeout of 60 seconds is implemented to prevent deadlocks, as some code appears to hang indefinitely

DOC
https://pypi.org/project/RestrictedPython/

INSTALL
pip3 install RestrictedPython

edward | 2024-11-14
"""
from contextlib import redirect_stdout
from io import StringIO
from typing import Optional
from warnings import catch_warnings, filterwarnings

# 3rd party
from autopep8 import fix_code, reindent
from RestrictedPython import compile_restricted, safe_globals, PrintCollector # execution of Python in a trusted environment

from serentec.utils.check_isinstance import check_isinstance
from serentec.utils.timeout import timeout

# serentec: logging
from serentec.utils.logger import logger_dl
module_logger = logger_dl.getChild("PythonInterpeter")

class PythonInterpeter:

    def __init__(self, restricted : bool = True, debug : bool = False, debug2: bool = False):
        """
        :param restricted: use restricted environment if possible
        
        """
        self.debug = debug
        self.debug2 = debug2
        self.use_restricted = restricted

        self.restricted_warning_issued = False

        

    @timeout(function_timeout_seconds=60)
    def execute_code_stdout(self, source_code : str) -> Optional[str]:
        """
        Execute the source code using an in-memory Python interpreter. 
        
        IMPORTANT: Output is captured via stdout => a print statement is expected

        RestrictedPython is used if possible.

        :param source_code: Python code to be executed

        :return: produced string if any, else None
        """
        check_isinstance(source_code, str)

        if not self.use_restricted and not self.restricted_warning_issued:
            module_logger.warning(f"Python Interpeter running in non-restricted mode")
            self.restricted_warning_issued = True

        # IMPORTANT: Output is captured via stdout => a print statement is expected
        # BACKLOG: also look for sys.stdout
        if "print" not in source_code:
            raise ValueError(f"No print statement found")
        
        # clean up the source code to PEP standard; re-indent with 4 spaces
        clean_source_code = fix_code(reindent(source_code, 4))

        if self.debug and source_code != clean_source_code:
            module_logger.debug(f"Source code was refactored to PEP8 standard")

        if self.debug2:
            print(f"-- Clean clode (refectored to PEP8) --")
            print(clean_source_code)
            print("--")

        output_buffer = StringIO()

        # generate secure byte code
        # ignore SyntaxWarning: Line None: Prints, but never reads 'printed' variable.
        with catch_warnings():
            filterwarnings("ignore", category=SyntaxWarning)

            if self.use_restricted:
                byte_code = compile_restricted(clean_source_code, '<string>', 'exec')
            else:
                byte_code = compile(clean_source_code, '<string>', 'exec')

            if self.debug:
                module_logger.debug(f"Code compiled | restricted : {self.use_restricted}")

        
        if self.use_restricted:
            print_collector = PrintCollector
            safe_builtins = {}
            safe_builtins["_getattr_"] = getattr
            safe_builtins["__import__"] = __import__
            safe_builtins["_print_"] = print_collector

            restricted_globals = dict(__builtins__= safe_builtins)

            restricted_locals = {}

            exec(byte_code, restricted_globals, restricted_locals)

            # extract output
            # BACKLOG: is there any easier way?
           
            # NOTE: txt is a list with all prints
            answers = restricted_locals['_print'].txt
            if answers is None or len(answers) == 0:
                raise ValueError(f"No output generated | answers : {answers}")
            
            answer = answers[0]


        else:
            with redirect_stdout(output_buffer):
                exec(byte_code)

            # NOTE: print will append a newline => remove it with strip
            answer = output_buffer.getvalue().replace("\n", "")


        return answer

   




