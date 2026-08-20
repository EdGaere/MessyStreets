"""
model_base.py: Base class for all models

NOTES

CHANGE LOG
edward | 2024-08-17

BACKLOG
"""

from abc import ABC, abstractmethod
from os import environ
from typing import Any, Tuple, Optional, List, Dict
from uuid import uuid4, UUID

from serentec.utils.optional_abstractmethod import optional_abstractmethod

# logging
from serentec.utils.logger import logger_dl
model_logger = logger_dl.getChild("Model")


class ModelBase:


    def get_model_instance_uuid(self) -> UUID:
        """
        return the unique identifer of the instance of this model (UUID). Allows tracking id
        """
        if not hasattr(self, "model_instance_uuid") or self.model_instance_uuid is None:
            self.model_instance_uuid = uuid4()

        return self.model_instance_uuid


    def get_model_logfile(self) -> Optional[str]:
        """
        Return the filename of the logfile, if any. Returns None if there is no logfile.
        """
        return None

    
    @abstractmethod
    async def predict(self, input_sequence : str, prompt_template : Optional[str] = None) -> Tuple[Optional[Any], float]:
        """
        Single prediction.

        :param prompt_template: optional; use this prompt template
            if not specified, the default template defined at init is used (self.prompt_template)

        Retruns a 2-tuple; 
            1. prediction (should be cast to the correct type, e.g str, int, ... )
                can be None if the model returned no prediction
            2. probability
        """
        pass

    @optional_abstractmethod
    async def predict_batch(self
                            , input_sequences : List[str]
                            , prompt_template : Optional[str] = None
                            , prompt_args : Optional[List[Dict]] = None
                            , **kwargs) -> Tuple[ List[Optional[Any]], List[Optional[float]] ]:
        """
        Batch prediction.

        :param prompt_template: optional; use this prompt template
            if not specified, the default template defined at init is used (self.prompt_template)

        :param prompt_args: optional list of arguments for each prompt

        :param **kwargs: any additional arguments for the prompt or the model

        Returns 2 lists:
            1. predictions (should be cast to the correct type, e.g str, int, ... )
                can be None if the model returned no prediction
            2. probabilities
        """

        raise NotImplementedError(f"This model implementation does not support batch processing")
    
    
    @abstractmethod
    async def close(self):
        pass