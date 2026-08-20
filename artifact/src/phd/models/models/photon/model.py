"""
model.py: wrapper for geopy/Photon (Komoot) geolocation/geocoding service

SOURCE
https://github.com/komoot/photon

NOTES
* Does not require an API key

INSTALL
pip3 install certifi
pip3 install geopy

CHANGE LOG
edward | 2025-11-08

USAGE
python model.py country "The Book Club 100-106 Leonard St Shoreditch London EC2A 4RH, United Kingdom"
python model.py country "175 5th Avenue NYC"
python model.py country "173/Rebecca Place#Walk-|South Matthewton Macao,29272"
python model.py country "Branch|Robert Prairie 90620-|Port Jessica/37974 Brazil"
python model.py country "Rowland Mews/Landing-417-/70276/Jennifertown-South Africa"
python model.py country "Tara Trail|Courts 6715.#Barbarafurt#Saudi Arabia#05298"

python model.py geohash7 "1200 16th St NW Washington DC 20036 US"
"""
from asyncio import run as async_run
from random import choice
import ssl
from string import ascii_lowercase
from time import perf_counter
from typing import Dict, Tuple, Optional, List, Any

# 3rd party
import certifi
from geopy.geocoders import Photon
from geopy.extra.rate_limiter import RateLimiter
from pygeohash import encode as geohash

from serentec.utils.json.load_json import LoadJSON
from serentec.backend.cache.disk_cache import adisk_cache
from phd.models.model_base import ModelBase, model_logger

class Model(ModelBase):

    def __init__(self
                 , config : Dict = None
                 # NOTE: the following arguments are required for compatibility with RunExperiment
                 , timeout_seconds : int = None
                 , run_number : int = None
                 , debug : bool = False
                 , debug2 : bool = False
                 ):
        model_logger.debug(f"Model instance created with config : {config}")

        self.debug = debug

        # process config parameters
        self.config = config
        self.component = config["component"]
        model_logger.debug(f"component : '{self.component}'")

        # create geolocator instance with Rate Limiter
        ctx = ssl.create_default_context(cafile=certifi.where())
        self.geolocator = Photon(user_agent="Edward Gaere's PhD / Paper2", timeout=30, ssl_context=ctx)
        self.rate_limited_geocoder = RateLimiter(self.geolocator.geocode, min_delay_seconds=2)

    async def predict_batch(self
                            , input_sequences : List[str]
                            , prompt_template : Optional[str] = None
                            , prompt_args : Optional[List[Dict]] = None
                            , **kwargs) -> Tuple[ List[Optional[str]], List[Optional[float]] ]:
        
        """
        BACKLOG: not sure if geopy supports batch processing => simply iterate
        """
        predictions, probs = [], []

        for input_sequence in input_sequences:
            prediction, prob = await self.predict(input_sequence=input_sequence
                                                  , prompt_template=prompt_template
                                                  , **kwargs
                                                  )

            predictions.append(prediction)
            probs.append(prob)

        return predictions, probs
        
    @adisk_cache('~/data/cache/photon')
    async def _call_api(self, input_sequence : str) -> Any:
        return self.rate_limited_geocoder(input_sequence)
    
    async def predict(self, prompt_template : Optional[str] = None, **kwargs) -> Tuple[str, float]:

        assert "input_sequence" in kwargs

        input_sequence = kwargs["input_sequence"]
        #input_sequence = r"The Bookclub, 100-106, Leonard Street, EC2A 4RH, Leonard Street, London, England, United Kingdom"
        #input_sequence = r"175 5th Avenue NYC"
        model_logger.debug(f"input_sequence : '{input_sequence}'")

        t0 = perf_counter()
        location = await self._call_api(input_sequence)
        t1 = perf_counter()

        model_logger.debug(f"compute time : {round(1000.0 * (t1 - t0), 2)}ms")

        #if self.debug:
        model_logger.debug(f"location {type(location)} : {location}")
        

        prediction = None
        if location is not None:

            if self.component == "geohash":
                precision = self.config["precision"]
                prediction = geohash(latitude=location.latitude, longitude=location.longitude, precision=precision)

            else:
                # parse address components
                address = location.raw["address"]

                for k, v in address.items():
                    if self.debug:
                        model_logger.debug(f"{k} | {v}")
                    
                    if k == self.component:
                        prediction = v
        
        model_logger.debug(f"prediction : {prediction}")

        return prediction, None


if __name__ == "__main__":

    from typer import run

    def main(config : str, input_sequence : str, clear_cache : bool = False, debug : bool = False, debug2 : bool = False):
        async_run(amain(config, input_sequence, clear_cache=clear_cache, debug=debug, debug2=debug2))

    async def amain(config : str, input_sequence : str,  clear_cache : bool = False, debug : bool = False, debug2 : bool = False):
        """
        :param config: configuration to load, e.g. country

        :param input_sequence: address to be parsed
        """

        config_file = f"configs/{config}.hjson"
        config = LoadJSON().load(config_file)

        model = Model(config, debug=debug, debug2=debug2)
        if clear_cache:
            model._call_api.clear()
            print("cache cleared")
            
        prediction, prob = await model.predict(input_sequence=input_sequence)

        print(f"prediction : {prediction}")
        print(f"prob : {prob}")


    run(main)