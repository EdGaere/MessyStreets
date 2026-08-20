# -*- coding: utf-8 -*-
"""
comparator.py: class for comparing values of objects, using different methods: string-wise, float-wise, int, etc

# INSTALL
pip3 install ollama

# SETUP LLM-as-judge
# 1. ollama server
export CUDA_VISIBLE_DEVICES=0,2,3
OLLAMA_HOST=127.0.0.1:10000
ollama serve

# 2. load model and keep in memory (else it gets ditched after 5 minutes and will create client timeouts when being reloaded)
export NO_PROXY="localhost,127.0.0.1"
export OLLAMA_HOST=127.0.0.1:10000
curl http://$OLLAMA_HOST/api/generate -d '{
    "model": "qwen3.5:35b"
    , "keep_alive": -1
}'


CREATED
edward | 2024-09-05

USAGE
python3 comparator.py "hello" "hello" --method str
python3 comparator.py "hello" "world" --method str --return-details --debug

LLM AS JUDGE
export NO_PROXY="localhost,127.0.0.1"
export OLLAMA_HOST=127.0.0.1:10000
export NO_PROXY=localhost,127.0.0.1 # required to bypass ETH proxy
python3 comparator.py "hello" "hello" --method "llm(qwen3.5:35b, messy_streets_street_name_predicted_1)"
python3 comparator.py "Rue de la Croix d'Or, 25" "25 Croix d'Or" --method "llm(qwen3.5:35b, messy_streets_street_name_predicted_1)"

"""
from datetime import datetime, date
from decimal import Decimal
from os import environ
from pathlib import Path
from re import compile, IGNORECASE, sub as substitute
from time import perf_counter
from typing import Any, Union, Tuple, Dict, List

# for LLM-as-judge
from httpx import Client as HttpClient

# serentec: utils
from serentec.utils.check_isinstance import check_isinstance
from serentec.utils.parse_function_args import parse_function_args

# serentec: ml
from serentec.ml.llm.prompts import Prompts
from serentec.ml.llm.responses import Responses

# logging
from serentec.utils.logger import logger_dl
module_logger = logger_dl.getChild(f"Comparator")

