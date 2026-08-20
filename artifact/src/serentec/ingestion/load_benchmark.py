"""
load_benchmark.py: load a pre-generated benchmark from file 

NOTES
- benchmark can either be JSON or compressed JSON (gz)

CHANGE LOG
edward | 2024-06-22


BACKLOG

USAGE
python3 load_benchmark.py /tmp/87663153-2a90-44f4-acfa-3a75b6ec3f2b.json.gz


"""


import gzip
from json import loads
from os import path


# serentec
from serentec.utils.check_isinstance import check_isinstance

# logging
from serentec.utils.logger import logger_dl
module_logger = logger_dl.getChild("LoadBenchmark")

# -----
# class
# -----

class LoadBenchmark:

    """
    Load a pre-generated benchmark from file 
    """

    def __init__(self
                 , benchmark_file : str
                 , max_obs : int = None
                 , debug : bool = False
                 , debug2 : bool = False
                 , debug3 : bool = False
                 ):
        
        """
        :param max_obs: maximum obs to read; only applies to JSONL, other 
        """

        self.debug = debug

        self.metadata = None

        # NOTE: benchmark can either be JSON or compressed JSON (gz), or compressed JSONL (.jsonl.gz)
        if not path.isfile(benchmark_file):
            # try addpending 'benchmark.json.gz'
            if path.isfile(f"{benchmark_file}/benchmark.json.gz"):
                module_logger.debug(f"Automatically added 'benchmark.json.gz' to the provided benchmark path '{benchmark_file}'")
                benchmark_file = f"{benchmark_file}/benchmark.json.gz"
            
            elif path.isfile(f"{benchmark_file}/benchmark.jsonl.gz"):
                module_logger.debug(f"Automatically added 'benchmark.jsonl.gz' to the provided benchmark path '{benchmark_file}'")
                benchmark_file = f"{benchmark_file}/benchmark.jsonl.gz"
                
            else:
                raise FileNotFoundError(f"Benchmark file '{benchmark_file}' not found")
                

        self.benchmark_file = benchmark_file

        if benchmark_file.endswith("json.gz"):
            module_logger.debug(f"Reading compressed JSON  | {benchmark_file}...")
            # compressed JSON
            with gzip.open(benchmark_file, 'rb') as f_in:
                raw_json = f_in.read().decode("utf-8")
                benchmark = loads(raw_json)

        elif benchmark_file.endswith("jsonl.gz"):
            # compressed JSONL
            if max_obs is None:
                module_logger.debug(f"Reading full compressed JSONL | {benchmark_file}...")
            else:
                check_isinstance(max_obs, int)
                module_logger.debug(f"Reading at most {max_obs} compressed JSONL | {benchmark_file}...")

            with gzip.open(benchmark_file, "rt", encoding="utf-8") as f_in:
                benchmark = [loads(line) for i, line in enumerate(f_in) if max_obs is None or i < max_obs]

            # read meta, separate file in this case
            meta_file = benchmark_file.replace("jsonl.gz", "meta.json")
            with open(meta_file, "r", encoding="utf-8") as f:
                self.metadata = loads(f.read())
        
        else:
            module_logger.debug("Reading non-compressed file...")
            # assume not compressed
            with open(benchmark_file, "r", encoding='utf8') as json_file:
                benchmark = loads(json_file.read())
        
        assert benchmark is not None
        assert isinstance(benchmark, (dict, list))

        # benchmark can either be a list of observations, or contain meta information
        self.data = benchmark["data"] if isinstance(benchmark, dict) else benchmark
        check_isinstance(self.data, list)
        module_logger.info(f"Benchmark : {benchmark_file} | Num observations : {len(self.data)}")

        # for JSON file, read metadata if availble
        if self.metadata is not None and isinstance(benchmark, dict):
            if "meta" in benchmark:
                self.metadata  = benchmark["meta"]

            elif "args" in benchmark:
                self.metadata  = benchmark["args"]

        if self.debug:
            if self.metadata is not None:
                self.target_field = self.metadata["arguments"].get("target_field", None)
                module_logger.debug(f"benchmark target : {self.target_field}")

                self.input_byte_encoding = self.metadata["arguments"].get("byte_encoding", None)
                module_logger.debug(f"byte encoding for the benchmark inputs : {self.input_byte_encoding}")

            else:
                module_logger.warning(f"no meta data found in benchmark {benchmark_file}")


if __name__ == "__main__":
            
    # data
    from argparse import ArgumentParser
    
    from pandas import DataFrame
    from tabulate import tabulate


    def main():
        parser = ArgumentParser(description='Run the model on N static observations in the benchmarks/ folder')
        parser.add_argument('benchmark', default=None, type=str, help='name of the benchmark; e.g benchmarks/manual.a.json')
    
        parser.add_argument('--debug', default=False, dest='debug', action='store_true', help='debugging')
        parser.add_argument('--debug2', default=False, dest='debug2', action='store_true', help='debugging')
        
        args = parser.parse_args()

        load_benchmark = LoadBenchmark(args.benchmark)

        if load_benchmark.metadata is not None:
            print("\n-- meta data --")
            for k, v in load_benchmark.metadata.items():
                print(k, v)


    main()