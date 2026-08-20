# -*- coding: utf-8 -*-
"""
training_pair.py: a pair for training, comprised of an input and an output

edward | 2021-06-04 | Initial Version
edward | 2021-09-10 | Added the locale since this is required for round robin checks.
edward | 2023-02-02 | Added "aux" for additional info
"""

# -------
# imports
# -------

#from collections import namedtuple

# New in Python 3.6, we can use a class definition with typing.NamedTuple to create a namedtuple
from typing import Any, Optional, NamedTuple

#TrainingPair = namedtuple("TrainingPair", ["input", "output", "locale"])
class TrainingPair(NamedTuple):
    
    input : Any
    output : Any
    locale : Optional[str]
    aux : Any = None        # default value must be specified


    

