# -*- coding: utf-8 -*-

"""
load_json.py: helper class to load JSON or HJSON files from file

edward | 2024-08-17 | Initial version

USAGE
python3 load_json.py samples/a.json
python3 load_json.py samples/a.hjson

"""
# python lib
from gzip import GzipFile, open as gzip_open
from json import loads, dumps
from os import path
from pathlib import Path
from subprocess import Popen, PIPE
from typing import Any

# 3rd party
from hjson import loads as hloads

# serentec
from serentec.utils.check_isinstance import check_isinstance
from serentec.utils.file.check_isfile import check_isfile

# serentec: logging
from serentec.utils.logger import logger_dl
module_logger = logger_dl.getChild("LoadJSON")

class LoadJSON:

    def __init__(self, debug : bool = False):
        self.debug = debug


    def load(self, filename : str) -> Any:
        """
        Load a JSON or HJSON from file

        :param filename:load file

        :return: Python object (the result of loads)
        """

        # normalize to string
        check_isinstance(filename, (str, Path))
        if isinstance(filename, Path):
            filename = filename.as_posix()

        check_isfile(filename)

        _, extension = path.splitext(path.basename(filename)) 

        if extension == ".json":
            # normal JSON
            with open(filename, "r", encoding='utf8') as json_file:
                contents = loads(json_file.read())


        elif extension == ".hjson":
            # HJSON: human readable JSON
            with open(filename, "r", encoding='utf8') as json_file:
                contents = hloads(json_file.read())
        
        elif extension == ".jsonl":
            # JSON Lines (aka NDJSON (Newline Delimited JSON, extension )
            with open(filename, "r", encoding='utf8') as json_file:
                contents = [loads(line) for line in json_file]

        elif extension == ".gz" and filename.endswith(".jsonl.gz"):
            # compressed JSON Lines (aka NDJSON (Newline Delimited JSON, extension )
            try:
                with gzip_open(filename, "rt", encoding="utf8") as f:
                    contents = [loads(line) for line in f]
            
            except EOFError as e:
                contents = []
                with GzipFile(filename, "rb") as f:
                    while True:
                        try:
                            line = f.readline()
                            if not line:
                                break
                            contents.append(loads(line.decode("utf8")))
                        except (EOFError, OSError):
                            break

                module_logger.warning(f"Malformed GZIP | Recovered {len(contents)} records")
            
            except Exception as e:
                raise e

        else:
            raise ValueError(f"Don't know how to handle file {filename} with extension of type {extension}")


        return contents


if __name__ == '__main__':


    def main():

        from argparse import ArgumentParser

        # parse command line arguments
        cmd_line_parser = ArgumentParser(description='driver for LoadJSON')
        cmd_line_parser.add_argument('filename', type=str, default=None)
        cmd_line_parser.add_argument('--debug', default=False, dest='debug', action='store_true', help='debugging')
        args = cmd_line_parser.parse_args()

        load_json = LoadJSON(debug=args.debug)
        contents = load_json.load(args.filename)

        print(contents)

        assert contents['a'] == 1
        assert contents['b'] == 2
        assert contents['c'] == 3
        print(f"tests passed")


        
    main()