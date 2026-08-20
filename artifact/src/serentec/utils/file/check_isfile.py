# -*- coding: utf-8 -*-
"""
check_isfile.py: one-liner to check if a file exists

edward | 2022-11-29

"""

from os import path
from pathlib import Path
from typing import Union

# serentec
from serentec.utils.check_isinstance import check_isinstance
from serentec.exceptions import FileNotFound

def check_isfile(filename : Union[str, Path]):

    """
    check_isfile: check if file exists; raises a FileNotFound exception if not

    :param filename: filename

    """

    check_isinstance(filename, (str, Path))

    if isinstance(filename, Path):
        filename = str(filename)
    
    if not path.isfile(filename):
        raise FileNotFound(f"File not found : {filename}")