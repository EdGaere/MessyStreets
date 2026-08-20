# -*- coding: utf-8 -*-
"""
messy_streets/v0/generators/v2: Generate addresses based on OA+OSD with augmented country names

BASE
v1

MODIFICATIONS
1. augment country name for level1 and level2
2. removed 'nan' and other missing values that appeared in the ouptuts
3. missing values harmonised to "NULL" (previously was "")
4. fix corrupted encoding characters in the input sequences; e.g. "Incheon/\uc1a1\ubbf8\ub85c20\ubc88\uae38//KR" 

OUTPUTS
- country           : country as displayed; NULL if missing
                      => extract model

- source(country)   : country as specified in the source, regardless if the value is visible in the output; NULL if missing in the source
                      => predict country, region, street

- has(country)      : if the component is displayed, e.g. 'country', generate 'Yes', else 'No'
                      components : country, locality
                      => for span extraction, no point extracting if nothing to extract
                      
- surface_form_1    : the same canonical address as the input but in a different surface form 
                       => train an embedding model

- geohash(x)        : geohash at specified precision level, 1 to 10


EXAMPLES
0                                         横越大滝線, 147  Japan
1   Keysville-Mary Knoll Lane, 70--United States of America
2          North Broadway Way, 148  Portland  United States
3   Springfield,Rubsam Street, 153,United States of America
4                     3 Chemin des Friches..French Republic
..                                                      ...
95    Ennis 89 Westfields Ennis Municipal District  Ireland
96                 Hunter Road, 66765#La Grande#OR#97850#US
97                             HELEN AVENUE, 2001/TX//78333
98                     KOORLONG|TWENTY THIRD STREET, 259|AU
99                                  |CL POLAN, 8||45100|ESP


BACKLOG
* span extraction
* add person's name => full postal address

INSTALL
pip3 install ftfy

SETUP
export MESSY_STEETS_DATA_DIR=/local/home/gaeree/data/messy_streets/v0

USAGE
python3 v2.py geohash7 10

python3 v2.py geohash7 10 --batch_size 100 --debug --stop_on_error --schemas level2

# raw WDC addresses with seed for reproducibility
python3 v2.py geohash6 10 --batch_size 100 --db wdc --schemas basic --seed 42

# WDC using the street of the paired address in OA or OSD
python3 v2.py geohash6 10 --batch_size 100 --db hq_10000 --schemas paired_street --seed 42

# has(x): is a component present
python3 v2.py 'has(country)' 10 --batch_size 100 --remove 0.1
python3 v2.py 'has(address)' 10 --batch_size 100 --remove 0.1

# standardisation
python3 v2.py 'standard_format_1' 10 --batch_size 100 --remove 0.1 --schemas level2

# use pre-existing benchmark config
python3 v2.py geohash7 10 --config messy_streets/release_gold_geohash1_1 --debug --stop_on_error

CREATED
edward | 2026-05-15
"""

# -------
# imports
# -------

from asyncio import run as async_run
from collections import defaultdict
from datetime import datetime, timedelta
from gzip import open as gzip_open
from hashlib import md5
from io import BytesIO
from json import dumps, loads, JSONDecodeError
from locale import getdefaultlocale
from os import environ, path
from pathlib import Path
from random import randint, random, choice
from re import compile, search
from socket import gethostname
from tarfile import open as tar_open
from time import perf_counter
from traceback import print_exception
from typing import Any, List, Set, Dict, Tuple, Optional, Union, Iterable, Iterator

# data
from duckdb import connect
from ftfy import fix_text
from pandas import read_csv, DataFrame, isna, to_numeric, set_option
from pycountry import countries
from pygeohash import encode as geohash

# serentec
from serentec.config import Config as SerentecBaseConfig
from serentec.ml.config import Config
from serentec.ml.training_pair import TrainingPair
from serentec.utils.check_isinstance import check_isinstance
from serentec.utils.json.load_json import LoadJSON
from serentec.utils.parse_function_args import parse_function_args

# serentec: logging
from serentec.utils.logger import logger_dl
module_logger = logger_dl.getChild("messy_streets/v2")

# -----
# class
# -----

# METHODOLOGY: find rogue JSON objects that contain WDC language variations
# EXAMPLES
#   {fr":"Buggenhout", "nl":"Buggenhout"}"
#   {'de': 'Genf', 'fr': 'Genève'}
RE_JSON_OBJ = compile(r'\{[^{}]*:[^{}]*\}')
RE_FIX_KEY = compile(r'(\{|,)\s*(\w+)":')

