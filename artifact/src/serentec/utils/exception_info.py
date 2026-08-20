# -*- coding: utf-8 -*-
"""
exception_info.py: return information about a recently occurred exception

edward | 2021-11-03

"""

from linecache import checkcache, getline
from sys import exc_info

def exception_info(exception : Exception ) -> dict:

    exc_type, exc_obj, tb = exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    checkcache(filename)
    line = getline(filename, lineno, f.f_globals)

    return { 
        "exception_type" : type(exception).__name__
        , "file" : filename
        , "line" : lineno
        , "statement" : line.strip()
        , "msg" : exc_obj # the actual message
        
        
        }