"""
descriptive_stats.py: compute basic descriptive statistics for a
vector of floats and serialise them to JSON.
"""

from json import dump
from pathlib import Path
from typing import Dict, Optional, Sequence

import numpy as np


class DescriptiveStats:
    """
    Compute descriptive statistics for a numeric vector.

    Statistics include count, min, max, mean, median, standard
    deviation, and the 1st and 99th percentiles.
    """

    def __init__(self, values: Sequence[float], label: Optional[str] = None) -> None:
        """
        Compute statistics on construction.

        :param values: Sequence of numeric values.
        :param label: Optional identifier carried through to output.
        :raises ValueError: If values is empty.
        """
        arr = np.asarray(values, dtype=float)
        if arr.size == 0:
            raise ValueError("values must not be empty")

        self.label = label
        self.n = int(arr.size)
        self.min = float(np.min(arr))
        self.max = float(np.max(arr))
        self.mean = float(np.mean(arr))
        self.median = float(np.median(arr))
        self.std = float(np.std(arr))
        self.p1 = float(np.percentile(arr, 1))
        self.p99 = float(np.percentile(arr, 99))

    def as_dict(self) -> Dict:
        """
        Return statistics as a dictionary.

        :return: Mapping of statistic name to value, including label.
        """
        return {
              "label": self.label
            , "n": self.n
            , "min": self.min
            , "p1": self.p1
            , "median": self.median
            , "mean": self.mean
            , "p99": self.p99
            , "max": self.max
            , "std": self.std
        }

    def to_json(self, path: Path) -> None:
        """
        Write statistics to a JSON file.

        :param path: Output file path.
        :return: None.
        """
        with open(path, "w", encoding="utf-8") as f:
            dump(self.as_dict(), f, indent=2)


if __name__ == "__main__":
    from numpy.random import default_rng

    rng = default_rng(3407)
    sample = rng.beta(2, 3, size=1000).tolist()

    stats = DescriptiveStats(sample, label="token_jaccard")
    print(stats.as_dict())
    stats.to_json(Path("token_jaccard_stats.json"))