class Generate:

    """
    Generate a sample of dates for training
    """

    def __init__(self, debug : bool = False, debug2 : bool = False):

        self.debug = debug
        self.debug2 = debug2

        self.missing_value_tokens = SerentecBaseConfig().default_missing_data_tokens

        self.data_path = environ["MESSY_STEETS_DATA_DIR"]
        module_logger.debug(f"MESSY_STEETS_DATA_DIR : {self.data_path}")
        if not path.exists(self.data_path):
            raise FileNotFoundError(f"MESSY_STEETS_DATA_DIR | {self.data_path} not found")
        
        # the core datalake type being generated (see Config.core_pandas_type_map)
        self.model_name = "STR"

        # for NER (named entity resolution)
        self.entity = "address"
        
        # get generators
        self.config = Config()
        self.addresses = None

        self.not_present = None
        self.not_present_str = "#N/A"

        # formats are inspired by dates/date/generate20.py
        # METHODOLOGY: for ablations, we can control which separators
        self.separators = {
            "basic" : [" "]
            , "level1" : [" ", ",", ";"]
            , "level2" : [' ', '.', '/', '-', '#', '|', ',']
        }

        self.separators["basic_no_country"] = self.separators["basic"]
        self.separators["street_only"] = self.separators["basic"]
        self.separators["street_country"] = self.separators["basic"]
        self.separators["level2_no_country"] = self.separators["level2"]
        self.separators["paired_street"] = self.separators["basic"]
        self.separators["all"] = self.separators["level2"]

        # for street augmentation to address (schema "level2")
        self.road_suffixes = ["", "Road", "Street", "St", "Rd", "Ave", "Blvd", "Lane", "Dr", "Way"]

        # NOTE: map the possible components from schema.org to tokens in the formatting strings
        # set to None if no component exists
        # METHODOLOGY: there is no city in the WDC dataset, only addressLocality which is kept as is
        # NOTE: need one mapping per source
        self.possible_components = {
            "wdc" : {
                "streetAddress" : "street"
                , "postalCode" : "postcode"
                , "addressLocality" : "locality"
                , "addressRegion" : "region"
                , "addressCountry" : "country"
                , "postOfficeBoxNumber" : "pobox"
            }

            , "osd" : {
                "street_name" : "street"
                , "postal_code" : "postcode"
                , "city" : "locality"
                , "region" : "region"
                , "country" : "country"
                , 

            }

            , "oa" : {
                "street" : "street"
                , "postcode" : "postcode"
                , "city" : "locality"
                , "region" : "region"
                , "country" : "country"
            }

        }

        # HACK: paired addresses share the wdc schema
        self.possible_components["hq_10000"] = self.possible_components["wdc"]
        self.possible_components["hq_1000"] = self.possible_components["wdc"]
        self.possible_components["mq_10000"] = self.possible_components["wdc"]
        self.possible_components["mq_1000"] = self.possible_components["wdc"]
        self.possible_components["lq_10000"] = self.possible_components["wdc"]
        self.possible_components["lq_1000"] = self.possible_components["wdc"]

        # HACK: for augmentation
        for k, v in self.possible_components.items():
            v["address"] = "address"

        # METHODOLOGY: for ablations, we can control which formats are generated
        self.format_spec = {

                            "basic" : [
                               # all components possible
                               # METHODOLOGY: exactly the same as address/openaddresses/generators/v1.py
                                # except with no city: no city in the WDC dataset, only addressLocality which is kept as is
                                r"{street}{separator}{locality}{separator}{region}{separator}{postcode}{separator}{country}"
                            ], 

                            "street_only" : [r"{street}"],

                            "street_country" : [r"{street}{separator}{country}"],

                            "basic_no_country" : [ 
                               # basic - country
                                r"{street}{separator}{locality}{separator}{region}{separator}{postcode}"
                            ],

                            "address" : [
                               # using the rendered address
                                r"{address}{separator}{locality}{separator}{region}{separator}{postcode}{separator}{country}"
                            ], 

                            "paired_street" : [
                               # all components possible but uses the street from the source
                                r"{paired_street}{separator}{locality}{separator}{region}{separator}{postcode}{separator}{country}"
                            ], 
                            
                            
                            # METHODOLOGY: exactly the same as address/openaddresses/generators/v1.py
                            # except with no city: no city in the WDC dataset, only addressLocality which is kept as is
                            "level1" : [

                                # variations, always with a street
                                r"{street}{separator}{locality}{separator}{region}{separator}{postcode}{separator}{country}"
                                
                                , r"{street}{separator}{postcode}{separator}{country}"
                                , r"{street}{separator}{locality}{separator}{country}"
                                , r"{street}{separator}{region}{separator}{country}"

                                , r"{street}{separator}{locality}{separator}{postcode}{separator}{country}"
                                , r"{street}{separator}{locality}{separator}{region}{separator}{postcode}{separator}{country}"

                                , r"{street}{separator}{region}{separator}{postcode}{separator}{country}"
                                , r"{street}{separator}{region}{separator}{country}"
                                , r"{street}{separator}{region}{separator}{locality}{separator}{postcode}{separator}{country}"


                                # no country
                                , r"{street}{separator}{locality}{separator}{region}{separator}{postcode}"
                                
                                , r"{street}{separator}{postcode}"
                                , r"{street}{separator}{locality}"
                                , r"{street}{separator}{region}"

                                , r"{street}{separator}{locality}{separator}{postcode}"
                                , r"{street}{separator}{locality}"
                                , r"{street}{separator}{locality}{separator}{region}{separator}{postcode}"

                                , r"{street}{separator}{region}{separator}{postcode}"
                                , r"{street}{separator}{region}"
                                , r"{street}{separator}{region}{separator}{locality}{separator}{postcode}"

                            ]

                            # level2 : the 'street' component is replaced with an 'address' that may contain additional building information
                            # such as street number, building name, etc
                            , "level2" : [

                                # variations, always with a street
                                r"{address}{separator}{locality}{separator}{region}{separator}{postcode}{separator}{country}"
                                
                                , r"{address}{separator}{postcode}{separator}{country}"
                                , r"{address}{separator}{locality}{separator}{country}"
                                , r"{address}{separator}{region}{separator}{country}"

                                , r"{address}{separator}{locality}{separator}{postcode}{separator}{country}"
                                , r"{address}{separator}{locality}{separator}{region}{separator}{postcode}{separator}{country}"

                                , r"{address}{separator}{region}{separator}{postcode}{separator}{country}"
                                , r"{address}{separator}{region}{separator}{country}"
                                , r"{address}{separator}{region}{separator}{locality}{separator}{postcode}{separator}{country}"

                                # variation: address is second
                                , r"{locality}{separator}{address}{separator}{region}{separator}{postcode}{separator}{country}"

                                , r"{postcode}{separator}{address}{separator}{country}"
                                , r"{locality}{separator}{address}{separator}{country}"
                                , r"{region}{separator}{address}{separator}{country}"

                                , r"{locality}{separator}{address}{separator}{postcode}{separator}{country}"
                                , r"{locality}{separator}{address}{separator}{region}{separator}{postcode}{separator}{country}"

                                , r"{region}{separator}{address}{separator}{postcode}{separator}{country}"
                                , r"{region}{separator}{address}{separator}{country}"
                                , r"{region}{separator}{address}{separator}{locality}{separator}{postcode}{separator}{country}"


                                # no country
                                , r"{address}{separator}{locality}{separator}{region}{separator}{postcode}"
                                
                                , r"{address}{separator}{postcode}"
                                , r"{address}{separator}{locality}"
                                , r"{address}{separator}{region}"

                                , r"{address}{separator}{locality}{separator}{postcode}"
                                , r"{address}{separator}{locality}"
                                , r"{address}{separator}{locality}{separator}{region}{separator}{postcode}"

                                , r"{address}{separator}{region}{separator}{postcode}"
                                , r"{address}{separator}{region}"
                                , r"{address}{separator}{region}{separator}{locality}{separator}{postcode}"

                            ]

                            # level2_no_country : level2 without the country component
                            , "level2_no_country" : [
                                r"{address}{separator}{locality}{separator}{region}{separator}{postcode}"
                                , r"{locality}{separator}{address}{separator}{region}{separator}{postcode}"
                                , r"{postcode}{separator}{address}"
                                , r"{locality}{separator}{address}"
                                , r"{region}{separator}{address}"
                                , r"{locality}{separator}{address}{separator}{postcode}"
                                , r"{address}{separator}{postcode}"
                                , r"{address}{separator}{locality}"
                                , r"{address}{separator}{region}"
                                , r"{address}{separator}{locality}{separator}{postcode}"
                                , r"{address}{separator}{region}{separator}{postcode}"
                                , r"{address}{separator}{region}{separator}{locality}{separator}{postcode}"

                            ]


        }

        # keep track of displayed warnings to not show them twice
        self.warnings = set()

        self.addresses : List[Dict] = None
       
    async def close(self):
        pass
    
    
    def field_map(self, source: str, target: str) -> Dict[str, str]:
        """
        Build a direct field name mapping from source schema to target schema,
        via the shared common vocabulary.

        :param source: source schema key, e.g. "osd", "oa", "wdc"
        :param target: target schema key, e.g. "wdc", "osd", "oa"
        :return: dict mapping source field names to target field names
        """
        src = self.possible_components[source]   # source_field → common
        tgt = self.possible_components[target]   # target_field → common
        tgt_inv = {v: k for k, v in tgt.items()}  # common → target_field
        return {sf: tgt_inv[common] for sf, common in src.items() if common in tgt_inv}

    def augment_country(self, country_code: str) -> str:
        """Return a random surface form of the given country.

        Looks up the country by ISO alpha-2 or alpha-3 code and
        returns one of: alpha_2, alpha_3, English name, official
        name, common name, or a locale translation (where available).
        If the code is not recognised, returns the input verbatim.

        BACKLOG
        * support locale as an argument

        :param country_code: ISO 3166-1 alpha-2 or alpha-3 code.
        
        :return: A randomly chosen surface form of the country.
        """
        
        code = country_code.strip()

        if len(code) == 2:
            country = countries.get(alpha_2=code.upper())
        elif len(code) == 3:
            country = countries.get(alpha_3=code.upper())
        else:
            return country_code

        if country is None:
            return country_code

        forms = [country.alpha_2, country.alpha_3, country.name]
        for attr in ("official_name", "common_name"):
            val = getattr(country, attr, None)
            if val is not None:
                forms.append(val)

        # locale translations: de, fr, pt, es, it, ja, zh, ...
        for loc in ("de", "fr", "pt", "es", "it", "nl", "ja", "zh", "ar", "ru"):
            try:
                translated = country.name  # fallback
                loc_countries = countries._get_locale(loc)
                translated = loc_countries.get(country.alpha_2, country.name)
                if translated != country.name:
                    forms.append(translated)
            except Exception:
                continue

        return choice(forms)

    
    def augment_street(self
                , street: str
                , number_min: str | None = None
                , number_max: str | None = None
                , add_suffix_prob: float = 0.3
            ) -> str:
        """
        Augment a bare street name with a building number and optional suffix.

        :param street: Bare street name, e.g. 'Viborgvej'.
        :param number_min: Lower bound of known number range, e.g. '151.0'.
        :param number_max: Upper bound of known number range, e.g. '454.0'.
        :param add_suffix_prob: Probability of appending a road suffix.
        :return: Augmented address string, e.g. '273 Viborgvej'.
        """
        number = randint(1, 200)
        
        try:
            if number_min and number_max:
                lo = int(float(number_min))
                hi = int(float(number_max))
                number = randint(lo, hi)
        except:
            pass

        suffix = f" {choice(self.road_suffixes[1:])}" if random() < add_suffix_prob else ""
        
        # do not add a number if there is already one
        if search(r'\d', street):
            return  f"{street}{suffix}"
        else:
            return choice((f"{number} {street}{suffix}", f"{street}{suffix} {number}", f"{street}{suffix}, {number}"))

    def render(self,
                address : Dict
                , source : str
                , format_spec : str
                , separators : List[str]
                , schemas : List[str] = None
                , remove_random_component_probability : float = None
                , show_components : Set[str] = None
               ) -> Tuple[str, Dict, Set]:
        """
        :param address: address to be rendered

        :param source: where the address comes from, e.g OA, OSD

        :param format_spec: format template to apply

        :param separators: separators to choose from

        :param remove_random_component_probability: randomly remove components; default: do not remove any

        :param show_components: optional; if specified, only show these components

        :return: 3-tuple:
            1. rendered input sequence
            2. additional information (aux)
            3. visible_components

        """
        
        # BACKLOG: this should be done at the end => remove contiguous separators if a component was not rendered, e.g. {separator}{separator}
        while r"{separator}" in format_spec:
            # choose a different separator for each instance
            _separator_character = choice(separators)
            # NOTE: The third parameter is the maximum number of occurrences that you want to replace => replace one at a time
            format_spec = format_spec.replace(r"{separator}", _separator_character, 1)

        if self.debug:
            module_logger.debug(f"format_spec with separators resolved : {format_spec}")

        # generate input string
        input_str = format_spec
        token_values = {} # mapping from standardised component name => rendered value, e.g "address" => "4 Wetterburg"
        visible_components = set()
        
        for component_name, possible_component in self.possible_components[source].items():
            if '{' + possible_component + '}' in format_spec:
                
                # only render the component if it's not None (we have a mapping) and it's part of the output compoonents (if specified)
                if possible_component is not None:
                    
                    if remove_random_component_probability is not None and random() < remove_random_component_probability:
                        # remove from the input str
                        
                        if self.debug:
                            module_logger.warning(f"Removing component '{possible_component}' ({component_name}) | {address}")
                        
                        possible_component_value = "NULL"

                        
                        # BACKLOG: should also remove the adjacent separator
                        input_str = input_str.replace('{' + possible_component + '}', "")
                    
                    elif show_components is not None and possible_component not in show_components:
                        # remove from the input str
                        possible_component_value = "NULL"                        
                        input_str = input_str.replace('{' + possible_component + '}', "")

                    else:
                        
                        # lookup value in random address from OpenStreetMap
                        if component_name in address:
                            possible_component_value = address[component_name]

                            # augment country (if possible), and only for schemas with augmentation
                            if ("level1" in schemas or "level2" in schemas) and possible_component == "country":
                                country_code = address[component_name]
                                possible_component_value = self.augment_country(country_code)
                            else:

                                # METHODOLOGY: handle elements that have multiple versions, e.g. locale {fr\":\"Oostakker\", \"nl\":\"Oostakker\"}\"
                                # fallback to a random element if the dict is parseable or the raw unchanged value itself otherwise
                                try:
                                    match = RE_JSON_OBJ.search(str(possible_component_value))
                                    
                                    if match:
                                        fixed = RE_FIX_KEY.sub(r'\1"\2":', match.group())

                                        try:
                                            # try to caast to a dcit
                                            _d = loads(fixed)
                                            check_isinstance(_d, dict)

                                            # choose a random value
                                            # BACKLOG: filter for a specific locale if possible
                                            possible_component_value = choice(list(_d.values()))
                                            
                                            if self.debug:
                                                module_logger.debug(f"Serialised JSON | '{component_name}' | {_d} | selected : {possible_component_value}")
                                            

                                        except JSONDecodeError:
                                            # fallback: leave as is
                                            module_logger.warning(f"JSON fallback | {e} | component_name : {component_name} | possible_component_value : {possible_component_value} | {type(possible_component_value)}")
                                
                                except TypeError as e:
                                    module_logger.error(f"JSON search error | {e} | component_name : {component_name} | possible_component_value : {possible_component_value} | {type(possible_component_value)}")
                                    exit(1)
                                
                            # handle data-cleaner standardised missing data: #N/A
                            # add nan + other missing values
                            if possible_component_value is None or isna(possible_component_value) or possible_component_value in self.missing_value_tokens:
                                possible_component_value = "NULL"
                            else:
                                visible_components.add(possible_component)
                        else:                            
                            possible_component_value = "NULL"

                    
                        if self.debug:
                            module_logger.debug(f"possible_component : {possible_component} | component_name : {component_name} | possible_component_value : {possible_component_value}")

                        # generate input string
                        check_isinstance(possible_component_value, str)

                        # NOTE: if missing value, we don't want a "NULL" in our string
                        # BACKLOG: should also remove the adjacent separator
                        if possible_component_value == "NULL":
                            input_str = input_str.replace('{' + possible_component + '}', "")
                        else:
                            input_str = input_str.replace('{' + possible_component + '}', possible_component_value)

                        # check unique occurence of the component
                        assert '{' + possible_component + '}' not in input_str

                        
                else:
                    # no mapping for this generator => remove token
                    # BACKLOG: should also remove the adjacent separator
                    input_str = input_str.replace('{' + possible_component + '}', "")

                    possible_component_value = "NULL"

                token_values[possible_component] = possible_component_value

        # METHODOLOGY: fix corrupt unicode
        # "Incheon/\uc1a1\ubbf8\ub85c20\ubc88\uae38//KR" → "Incheon/송미로20번길//KR"
        input_str = fix_text(input_str)
        
        return input_str, token_values, visible_components
    
    def generate(self
                , output : str
                , num_observations : int
                , schemas : List[str] = None
                , batch_size : int = 10000
                , use_cache : bool = True
                , stop_on_error : bool = False
                , require_minimum_fields : bool = True
                , databases : List = ["oa", "osd"]
                , seed : int = None
                , remove_random_component_probability : float = None
                , toggle_source : bool = False
                , add_source : bool = False

                # for compatibility with the generic signature of the generate() function
                , start_date = None 
                , locale_schema : str = None
                ) -> Iterator[ Tuple[ TrainingPair, None] ]:

        """

        :param output: what do generate: pattern

        :param num_observations: amount of observations to generate in total

        :param schemas: list of schemas for the formats

        :param rebuild: force a rebuild of the dataset and overwrite the existing one (if one exists)
            if no existing dataset exists, a new one is created

        :param max_addr: maximum number of addresses to read from file; if None, all are read

        :param databases: list of addresses to read

        :param seed: optional seed for reproducibility => deterministic sampling from the source database
            use an integer, e.g. 42

        :param remove_random_component_probability: randomly remove components; default: do not remove any

        :param toggle_source: optional; if True, use the paired addressed from OA or OSD as input address

        :return: function is a generator -> an iterator of 2-tuples
            1. TrainingPairs (namedtuple)
            2. the input string

        """

        assert isinstance(output, str)
        assert isinstance(num_observations, int)
        assert num_observations > 0 

        if locale_schema is not None:
            warning_key = f"locale_schema_{locale_schema}"
            if warning_key not in self.warnings:
                module_logger.warning(f"requested locale schema '{locale_schema}' will be ignored (no locales currently supported)")
                self.warnings.add(warning_key)
            locale_schema = None

        all_schemas = list(self.format_spec.keys())
        if schemas is None:
            assert "basic" in all_schemas
            schemas = ["basic"]
            module_logger.warning(f"no schemas specified | defaulting to {schemas}")
        else:
            # user specified list of schemas to use
            check_isinstance(schemas, list)
            for schema in schemas:
                assert schema in all_schemas
        
        if self.debug:
            module_logger.debug(f"Selecting from {len(schemas)} schemas | {schemas}")

        # check databases
        check_isinstance(databases, list)
        if len(databases) == 0:
            raise ValueError(f"No databases specified")
        
        if self.debug:
            module_logger.debug(f"{len(databases)} database(s) specified | {databases}")

        #module_logger.debug(f"{len(databases)} databases : {databases}")
        #module_logger.error("debug exit")
        #exit(1)

        # connect to from duckdb for addresses 
        # NOTE: allow user to specify the databases to connect to => create a different cache for different databses
        # NOTE: use a hash becuase we can't have the main database attaching to other source databases with the same name
        cache_path = Path("/tmp/messy_streets")
        cache_path.mkdir(exist_ok=True)
        db_path = cache_path / md5("+".join(sorted(databases)).encode("UTF-8")).hexdigest()

        
        module_logger.debug(f"{len(databases)} databases : {databases} | db_path : {db_path}")

        if db_path.exists():
            db = connect(db_path, read_only=True) # use cache
            if self.debug: module_logger.debug(f"Database already exits, opened Duck DB in read-only mode | {db_path}")
        else:
            db = connect(db_path)
            if self.debug: module_logger.debug(f"Created Duck DB | {db_path}")

        # attach OA and OSD as a convenience
        # NOTE: queries as oa.addresses and osd.addresses
        for database in databases:
            db.execute(f"ATTACH '{self.data_path}/{database}' AS {database} (READ_ONLY)")
        
        if self.debug:
            module_logger.debug("OA and OSD attached")

        # Create a unified view with source provenance
        # NOTE: materialise to avoid full rescans, and shuffle once upfront => fast samppling after
        if not use_cache:
            db.execute("""DROP TABLE IF EXISTS addresses""")

        tables = [t[0] for t in db.execute("SHOW TABLES").fetchall()]

        if "addresses" not in tables:
            # re-open with write 
            db.close()
            db = connect(db_path, read_only=False)
            for database in databases:
                db.execute(f"ATTACH '{self.data_path}/{database}' AS {database} (READ_ONLY)")

            databases_str = "+".join(databases)
            module_logger.debug(f"No cached database found | Materialising addresses from {len(databases)} databases | {databases_str} | ...")
            sql = f"""CREATE TABLE addresses AS SELECT *, '{databases[0]}' AS source FROM {databases[0]}.addresses"""
            for database in databases[1:]:
                sql += f"""\nUNION ALL SELECT *, '{database}' AS source FROM {database}.addresses"""

            
            #print(sql)
            #module_logger.error("debug exit")
            #exit(1)

            db.execute(sql)

        # Get total row count to compute sample percentage
        total_rows = db.execute("SELECT count(*) FROM addresses").fetchone()[0]
        module_logger.debug(f"Total observations available | {total_rows}")
        
        def address_generator(batch_size : int, seed: int | None = None):
            """
            :param seed: optional seed
            """
            check_isinstance(batch_size, int)
            check_isinstance(seed, int, none_ok=True)

            # if a seed is not provided, use a random one
            if seed is None:
                seed = randint(0, 1000)

            batch_num = 0
            while True:
                
                sample_clause = f"USING SAMPLE reservoir({batch_size} ROWS) REPEATABLE({seed + batch_num})"

                if self.debug:
                    module_logger.debug(f"Sampling {batch_size} rows... | {sample_clause}")

                sql = f"""SELECT * FROM addresses {sample_clause}"""
                try:
                    rows = db.execute(sql).fetchall()
                    if self.debug:
                        module_logger.debug(f"Sample taken")

                    cols = [d[0] for d in db.description]
                    yield from (dict(zip(cols, row)) for row in rows)
                    batch_num += 1
                    

                except Exception as e:
                    print(sql)
                    module_logger.error(f"{type(e)} | {e}")
                    exit(1)

        addresses = address_generator(batch_size=batch_size, seed=seed)
            
        # generate random addresses
        t0 = perf_counter()
    
        observation_idx = 0
        random_address = None
        source_datasets = set() # keep track of which databases where add to resolve or toggle sources addresses; don't interfere with addresses list

        while observation_idx < num_observations:
                
            try:

                # select a random address
                """
                # OA example
                {'id': 'b8c3154dda0fe579', 'geohash10': '6gvhw86wy2'
                , 'payload': '{"longitude": "-48.929403", "latitude": "-23.112701", "oa_source": "br/sp/statewide", "oa_id": "b8c3154dda0fe579", "number_min": "151.0", "number_max": "454.0", "number_count": "18", "street": "RUA AMERICA", "unit": "", "city": "Avar\\u00e9", "district": "Avar\\u00e9", "region": "SP", "postcode": "18703-150", "country": "br", "__index__": "0PA9QDJ94CKY4", "__row__": 51654}', 'source': 'oa'}


                # OSD example
                {'id': 'w193835624', 'geohash10': '9wk0etghmu'
                , 'payload': '{"osm_id": "w193835624", "street_name": "10th Street Northeast", "geometry": "LINESTRING (-106.7168253 35.2743695, -106.7168249 35.2745046, -106.7168204 35.2760833, -106.7168141 35.2771152, -106.7168415 35.2781206, -106.7168385 35.2784855, -106.7168201 35.2785882)", "neighbourhood": "#N/A", "region": "#N/A", "postal_code": "#N/A", "country": "US", "lon": "-106.7168242998083", "lat": "35.27647975187917", "__index__": "0PF27E110CTCF", "__row__": 6143035, "city": "Rio Rancho", "city_distance_km": 6.75, "city_geonameid": 5487811, "oa_source": "US"}', 'source': 'osd'}
                """
                random_record = next(addresses)

                address_source = random_record["source"]
                check_isinstance(random_record, dict)

                # extract the address part
                random_address = loads(random_record["payload"])
                check_isinstance(random_address, dict)

                # METHODOLGY: use the lon/lat of the WDC record before toggling the source, else we create a confound if we use the coordinates of the source record
                latitude = float(random_address["latitude"]) if "latitude" in random_address else float(random_address["lat"])
                longitude = float(random_address["longitude"]) if "longitude" in random_address else float(random_address["lon"])

                # METHODOLOGY: for measuring accuracy loss due to the messy address, we can toggle the source to OA/OSD and use the cleaner version as baseline
                source_record = None
                source_record_db = None

                if add_source or toggle_source:
                    
                    source_record_info = loads(random_record["aux"])[0] # NOTE: take first match
                    source_record_id = source_record_info["id"]
                    source_record_db = source_record_info["source"]

                    # attach database if necessary
                    if source_record_db not in source_datasets:
                        db.execute(f"ATTACH '{self.data_path}/{source_record_db}' AS {source_record_db} (READ_ONLY)")
                        source_datasets.add(source_record_db)

                        if self.debug:
                            module_logger.debug(f"Attached database '{source_record_db}'")

                    sql = f"SELECT * FROM {source_record_db}.addresses WHERE id = '{source_record_id}'"
                    source_rows = db.execute(sql).fetchall()
                    if source_rows is None or len(source_rows) == 0:
                        raise ValueError(f"Could not find record '{source_record_id}' in database '{source_record_db}'")
                    
                    source_cols = [d[0] for d in db.description]
                    source_record = dict(zip(source_cols, source_rows[0]))

                    # extract address; note that the keys are those of the source, they will be aligned later
                    source_address = loads(source_record["payload"])
                
                    # swap data, so this source becomes the current record
                    if toggle_source:
                        original_record = random_record.copy()
                        random_record = {"payload" : source_record, "id" : original_record["id"], "geohash10" : original_record["geohash10"] , "aux" : original_record}
                        random_address = source_address
                        address_source = source_record_db

                        check_isinstance(random_record, dict)
                        check_isinstance(random_address, dict)


                if self.debug2:
                    module_logger.debug(f"Observation #{observation_idx} | source : {address_source} | random_record : {random_record}")
                
                
                if address_source not in self.possible_components:
                    print(f"random_record : {random_record}")
                    raise ValueError(f"Unknown source : {address_source} | Possible sources : {self.possible_components}")

                
                # additional info for post analysis
                # NOTE: export the id to ensure no overlap between FT dataset and the benchkar
                aux_info = {
                            "id" : random_record["id"]
                            , "geohash10" : random_record["geohash10"]
                            , "source" : address_source
                            , "address" : random_address
                            }

                if add_source:
                    assert source_record is not None
                    assert source_record_db is not None
                    aux_info["existence"] = { "source" : source_record_db, "address" : source_record }
                    assert "payload" in aux_info["existence"]["address"]

                    # NOTE: ensure JSON
                    """
                    else we get this
                    "{\"osm_id\": \"w1130706497\", \"street_name\": \"Via Toscana\", \"geometry\": \"LINESTRING (11.3708389 44.4683673, 11.3708518 44.4684389, 11.3708866 44.4685708)\", \"postal_code\": \"#N/A\", \"country\": \"IT\", \"lon\": \"11.37086090442812\", \"lat\": \"44.46846945903821\", \"__index__\": \"0PF2YE2NRCR7G\", \"__row__\": 132965, \"city\": \"Ponticella\", \"city_distance_km\": 1.672, \"city_geonameid\": 8948878, \"oa_source\": \"IT\"}"
                    """
                    if isinstance(aux_info["existence"]["address"]["payload"], str):
                        aux_info["existence"]["address"]["payload"] = loads(aux_info["existence"]["address"]["payload"])

                
                # standardise country to lower case
                if "country" in random_address:
                    random_address["country"] = random_address["country"].lower()

                if self.debug2:
                    module_logger.debug(f"latitude : {latitude} | longitude : {longitude}")
                                
                # select a random formatting schema
                random_schema = choice(schemas)
                format_spec = choice(self.format_spec[random_schema])
                separators = choice(self.separators[random_schema])

                # paired street
                # if we need the 'paired_street' component, use the street from the paired OA/OSD address
                # BACKLOG: paired address: keep numbers in the string
                if r"{paired_street}" in format_spec:
                    # NOTE: not compatible with address => BACKLOG: pairsed_address => augment_street()
                    assert r"{address}" not in format_spec

                    # extract pairing info (stored in aux)
                    # NOTE: it's a list as there could e
                    random_address_pairing_info = loads(random_record["aux"])
                    check_isinstance(random_address_pairing_info, list)
                    if len(random_address_pairing_info) > 1:
                        module_logger.warning(f"{len(random_address_pairing_info)} pairing elements found | Only using the first one")
                    
                    random_address_pair = random_address_pairing_info[0]
                    check_isinstance(random_address_pair, dict)

                    street_key = next(k for k, v in self.possible_components[address_source].items() if v == "street")

                    # extract paired address
                    print(random_address)
                    print(random_address_pair)
                    #paired_address = random_address["aux"]["address"]
                    #print(f"paired_address : {paired_address}")
                    paired_street = random_address_pair["street"].replace('"', '') # cleanup double quotes, e.g. "CALLE GRAN" 
                    previous_street = random_address[street_key]


                    print(f"new paired street | {previous_street} | {paired_street}")

                    
                    format_spec = format_spec.replace(r"{paired_street}", r"{street}")

                    

                    # need to use the token of the source, e.g. streetAddress
                    
                    random_address[street_key] = paired_street

                    print(f"new format_spec : {format_spec}")
                    print(f"new random_address : {random_address}")


                # if we need the 'address' component, we need to create an augmented address
                # NOTE: in creating the synthetic address component and inserting it into random_address now, it becomes immutable for this observation
                # this means that when creating pairs for embeddings, the 'address' no longer changes. another design would be to allow the address to change for each rendering
                # so this could should be moved to the render() function
                if r"{address}" in format_spec:
                    if self.debug2:
                        module_logger.debug(f"format_spec : {format_spec}")

                    # extract street name for augmentation
                    street_key = next(k for k, v in self.possible_components[address_source].items() if v == "street")
                    assert street_key is not None
                    street_value = random_address[street_key]

                    if self.debug2:
                        module_logger.debug(f"street_key : {street_key} | street_value : {street_value}")

                    augmented_address = self.augment_street(street=street_value
                                                         , number_min=random_address.get("number_min")
                                                         , number_max=random_address.get("number_max")
                    )

                    if self.debug2:
                        module_logger.debug(f"augmented_address : {street_value} => {augmented_address}")

                    random_address["address"] = augmented_address

                

                
                
                if self.debug:
                    separators_print = [f"{separator} ({ord(separator)})" for separator in separators ]
                    module_logger.debug(f"schema : {random_schema} | format_spec : {format_spec} | {len(separators_print)} separator(s) : {separators_print}")

                input_str, token_values, visible_components = self.render(address=random_address
                                                                          , source=address_source
                                                                          , format_spec=format_spec
                                                                          , separators=separators
                                                                          , schemas=schemas
                                                                          , remove_random_component_probability=remove_random_component_probability
                                                                            )


            except Exception as e:
                tb = e.__traceback__
                
                if self.debug:
                    module_logger.warning(f"Exception at line {tb.tb_lineno}) | {type(e)} | {e} | {random_address}")

                if stop_on_error:
                    print_exception(type(e), e, tb)
                    module_logger.error(f"Exception at line {tb.tb_lineno}) | {type(e)} | {e} | {random_address}")
                    print("STOP ON ERROR")
                    exit(1)
                    
                continue


                #else:
                #    token_values[possible_component] = self.not_present_str

            # require a minimum set of fields to ensure the address can be located within a town/city
            # METHODOLOGY: exactly the same as address/openaddresses/generators/v1.py
            is_valid = not require_minimum_fields or (
                visible_components
                and
                ("street" in visible_components or "address" in visible_components)
                and
                not visible_components.isdisjoint({"locality", "city", "postcode", "region", "country"})
            )

            if not is_valid:
                if self.debug:
                    module_logger.warning(f"Skipping observation {random_address} as missing one or more required components | format_spec : {format_spec} | visibile : {visible_components}")

                continue

            if self.debug:
                module_logger.debug(f"{len(token_values)} token_values")
                for k, v in token_values.items():
                    module_logger.debug(f"{k} : {v}")
            
            # prepare target             
            if output == "model":
                output_str = self.model_name
            
            # for NER (named entity resolution)
            elif output == "entity": 
                output_str = self.entity

            elif output == "raw_components":
                output_str = random_address
                check_isinstance(output_str, dict)

            elif output == "latitude": 
                output_str = str(latitude)

            elif output == "longitude": 
                output_str = str(longitude)

            elif output == "standard_format_1":
                # a standardised surface form for the same canonical address, rendered with the standard template
                output_str, _, _ = self.render(address=random_address
                                                , source=address_source
                                                , format_spec=self.format_spec["address"][0]
                                                , separators=[r"|"]
                                                , schemas=["address"] # METHODOLOGY : prevents augmentation of the country => use two letter code
                                                , remove_random_component_probability=None
                                                , show_components=visible_components
                                                )

            elif output == "standard_format_2":
                # standard_format_2: show the original street from OA/OSD, not the augmented address
                # a standardised surface form for the same canonical address, rendered with the standard template
                # e.g. "2 rue santos dumont,Bourg-en-Bresse,01000" => "rue santos dumont|Bourg-en-Bresse||01000|"
                std_visible_components = visible_components.copy()
                std_visible_components.add("street")
                std_visible_components.remove("address")

                output_str, _, _ = self.render(address=random_address
                                                , source=address_source
                                                , format_spec=self.format_spec["basic"][0]
                                                , separators=[r"|"]
                                                , schemas=["basic"] # METHODOLOGY : prevents augmentation of the country => use two letter code
                                                , remove_random_component_probability=None
                                                , show_components=std_visible_components
                                                )

            elif output == "surface_form_1":
                # Another surface form of the same canonical address, rendered with an independently sampled format and separator set.
                # Paired with input_str for contrastive embedding training.
                # NOTE: surface_form_1 maintains all the components in the input first surface form
                format_spec_2 = choice(self.format_spec[random_schema])
                separators_2 = choice(self.separators[random_schema])

                output_str, _, _ = self.render(address=random_address
                                                , source=address_source
                                                , format_spec=format_spec_2
                                                , separators=separators_2
                                                , schemas=schemas
                                                , remove_random_component_probability=None
                                                )

            elif output == "surface_form_2":
                # Another surface form of the same canonical address, rendered with an independently sampled format and separator set.
                # Paired with input_str for contrastive embedding training.
                # NOTE: surface_form_2 can remove a component according to remove_random_component_probability (if not None and if > 0.0)
                # this allows further expansion of the surface form space
                format_spec_2 = choice(self.format_spec[random_schema])
                separators_2 = choice(self.separators[random_schema])

                output_str, _, _ = self.render(address=random_address
                                                , source=address_source
                                                , format_spec=format_spec_2
                                                , separators=separators_2
                                                , schemas=schemas
                                                , remove_random_component_probability=remove_random_component_probability
                                                )

            elif output == "geohash1":
                output_str = geohash(latitude=latitude, longitude=longitude, precision=1)

            elif output == "geohash2":
                output_str = geohash(latitude=latitude, longitude=longitude, precision=2)

            elif output == "geohash3":
                output_str = geohash(latitude=latitude, longitude=longitude, precision=3)

            elif output == "geohash4":
                output_str = geohash(latitude=latitude, longitude=longitude, precision=4)

            elif output == "geohash5":
                output_str = geohash(latitude=latitude, longitude=longitude, precision=5)

            elif output == "geohash6":
                output_str = geohash(latitude=latitude, longitude=longitude, precision=6)

            elif output == "geohash7":
                output_str = geohash(latitude=latitude, longitude=longitude, precision=7)

            elif output == "geohash8": 
                output_str = geohash(latitude=latitude, longitude=longitude, precision=8)

            elif output == "geohash9": 
                output_str = geohash(latitude=latitude, longitude=longitude, precision=9)

            elif output == "geohash10":
                output_str = geohash(latitude=latitude, longitude=longitude, precision=10)

            elif output in ('street_address', 'street'):
                output_str = token_values.get("street", 'NULL')

            elif output.startswith("source("):
                # e.g 'source(country)', 'source(locality)', 'source(region)', 'source(street)', 'source(pobox)', 
                # country name as specified verbatim in the input source, even if not present in the output sequence
                # if missing in the source, "NULL" is produced
                # e.g. br, US, NO, PT
                # NOTE: it may require further standardisation downstrean
                output_args = parse_function_args(output)
                output_component = output_args[0]
                #print(f"output_args : {output_args} | output_component : {output_component}")
                try:
                    output_key = next(k for k, v in self.possible_components[address_source].items() if v == output_component)
                except Exception as e:
                    if stop_on_error:
                        module_logger.error(f"Something went wrong retrieving output_component '{output_component}' for source '{address_source}' | available components : {self.possible_components[address_source].keys()}")
                        raise e
                    
                    # try another one
                    continue
                
                #print(f"output_key : {output_key}")
                assert output_key is not None
                output_value = random_address.get(output_key, "NULL")
                # HACK: quick whitespace cleaning
                if output_value is None or len(output_value.strip()) == 0 or output_value.strip() in self.missing_value_tokens:
                    output_value = "NULL"
                output_str = output_value
            
            elif output.startswith("has("):
                # e.g 'has(country)', 'has(locality)', 'has(region)', 'has(street)', 'has(postcode)', 
                # if the component is displayed, e.g. 'country', generate 'Yes', else 'No'
                # NOTE: it may require further standardisation downstrean
                output_args = parse_function_args(output)
                output_component = output_args[0]
                #print(f"output_args : {output_args} | output_component : {output_component}")
                output_str = 'Yes' if output_component in visible_components and token_values[output_component] != "NULL" else 'No'

            elif output == 'std_oa_street':
                # street name as specified verbatim in the source from OpenAddresses only (else NULL), even if not present in the output sequence
                # if missing in the source, "NULL" is produced
                if address_source == 'oa':
                    street_key = next(k for k, v in self.possible_components[address_source].items() if v == "street")
                    assert street_key is not None
                    street_value = random_address.get(street_key, "NULL")
                    output_str = street_value
                else:
                    output_str = "NULL" 

            elif output in ('address', 'address'):
                output_str = token_values.get("address", 'NULL')

            elif output in ('postal_code', 'postcode'):
                output_str = token_values.get("postcode", 'NULL')

            elif output == 'locality':
                output_str = token_values.get("locality", 'NULL')

            elif output == 'region':
                output_str = token_values.get("region", 'NULL')

            elif output == 'country':
                output_str = token_values.get("country", 'NULL')

            elif output == 'pobox':
                output_str = token_values.get("pobox", 'NULL')
          
            else:
                raise RuntimeError(f"unhandled output '{output}'")

            
            observation_idx += 1
            yield (TrainingPair(input=input_str, output=output_str, locale=None, aux=aux_info), None)

        

                   
