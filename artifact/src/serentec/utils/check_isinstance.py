# -*- coding: utf-8 -*-
"""
check_isinstance.py: similar to Python isinstance but provides user-friendly output.

Uses isinstance and this the interface is exactly identical.

Type check is compatible with:
- Python built-in types 
- typing types (e.g Dict, List, etc)

raises a SerenTec ArgumentTypeError

edward | 2021-08-17

"""
from inspect import currentframe, getframeinfo
from typing import Any, Union, Tuple

from serentec.exceptions import ArgumentTypeError

def check_isinstance(obj : Any, target_types : Union[Any, Tuple[Any]], none_ok : bool = False, allow_none : bool = False) -> bool:

    """

    check_isinstance: check if obj is of the specified type(s)

    similar to Python isinstance but provides user-friendly output.

    :param obj: a Python object or a 

    :param target_types: a single type, or list-like of types
        n.b: to compare for None, use type(None))

    :param none_ok: optional; if True, None is acceptable type
        default is False (None is not acceptable)

    :param allow_none: optional; alias for none_ok

    """
    
    # alias for none_ok
    none_ok = allow_none if allow_none else none_ok


    # check for None
    if none_ok and obj is None:
        # OK
        pass
    elif not isinstance(obj, target_types):
        # Determine on which line the problem occurred
        # NOTE: no exception was thrown, so we need frameinfo
        # NOTE: we need the prior statement (where the type check failed), not the current one
        frameinfo = getframeinfo(currentframe().f_back)
        raise ArgumentTypeError(f"type error: the value '{str(obj)[0:20]}...' has type '{type(obj)}', expected {target_types} | file : {frameinfo.filename} | line :  {frameinfo.lineno}")