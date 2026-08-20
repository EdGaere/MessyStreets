"""
model.py: wrapper for geopy/OpenMapQuest geocoding service (open OSM data)

NOTES
* OpenMapQuest extends Nominatim, so response shape matches Nominatim
* Requires a MapQuest API key (even for the open endpoint)

USAGE
# [credential removed when vendoring; supply your own via the environment — see README]

python model.py country "175 5th Avenue NYC"
python model.py geohash4 "175 5th Avenue NYC"
"""
from asyncio import run as async_run
from os import environ
import ssl
from time import perf_counter
from typing import Dict, Tuple, Optional, List, Any

import certifi
from geopy.geocoders import MapQuest
from geopy.extra.rate_limiter import RateLimiter
from pygeohash import encode as geohash

from serentec.utils.json.load_json import LoadJSON
from serentec.backend.cache.disk_cache import adisk_cache
from phd.models.model_base import ModelBase, model_logger


class Model(ModelBase):

    def __init__(self
                 , config: Dict = None
                 , timeout_seconds: int = None
                 , run_number: int = None
                 , debug: bool = False
                 , debug2: bool = False
                 ):
        model_logger.debug(f"Model instance created with config : {config}")

        self.debug = debug
        self.debug2 = debug2

        self.config = config
        self.component = config["component"]
        model_logger.debug(f"component : '{self.component}'")

        if "MAPQUEST_API_KEY" not in environ:
            raise RuntimeError("MAPQUEST_API_KEY not specified")
        api_key = environ["MAPQUEST_API_KEY"]

        ctx = ssl.create_default_context(cafile=certifi.where())
        self.geolocator = MapQuest(api_key=api_key, timeout=30, ssl_context=ctx)
        self.rate_limited_geocoder = RateLimiter(self.geolocator.geocode, min_delay_seconds=1)

    async def predict_batch(self
                            , input_sequences: List[str]
                            , prompt_template: Optional[str] = None
                            , prompt_args: Optional[List[Dict]] = None
                            , **kwargs) -> Tuple[List[Optional[str]], List[Optional[float]]]:
        predictions, probs = [], []
        for input_sequence in input_sequences:
            prediction, prob = await self.predict(input_sequence=input_sequence
                                                  , prompt_template=prompt_template
                                                  , **kwargs)
            predictions.append(prediction)
            probs.append(prob)
        return predictions, probs

    @adisk_cache('~/data/cache/openmapquest')
    async def _call_api(self, input_sequence: str) -> Any:
        if self.debug:
            model_logger.debug("Sending request to OpenMapQuest...")
        return self.rate_limited_geocoder(input_sequence)

    async def predict(self, prompt_template: Optional[str] = None, **kwargs) -> Tuple[str, float]:
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
            if self.component == "geohash":
                precision = self.config["precision"]
                prediction = geohash(latitude=location.latitude, longitude=location.longitude, precision=precision)
            else:
                raw = location.raw
                field = {
                    "country": "adminArea1"    # "GB"
                    , "region": "adminArea3"     # "ENG"
                    , "locality": "adminArea5"   # "London"
                    , "postcode": "postalCode"
                    , "street": "street"
                }.get(self.component)
                if field and raw.get(field):
                    prediction = raw[field]

        model_logger.debug(f"prediction : {prediction}")
        return prediction, None


if __name__ == "__main__":
    from typer import run

    def main(config: str, input_sequence: str, clear_cache: bool = False, debug: bool = False, debug2: bool = False):
        async_run(amain(config, input_sequence, clear_cache=clear_cache, debug=debug, debug2=debug2))

    async def amain(config: str, input_sequence: str, clear_cache: bool = False, debug: bool = False, debug2: bool = False):
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