class Comparator:

    def __init__(self, method : str = "str", return_details : bool = False, debug : bool = False, debug2 : bool = False):
        """

        :param return_details: in addition to the result of the comparison (bool), return evaluation details as a dicft
        
        """
        
        self.method = method
        self.return_details = return_details
        self.debug = debug

        if self.debug:
            module_logger.debug(f"Initialising comparator with method '{method}'")
        

        if method in (r"iso8601-regex-1", r"iso8601-regex-n"):
            # NOTE: non-capturing group to capture the entire ISO-8601 string (and not parts of it)
            # NOTE: minutes and seconds are optional
            # NOTE: we also allow a wildcard at the end to capture microseconds, timezone or other text in the models output
            # NOTE: the first regex to find valid 4-digit year patterns even when embedded in longer digit strings, and return just the valid datetime portion
            # for example, we want "ÌK)2025-01-01T13:14:1" or "02025-01-01T13:14:1 to match
            self.regex_iso8601_1_pattern = r'\d{4}-\d{1,2}-\d{1,2}(?:[T ]\d{1,2}(?::\d{1,2})*[^\s]*?)?'
            self.regex_iso8601_1 = compile(self.regex_iso8601_1_pattern)

            # NOTE: all components are optional
            self.regex_iso8601_1_components_pattern = r"(?P<year>\d{4})?(?:-(?P<month>\d{1,2}))?(?:-(?P<day>\d{1,2}))?(?:[T ](?P<hour>\d{1,2}))?(?::(?P<minute>\d{1,2}))?(?::(?P<second>\d{1,2}))?(?P<suffix>.*)"
            self.regex_iso8601_1_components = compile(self.regex_iso8601_1_components_pattern)
            if self.debug:
                module_logger.debug(f"regex_iso8601_1 compiled")

        elif method in (r"boolean-end-1"):
            # Extract the final yes/no from a model response.
            # METHODOLOGY: allow model to reason over tokens and possibly change it's mdin; e.g. "it's yes... but wait, so it's no" 
            # here we are comparing the last occurence of 'yes' or 'no' in the output sequence
            # the target must be 'yes' or 'no' (case insensitive)
            # NOTE: we don't require a leading word boundary, for cases when model does not put a whitespace between it's thinking and then it's answer
            # see this verbatim example from Claude 4.1 Opus
            # Let me work through this step by step.First, parsing the dates:- Start date: 11:14:21 AM, 18 Jul/2036 (July 18, 2036)- Event date: 11:14:21 AM, 28 Feb/2037 (February 28, 2037)Second, adding 250 days to the start date:- Starting from July 18, 2036- July 2036: 13 days remaining (19-31)- August 2036: 31 days- September 2036: 30 days- October 2036: 31 days- November 2036: 30 days- December 2036: 31 days- January 2037: 31 days- February 2037: 28 days- Running total: 13 + 31 + 30 + 31 + 30 + 31 + 31 + 28 = 225 daysThis takes us to February 28, 2037. We need 250 days total, so we need 25 more days.- March 2037: 25 days- Completion date: March 25, 2037Third, comparing dates:- Completion date: March 25, 2037- Event date: February 28, 2037- March 25, 2037 is after February 28, 2037No
            self.boolean_end_1_pattern = r'(yes|no)\b'
            self.boolean_end_1 = compile(self.boolean_end_1_pattern)
            if self.debug:
                module_logger.debug(f"boolean_end_1 compiled")
        
        elif method in (r"xml-answer-exact-1"):
            # catpure an answer within specific XML tags e.g. "<answer>Congo</answer>"
            # NOTE: allow case insensitive match on tags, e.g. "<ANSWER>Congo</ANSWER>"
            self.regex_xml_answer_1_pattern = r"<answer>(.*?)</answer>"
            self.regex_xml_answer_1 = compile(self.regex_xml_answer_1_pattern, IGNORECASE)

            if self.debug:
                module_logger.debug(f"xml-answer-exact-1 compiled")

        elif method.startswith(r"geohash-regex-1"):
            # EXEPECTED FORMAT
            # geohash-regex-1(precision=1)
            
            
            # METHODOLOGY
            # create one regex for each precision level, since we know ex-ante what precision the task is
            # looking for isolated character groups with negative lookahead/lookbehind for geohash characters instead of generic word boundaries (more precise)
            # Geohash uses a restricted base32 alphabet: Notably excluded: a, i, l, o (to avoid visual confusion with 0, 1, etc.)
            # SOURCE: https://claude.ai/chat/91e2bd62-c8ac-45be-8086-8a1767187263
            
            method_arguments = parse_function_args(method)
            assert "precision" in method_arguments
            self.geohash_precision = method_arguments["precision"]
            assert int(self.geohash_precision) >= 1 and int(self.geohash_precision) <= 10
            
            # NOTE: use word boundary
            r"""
            # METHODOLOGY
            The geohash extraction uses a regular expression pattern to identify valid geohash strings of a specified precision level. Geohashes use a base-32 character set consisting of digits 0–9 and letters b–z, excluding the letters a, i, l, and o to avoid ambiguity with digits.
            The pattern (?<!\w)[0-9b-hjkmnp-z]{n}(?!\w) matches character sequences of exactly n characters from the valid geohash alphabet. The negative lookbehind (?<!\w) ensures the match is not preceded by an alphanumeric character. The negative lookahead (?!\w) ensures the match is not followed by an alphanumeric character. Together, these constraints ensure that only standalone tokens are matched, preventing false positives from substrings within longer words.
            The pattern is compiled with case-insensitive matching to handle both uppercase and lowercase input. All extracted matches are normalized to lowercase for consistency.
            
            SOURCE: https://claude.ai/chat/5c4110e8-c995-4aed-bed4-b5274b6d575c
            """

            pattern = rf'(?<!\w)[0-9b-hjkmnp-z]{{{self.geohash_precision}}}(?!\w)'
            self.geohash_regex = compile(pattern, IGNORECASE)

            if self.debug:
                module_logger.debug(f"geohash-regex-1 compiled for precision {self.geohash_precision}")

   
        
        elif method in ('str', 'istr', 'float', 'int', 'decimal', 'contains', 'iso8601-datepart', 'starts-with', 'istarts-with', 'has_prediction' ):
            # simple methods that do not require initialisation
            pass

        elif method.startswith("left("):
            left_arguments = parse_function_args(method)
            assert len(left_arguments) == 1
            self.left_len = int(left_arguments[0])
            assert self.left_len > 0
            
            if self.debug:
                module_logger.debug(f"{method} | left_len : {self.left_len}")

        elif method.startswith("ileft("):
            left_arguments = parse_function_args(method)
            assert len(left_arguments) == 1
            self.left_len = int(left_arguments[0])
            assert self.left_len > 0
            
            if self.debug:
                module_logger.debug(f"{method} | left_len : {self.left_len}")

        # llm-as-judge
        # e.g. llm(qwen3.5:35b, {component:prompt})
        # NOTE: see instructions at top of file for launching the server
        elif method.startswith("llm("):
            llm_arguments = parse_function_args(method)
            assert len(llm_arguments) == 2
            self.llm_model_name = llm_arguments[0]
            self.llm_model_prompt = llm_arguments[1]
            module_logger.debug(f"LLM-as-Judge | {method} | llm_model_name : {self.llm_model_name} | llm_model_prompt : {self.llm_model_prompt}")

            # prepare LLM client
            if "OLLAMA_HOST" not in environ:
                raise KeyError(f"You need to specify OLLAMA_HOST in the environment")
            ollama_host = environ["OLLAMA_HOST"]
            module_logger.debug(f"ollama_host : {ollama_host}")
            timeout = 240.0
            self.ollama_client = HttpClient(base_url=f"http://{ollama_host}", timeout=timeout)
            module_logger.info(f"Connected to Ollama | {ollama_host} | timeout : {timeout}")
            
            # load PhD prompts file => phd_prompts_filename
            phd_prompts_filename = Path(environ["PYTHONPATH"]) / "phd/configs/prompts.json"
            self.prompts = Prompts(phd_prompts_filename, debug=debug2)
            if self.llm_model_prompt not in self.prompts.templates:
                raise ValueError(f"Prompt template '{self.llm_model_prompt}' not found in prompts | {phd_prompts_filename}")
            
            self.method = "llm-as-judge"

            module_logger.info(f"LLM-as-Judge | {self.method} | LLM ready")

            


        else:
            raise NotImplementedError(f"Comparison method '{method}' not supported")
        
        if self.debug:
            module_logger.debug(f"Comparator created with method {method}")

    
    def matches(self, haystack : str) -> List[str]:
        """
        Returns the number of matches for the given string. Useful for calibration against false positives

        :param haystack: input string to be searched

        :return: matches that pass the regex fiter
        """

        if self.method.startswith(r"geohash-regex-1"):
            return list(set(self.geohash_regex.findall(haystack)))
        
        else:
            raise NotImplementedError(f"Comparison method '{self.method}' not supported")
    
    
    def parse_boolean(self, response: str) -> bool:
        """
        Extract yes/no from LLM response.

        :param response: Raw LLM output.
        :return: True for yes, False for no.
        :raises ValueError: If neither found.
        """
        token = response.strip().rstrip(".,!").split()[0].lower()
        if token == "yes":
            return True
        if token == "no":
            return False
        raise ValueError(f"Unparseable response: {response!r}")

    def __call__(self, val1 : Any, val2 : Any) -> Union[bool, Tuple[bool, Dict]]:
        """
        Compare two values, according to the method defined in self.method

        :param val1: target

        :param val2: prediction

        if method is 'contains', then:
            val1 : needle (string) 
            val2 : haystack (string) 

        :return: either 1- or 2-tuple;
            if self.return_details is False:
                returns a boolean with True if the two values are identical (according to the method defined in self.method), else False
            
            if self.return_details is True, returns a 2-tuple:
                1. returns a boolean with True if the two values are identical (according to the method defined in self.method), else False
                2. an additional dict is returned with evaluation details
            
        """
        if self.method in ('str', 'istr', 'float', 'int', 'decimal'):
            result = self.is_equal(val1, val2)

        elif self.method == 'has_prediction':
            result = val2 is not None, {"lhs" : val1, "rhs" : val2}

        elif self.method.startswith("left("):
            # prediction starts with target; case sensitive
            check_isinstance(val1, str)
            check_isinstance(val2, str)

            val1 = val1[0:self.left_len]
            val2 = val2[0:self.left_len]

            result = val1 == val2, {"lhs" : val1, "rhs" : val2}

        elif self.method.startswith("ileft("):
            # prediction starts with target; case insensitive
            check_isinstance(val1, str)
            check_isinstance(val2, str)

            val1 = val1[0:self.left_len].lower()
            val2 = val2[0:self.left_len].lower()

            result = val1 == val2, {"lhs" : val1, "rhs" : val2}


        elif self.method == "starts-with":
            # prediction starts with target; case sensitive
            check_isinstance(val1, str)
            check_isinstance(val2, str)
            
            result = val2.startswith(val1), {"lhs" : val1, "rhs" : val2}

        elif self.method == "istarts-with":
            # prediction starts with target; case insensitive
            check_isinstance(val1, str)
            check_isinstance(val2, str)

            val1 = val1.lower()
            val2 = val2.lower()
            
            result = val2.startswith(val1), {"lhs" : val1, "rhs" : val2}
        
        elif self.method == "contains":
            check_isinstance(val1, str)
            check_isinstance(val2, str)
            
            result = val1 in val2, {"lhs" : val1, "rhs" : val2}

        elif self.method == "boolean-end-1":
            # METHODOLOGY: allow model to reason over tokens and possibly change it's mdin; e.g. "it's yes... but wait, so it's no" 
            # here we are comparing the last occurence of 'yes' or 'no' in the output sequence
            # the target must be 'yes' or 'no' (case insensitive)
            check_isinstance(val1, str)
            check_isinstance(val2, str)
            val1 = val1.lower()
            val2 = val2.lower()
            assert val1 in ('yes', 'no')
            matches = self.boolean_end_1.findall(val2)
            parsed_answer = matches[-1] if matches else None
            result = val1 == parsed_answer, {"lhs" : val1, "rhs" : parsed_answer}

        elif self.method == "llm-as-judge":
            # render the prompt
            prompt, prompt_aux = self.prompts.generate(template_name=self.llm_model_prompt, input=val2, target=val1)
            module_logger.debug(f"prompt : {prompt} | {prompt_aux}")

            t0 = perf_counter()
            resp = self.ollama_client.post(
                    "/api/generate"
                    , json={"model": self.llm_model_name, "prompt": prompt, "stream": False, **prompt_aux}
                    , headers={"Content-Type": "application/json"}
                )
            t1 = perf_counter()
            elapsed_milliseconds = 1000.0 * (t1 - t0)
            resp.raise_for_status()
            llm_response = resp.json()["response"]
            module_logger.debug(f"llm_response : {llm_response} | {round(elapsed_milliseconds)} ms")

            # parse the response => bool
            llm_eval = self.parse_boolean(llm_response)
            check_isinstance(llm_eval, bool)

            result = llm_eval, None
        
        elif self.method == "xml-answer-exact-1":
            # xml-answer-exact-1: catpure an answer within specific XML tags e.g. "<answer>Congo</answer>""
            result = self.xml_answer_exact_1(val1, val2)
        
        elif self.method == "iso8601-regex-1":
            # For PhD DATETIME benchmark Paper 1 (v2). Find *first* matching ISO-8601 like string using regex and groups to extract components
            result = self.iso8601_regex_1(val1, val2)

        elif self.method == "iso8601-regex-n":
            # For PhD DATETIME benchmark Paper 1 (v2). Find *any* matching ISO-8601 like string using regex and groups to extract components
            result = self.iso8601_regex_n(val1, val2)

        elif self.method == "iso8601":
            """
            Simplified ISO 8601 without microseconds and without timezone; e.g 7942-01-22T23:41:06
            """
            result = self.iso8601(val1, val2)
        
        elif self.method == "iso8601-datepart":
            """
            ISO 8601 comparison comparing the date only; date.fromisoformat expects strings of exactly length 10
            """
            result = self.iso8601_datepart(val1, val2)

        elif self.method.startswith(r"geohash-regex-1"):
            #match = self.geohash_regex.search(val2)
            #print(f"val1 : {val1} | val2 : {val2} | match : {match}")
            matches = [m for m in self.geohash_regex.findall(val2)]
            matches_lc = [m.lower() for m in self.geohash_regex.findall(val2)]

            if val1.lower() in matches_lc:
                matched_idx = matches_lc.index(val1.lower())
                result = (True, {"lhs" : str(val1), "rhs" : matches[matched_idx], "matches" : matches})
            else:
                result = (False, {"lhs" : str(val1), "rhs" : None, "matches" : matches})
            
        else:
            raise ValueError(f"Unhandled method '{self.method }'")
        
        # NOTE: all comparators to return a 2-tuple
        assert len(result) == 2
        return result[0] if not self.return_details else result

    def iso8601_datepart(self, val1 : Any, val2 : Any) -> Tuple[bool, Dict]:
        """
        ISO 8601 comparison comparing the date only; date.fromisoformat expects strings of exactly length 10
        """

        # crop strings to max length 10 to remove any time, microsceonds and timezone informatin
        val1 = val1[0:10]
        val2 = val2[0:10]

        dt2 = None

        # val1 is the target value: it must be convertible to a datetime
        dt1 = date.fromisoformat(val1)

        # val2 is the prediction: it should be convertible to a datetime
        try:
            dt2 = date.fromisoformat(val2)
        except:
            return False, {"lhs" : dt1, "rhs" : dt2}
        
        # element-wise copmparison
        if  dt1.year == dt2.year and dt1.month == dt2.month and dt1.day == dt2.day:
            return True, {"lhs" : dt1, "rhs" : dt2}
        
        return False, {"lhs" : dt1, "rhs" : dt2}

    def pad_iso(self, s):
        """Pad single-digit components to two digits.

        What it does: Finds any single digit that sits between ISO-8601 separators (hyphen, T, colon, or space) or before end of string, and prepends a zero. So 1000-1-1T0:0:0 becomes 1000-01-01T00:00:00.
        
        What it does not do: It won't pad the year (it's 4 digits, never a single digit). It won't pad a single digit at the very start of the string (no preceding separator). It won't touch multi-digit numbers like 12 or 31 — the lookahead/lookbehind require separators on both sides, so digits adjacent to other digits are left alone.
        
        
        """
        return substitute(r'(?<=[-T: ])(\d)(?=[-T: ]|$)', r'0\1', s)
    
    def iso8601(self, val1 : Any, val2 : Any) -> Tuple[bool, Dict]:
        """
        Simplified ISO 8601 without microseconds and without timezone; e.g 7942-01-22T23:41:06

        Compares the following components:
        * year
        * month
        * day
        * hour
        * minute
        * second

        :param val1: target

        :param val2: prediction
        """

        check_isinstance(val1, str)
        check_isinstance(val2, str)
        dt2 = None

        # val1 is the target value: it must be convertible to a datetime
        # NOTE: pad digits because fromisoformat does not accept non-padded values like '1000-1-1T0:0:1'
        dt1 = datetime.fromisoformat(self.pad_iso(val1))

        # val2 is the prediction: it should be convertible to a datetime
        try:
            # NOTE: pad digits because fromisoformat does not accept non-padded values like '1000-1-1T0:0:1'
            dt2 = datetime.fromisoformat(self.pad_iso(val2))
        except:
            return False, {"lhs" : dt1, "rhs" : dt2}
        
        # element-wise comparison, without microseconds and without timezone
        if  dt1.year == dt2.year and dt1.month == dt2.month and dt1.day == dt2.day and dt1.hour == dt2.hour and dt1.minute == dt2.minute and dt1.second == dt2.second:
            return True, {"lhs" : dt1, "rhs" : dt2}
        
        return False, {"lhs" : dt1, "rhs" : dt2}
    
    def xml_answer_exact_1(self, target_sequence : Any, model_output : Any, first_match_only : bool = True) -> Tuple[bool, Dict]:
        """
        xml-answer-exact-1: catpure an answer within specific XML tags e.g. "<answer>Congo</answer>""
        
        :param target_sequence: target

        :param model_output: prediction

        :param first_match_only: if True, only the first XML match is evaluated
            if Falwe, any answer within <answer></answer> are evaluated

        :return: 2-tuple;
            1. True if both values are identical
            2. dict with intermedidate calculations
        """

        check_isinstance(target_sequence, str)
        check_isinstance(model_output, str)
        check_isinstance(first_match_only, bool)

        if first_match_only is False:
            raise NotImplementedError()

        details = {
                    "num_matches" : None
                    , "matches" : []
                   , "first_match" : None
        }

        # extract XML answer from prediction
        matches = self.regex_xml_answer_1.findall(model_output)
        details["num_matches"] = len(matches)

        if len(matches) == 0:
            # no matches
            if self.debug:
                module_logger.warning(f"No XML answers found in {model_output}")
            return False, details
        
        elif len(matches) == 1:
            module_logger.debug(f"One XML match found")

        else:

            raise NotImplementedError(f"multiple answers found | {len(matches)}")

        for match_idx, raw_match in enumerate(matches):
            module_logger.debug(f"evluating match #{match_idx+1} of {len(matches)} : {raw_match}")

            match = raw_match.strip()

            if match_idx == 0:
                details["first_match"] = match

            details["matches"].append(match)
        
            if match == target_sequence:
                return True, details
        
        
        return False, details
    
    def iso8601_regex_1(self, target_iso8601 : Any, model_output : Any) -> Tuple[bool, Dict]:
        """
        For PhD DATETIME benchmark Paper 1 (v2). Find *FIRST* matching ISO-8601 like string using regex and groups to extract components

        :param val1: target

        :param val2: prediction

        :return: 2-tuple;
            1. True if both values are identical
            2. dict with intermedidate calculations
        """

        return self.iso8601_regex_n(target_iso8601=target_iso8601, model_output=model_output, first_match_only=True )
    

    def iso8601_regex_n(self, target_iso8601 : Any, model_output : Any, first_match_only : bool = False) -> Tuple[bool, Dict]:
        """
        For PhD DATETIME benchmark Paper 1 (v2). Find *ANY* matching ISO-8601 like string using regex and groups to extract components

        :param val1: target

        :param val2: prediction

        :return: 2-tuple;
            1. True if both values are identical
            2. dict with intermedidate calculations
        """

        details = {
                    "num_matches" : None
                    , "matches" : []
                   , "first_match" : None
                   , "components" : None
                   , "lhs" : target_iso8601
                   , "rhs" : None
                   }

        if self.debug:
            module_logger.debug(f"iso8601_regex_1 | target_iso8601 : {target_iso8601} | model_output : {model_output}")

        # find first matching ISO-8601 like string using regex and groups to extract components
        matches = self.regex_iso8601_1.findall(model_output)

        details["num_matches"] = len(matches)

        if len(matches) == 0:
            # no matches
            if self.debug:
                module_logger.warning(f"No ISO-8601 matches found {model_output}")
            return False, details
        
        elif len(matches) > 1 and first_match_only:
            # multiple matches, only taking the first one
            module_logger.warning(f"{len(matches)} ISO-8601 matches found, only taking first match")
        
        # get first match
        for match_idx, match in enumerate(matches):
            module_logger.debug(f"evluating match #{match_idx+1} of {len(matches)} : {match}")
            
            if match_idx == 0:
                details["first_match"] = match

            details["matches"].append(match)

            # NOTE: search: looks anywhere in the string
            components_result = self.regex_iso8601_1_components.search(match)

            if components_result is None: 
                module_logger.warning(f"No components found in match #{match_idx+1} '{match}'")

            components = components_result.groupdict()

            if self.debug:
                module_logger.debug(f"{len(components)} raw regex component matches")
                for k, v in components.items():
                    module_logger.debug(f"{k} : {v}")

            # cast all components to integer
            # NOTE: skip None elements => some elements will be missing from components dict
            # NOTE: skip any trailing text after the date, which is grouped together in the 'suffix' group
            components = {k : int(v) for k, v in components.items() if k != "suffix" and v is not None}

            details["components"] = components

            if self.debug:
                module_logger.debug(f"{len(components)} matched components")
                for k, v in components.items():
                    module_logger.debug(f"{k} : {v}")


            # build ISO-8601 from groups; missing elements components will use datetime contructor defaults
            #print(f"components : {components}")
            predicted_iso8601 = datetime(**components)
            details["rhs"] = str(predicted_iso8601)

            #print(f"predicted_iso8601 : {predicted_iso8601}")

            # compare elements
            # iso8601 : Simplified ISO 8601 without microseconds and without timezone; e.g 7942-01-22T23:41:06
            is_equal = self.iso8601(target_iso8601, predicted_iso8601.isoformat())[0]

            if is_equal:
                return True, details
            
            if first_match_only:
                # stop iterating => will return False
                break

            # keep trying, evaluate remaining ISO-8601 strings
        
        # not equal
        return False, details

    def is_equal(self, val1 : Any, val2 : Any) -> Tuple[bool, Dict]:
        """
        compare two values using the method specifed specified in the constructor

        :return: True if both values are identical
        
        """
        

        if self.method == "str":
            return str(val1) == str(val2), {"lhs" : str(val1), "rhs" : str(val2)}
        
        elif self.method == "istr":
            return str(val1).lower() == str(val2).lower(), {"lhs" : str(val1), "rhs" : str(val2)}
        
        elif self.method == "float":
            return float(val1) == float(val2), {"lhs" : float(val1), "rhs" : float(val2)}
        
        elif self.method == "decimal":
            return Decimal(val1) == Decimal(val2), {"lhs" : Decimal(val1), "rhs" : Decimal(val2)}
        
        elif self.method == "int":
            return int(val1) == int(val2), {"lhs" : int(val1), "rhs" : int(val2)}
        
        else:
            raise ValueError(f"Unsupported comparison method '{self.method}'")
        





if __name__ == "__main__":
    

    from typer import Typer, Option
    from comparator import Comparator

    app = Typer()

    @app.command()
    def compare(
        val1: str
        , val2: str
        , method: str = Option("str", help="Comparison method")
        , return_details: bool = Option(False, help="Return detailed comparison info")
        , debug: bool = Option(False, help="Enable debug output")
    ):
        """
        Compare two values using the specified method.

        :param val1: target
        :param val2: prediction
        """
        c = Comparator(
            method=method
            , return_details=return_details
            , debug=debug
        )
        result = c(val1, val2)

        if return_details:
            match, details = result
            print(f"Match: {match}")
            for k, v in details.items():
                print(f"  {k}: {v}")
        else:
            print(f"Match: {result}")

    app()