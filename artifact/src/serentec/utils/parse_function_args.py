# -*- coding: utf-8 -*-
"""
comparator.py: class for comparing values of objects, using different methods: string-wise, float-wise, int, etc

edward | 2024-09-05
"""
from re import search
from typing import Any, Union, Tuple, Dict

# serentec: utils
from serentec.utils.check_isinstance import check_isinstance

# logging
from serentec.utils.logger import logger_dl
module_logger = logger_dl.getChild(f"Comparator")


def parse_function_args(func_string : str) -> Dict:
    """
    Parse a function call string and extract its arguments, e.g. my_func(a, b=1, c=2).

    NOTE: if no argument name is provided (like in the a above), the key is positional => 0
    
    NOTE: drop the quotes in the arguments
        func_str = "llm-as-judge(model=deepseek-r1-32b, prompt=contains-geohash-1)"
    
    :param func_string: A string containing a function call, e.g. "my_func(a, b, c)"
    
    :return: A dictionary mapping argument indices to their trimmed values
    """

    check_isinstance(func_string, str)
    
    match = search(r'\(([^)]*)\)', func_string)
    if not match:
        return {}
    
    args_string = match.group(1)
    if not args_string.strip():
        return {}
    
    result = {}
    for i, arg in enumerate(args_string.split(',')):
        arg = arg.strip()
        
        if '=' in arg:
            key, value = arg.split('=', 1)
            key = key.strip()
            value = value.strip()
        else:
            key = i
            value = arg
        
        # Convert to appropriate type
        try:
            value = int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                pass  # Keep as string
        
        result[key] = value
    
    return result

