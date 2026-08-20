# -*- coding: utf-8 -*-

"""
Setup of the colorlog

edward | 2020-06-29

BACKLOG
- add custom log level "trace" which is below "debug"
"""


import logging
import colorlog

# optional prefix to add to all outgoing names (pre-fixed to %(name)s)
# this is important for two reasons
# 1. easier to pickup was originated by Serentec
# 2. if we use None, then all logging is pickup at the root level, meaning debug statements of all imported libraries get picked up
#    this is really verbose in modules such as matplotlib, parse, hdf5
# edward | 2020-09-13
logger_dl = logging.getLogger("serentec")

BOLD = "\033[1m"
GREEN = "\033[92m"
BLUE = "\033[94m"
RESET = "\033[0m"

# e.g. module_logger.info(f"Change in {entity.value} | {previous} => {BOLD}{GREEN}{new_value}{RESET}")
# e.g. module_logger.info(f"Change in {entity.value} | {previous} => {BOLD}{BLUE}{new_value}{RESET}")

# avoid adding the handler twice
if not logger_dl.handlers:

    logger_dl.setLevel(logging.DEBUG)
    ch = colorlog.StreamHandler()
    ch.setLevel(logging.DEBUG)

    # the list of fields available for logging is in the docs
    # doc: https://docs.python.org/3/library/logging.html

    # format is aligned with guvicorn
    # [2022-01-05 10:19:59,243] [63641] [DEBUG] [serentec.PredictSequenceLite] ...
    #ch.setFormatter(colorlog.ColoredFormatter('%(log_color)s[%(asctime)s] [%(process)d / %(thread)d] [%(levelname)s] [%(name)s] %(message)s'))

    # compact form without [process / thread] and [level] 
    # anyhow, the level can be inferred from the color of the log
    ch.setFormatter(colorlog.ColoredFormatter('%(log_color)s[%(asctime)s] [%(name)s] %(message)s'))

    logger_dl.addHandler(ch)