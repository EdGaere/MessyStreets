# -*- coding: utf-8 -*-

"""
global configuration options for phd/experiments

edward | 2024-10-18

"""

from platform import system

from os import makedirs, path

# logging
from serentec.utils.logger import logger_dl
module_logger = logger_dl.getChild("experiment/Config")


class Config:

    def __init__(self):

        # prompt cache
        # MS_CACHE_DIR is set by the artefact to a per-run directory, so replays
        # cannot answer from a cache left behind by a previous run.
        from os import environ
        from tempfile import gettempdir

        cache_dir = environ.get("MS_CACHE_DIR")
        if cache_dir:
            self.cache_dir = cache_dir
        elif system() == r'Darwin':
            self.cache_dir = r"/users/gaeree/data/cache/phd/prompts.cache"
        elif system() == r'Linux':
            self.cache_dir = r"/tmp/cache"
        else:
            self.cache_dir = path.join(gettempdir(), "messy-streets-cache")

        self.cache_max_size_gbytes = 1 # giga-bytes
        makedirs(self.cache_dir, exist_ok=True)

      