# -----
# main
# -----

if __name__ == "__main__":

    from argparse import ArgumentParser

    # --- command line args ---
    cmd_line_parser = ArgumentParser(description='driver for Generate')
    cmd_line_parser.add_argument('output', type=str, default=None, help='model, entity')
    cmd_line_parser.add_argument('num_observations', type=int, default=None, help='number of observations to generate')

    # generator arguments
    cmd_line_parser.add_argument('--config', type=str, default=None, help="load the generator config from a benchmark config => reproducibility settings, e.g. 'messy_streets/release_gold_geohash1_1'")

    cmd_line_parser.add_argument('--locale_schema', type=str, default=None, help="locale schemas; not supported")
    cmd_line_parser.add_argument('--schemas', type=str, default=None, help="formatting schemas; comma separated, e.g. 'basic, ")
    cmd_line_parser.add_argument('--db', type=str, default="oa, osd", help="databses to connect to; comma separated, e.g. 'oa, osd, wdc'")
    cmd_line_parser.add_argument('--remove', type=float, default=None, help="remove_random_component_probability; probability E [0;1]")
    cmd_line_parser.add_argument('--toggle', default=False, dest='toggle_source', action='store_true', help='toggle the source, use OA or OSD as the input address for the input sequence')
    

    # output
    cmd_line_parser.add_argument('--inputs', default=False, dest='inputs', action='store_true', help='only show inputs in compact form')
    cmd_line_parser.add_argument('--targets', default=False, dest='targets', action='store_true', help='only show targets in compact form')
    cmd_line_parser.add_argument('--compact', default=False, dest='compact', action='store_true', help='compact output: inputs and targets only')

    # advanced
    cmd_line_parser.add_argument('--batch_size', type=int, default=10, help='read address in batches to reduce latency')
    cmd_line_parser.add_argument('--seed', type=int, default=None, help='optional seed for reproducibility => deterministic sampling from the source database use an integer, e.g. 42')
    
    cmd_line_parser.add_argument('--debug', default=False, dest='debug', action='store_true', help='debugging')
    cmd_line_parser.add_argument('--debug2', default=False, dest='debug2', action='store_true', help='debugging')
    cmd_line_parser.add_argument('--stop_on_error', default=False, dest='stop_on_error', action='store_true', help='debugging')
    cmd_line_parser.add_argument('--stop-on-error', default=False, dest='stop_on_error', action='store_true', help='debugging')
    

    args = cmd_line_parser.parse_args()

    # schemas
    schemas = [schema.strip() for schema in args.schemas.split(",")] if args.schemas is not None else None

    # databases
    databases = [db.strip() for db in args.db.split(",")] if args.db is not None else None

    # create generator
    generator = Generate(debug=args.debug, debug2=args.debug2)

    if args.config is None:
        # use CLI args
        results = generator.generate(args.output
                                 , num_observations=args.num_observations
                                 , schemas=schemas
                                 , locale_schema=args.locale_schema
                                 , batch_size=args.batch_size
                                 , stop_on_error=args.stop_on_error
                                 , databases=databases
                                 , seed=args.seed
                                 , remove_random_component_probability=args.remove
                                 , toggle_source=args.toggle_source
                                 , add_source=args.add_source
                                 )

    else:

        # use existing benchmark settings
        # Get benchmark path: e.g. messy_streets/release_gold_geohash1_1
        # full path: $PYTHONPATH//messy_streets/release_gold_geohash1_1/config.hjson 
        #
        # USAGE
        # python3 generators/v2.py geohash7 10 --config messy_streets/release_gold_geohash1_1 --debug --stop_on_error
        benchmark_path = Path(environ["PYTHONPATH"]) / "phd/benchmarks" /  args.config
        if not benchmark_path.exists():
            raise FileNotFoundError(f"Benchmark '{args.config}' not found in '{benchmark_path}'")
        benchmark_config_file = benchmark_path / "config.hjson"
        if not benchmark_config_file.exists():
            raise FileNotFoundError(f"Benchmark config not found in '{benchmark_path}'")

        module_logger.debug(f"Loading from {benchmark_config_file}...")
        benchmark_config = LoadJSON().load(benchmark_config_file)
        benchmark_kwargs = benchmark_config["kwargs"]
        module_logger.debug(f"Loaded bebchmark kwargs | {benchmark_kwargs}")
        check_isinstance(benchmark_kwargs, dict)
        # HACK: JSON type casts
        if "seed" in benchmark_kwargs:
            benchmark_kwargs["seed"] = int(benchmark_kwargs["seed"])

        module_logger.info(f"Using generator configuration from benchmark {args.config}")
        module_logger.debug(f"benchmark config : {benchmark_kwargs}")

        results = generator.generate(args.output
                                 , num_observations=args.num_observations
                                 , **benchmark_kwargs 
                                 , stop_on_error=args.stop_on_error
        )

    # show output
    outputs = []


    for idx, (training_pair, _) in enumerate(results):

        if args.compact:
            outputs.append({"input" : training_pair.input, "output" : training_pair.output})
            

        elif args.inputs:
            outputs.append(training_pair.input)
            
        
        elif args.targets:
            outputs.append(training_pair.output)
        
        else:
            outputs.append(training_pair)

    df = DataFrame(outputs)
    set_option("display.width", None)
    set_option("display.max_colwidth", 80)
    print(df)

             
    async_run(generator.close())
