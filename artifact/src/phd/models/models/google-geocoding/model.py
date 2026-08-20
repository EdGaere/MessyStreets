"""
model.py: wrapper for geopy/Googlv3 geolocation/geocoding service

NOTES
* Google Maps API v3 — released 2009, still current
* GoogleV3 calls the Google Maps Geocoding API, which is part of the Google Maps Platform.Specifically:
* Endpoint: https://maps.googleapis.com/maps/api/geocode/json
* Documentation: https://developers.google.com/maps/documentation/geocoding

INSTALL
pip3 install certifi
pip3 install geopy

SETUP
# [credential removed when vendoring; supply your own via the environment — see README]

CHANGE LOG
edward | 2025-11-08

USAGE
python model.py country "The Book Club 100-106 Leonard St Shoreditch London EC2A 4RH, United Kingdom"
python model.py country "175 5th Avenue NYC"
python model.py country "173/Rebecca Place#Walk-|South Matthewton Macao,29272"
python model.py country "Branch|Robert Prairie 90620-|Port Jessica/37974 Brazil"

python model.py geohash7 "1200 16th St NW Washington DC 20036 US"
"""
from asyncio import run as async_run
from os import environ
from random import choice
import ssl
from string import ascii_lowercase
from time import perf_counter
from typing import Dict, Tuple, Optional, List, Any

# 3rd party
import certifi
from geopy.geocoders import GoogleV3
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
        self.component_key = config.get("component_key")
        model_logger.debug(f"component : '{self.component}' | component_key : {self.component_key}")

        if "GOOGLE_MAPS_API_KEY" not in environ:
            raise RuntimeError(f"GOOGLE_MAPS_API_KEY not set")
        
        api_key = environ["GOOGLE_MAPS_API_KEY"]
        model_logger.debug(f"api key found : {api_key}")

        # create geolocator instance with Rate Limiter
        ctx = ssl.create_default_context(cafile=certifi.where())
        self.geolocator = GoogleV3(api_key=api_key, timeout=30, ssl_context=ctx)
        self.rate_limited_geocoder = RateLimiter(self.geolocator.geocode, min_delay_seconds=2)

    async def predict_batch(self
                            , input_sequences : List[str]
                            , prompt_template : Optional[str] = None
                            , prompt_args : Optional[List[Dict]] = None
                            , **kwargs) -> Tuple[ List[Optional[str]], List[Optional[float]] ]:
        
        """
        BACKLOG: not sure if the endpoint supports batch processing => simply iterate
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
        
    @adisk_cache('~/data/cache/google_geocoding')
    async def _call_api(self, input_sequence : str) -> Any:
        model_logger.debug(f"API call | {input_sequence}")
        return self.rate_limited_geocoder(input_sequence)


    async def predict(self, prompt_template : Optional[str] = None, **kwargs) -> Tuple[str, float]:


        assert "input_sequence" in kwargs

        input_sequence = kwargs["input_sequence"]
        model_logger.debug(f"input_sequence : '{input_sequence}'")

        t0 = perf_counter()
        location = await self._call_api(input_sequence)
        t1 = perf_counter()

        model_logger.debug(f"compute time : {round(1000.0 * (t1 - t0), 2)}ms")

        if self.debug:
            model_logger.debug(f"location {type(location)} : {location}")

        prediction = None
        if location is not None:
            # parse address components; it's a list of dicts
            """
            {'long_name': '100-106', 'short_name': '100-106', 'types': ['street_number']}
            {'long_name': 'Leonard Street', 'short_name': 'Leonard St', 'types': ['route']}
            {'long_name': 'London', 'short_name': 'London', 'types': ['postal_town']}
            {'long_name': 'Greater London', 'short_name': 'Greater London', 'types': ['administrative_area_level_2', 'political']}
            ...
            """
            if self.component == "geohash":
                precision = self.config["precision"]
                prediction = geohash(latitude=location.latitude, longitude=location.longitude, precision=precision)
            else:
                address_components = location.raw["address_components"]
                if self.debug:
                    model_logger.debug(f"\n-- {len(address_components    )} address components --")
                
                for address_component in address_components:

                    if self.debug:
                        model_logger.debug(address_component)

                    types = address_component["types"]
                    
                    if self.component in types:
                        assert self.component_key in address_component
                        prediction = address_component[self.component_key]
                        assert type(prediction) is str

                        # NOTE: limitation: stop on first matched type
                        break
        
        model_logger.debug(f"prediction : {prediction}")

        return prediction, None


if __name__ == "__main__":

    from typer import run

    def main(config : str, input_sequence : str, debug : bool = False):
        async_run(amain(config, input_sequence, debug))

    async def amain(config : str, input_sequence : str, debug : bool = False):
        """
        :param config: configuration to load, e.g. country

        :param input_sequence: address to be parsed
        """

        config_file = f"configs/{config}.hjson"
        config = LoadJSON().load(config_file)

        model = Model(config, debug=debug)
        prediction, prob = await model.predict(input_sequence=input_sequence)

        print(f"prediction : {prediction}")
        print(f"prob : {prob}")


    run(main)