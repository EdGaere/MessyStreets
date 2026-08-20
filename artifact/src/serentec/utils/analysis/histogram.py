"""
histogram.py: reusable terminal histogram for distribution analysis.
"""
from collections import Counter
from typing import Dict, Optional, Sequence

import numpy as np
import plotext as plt


def plot_counts(
      categories: Sequence[str]
    , title: str
    , xlabel: str
    , top_n: Optional[int] = None
    , show_stats: bool = True
) -> Dict[str, int]:
    """
    Plot a terminal bar chart of category frequencies.

    :param categories: Sequence of category labels (e.g. ISO2 codes).
    :param title: Plot title.
    :param xlabel: Label for the x-axis.
    :param top_n: If set, show only the top_n most frequent categories.
    :param show_stats: If True, print summary counts below the plot.
    :return: Dict mapping category to count, ordered most to least frequent.
    """
    counts = Counter(categories)
    ordered = counts.most_common(top_n)
    labels = [k for k, _ in ordered]
    values = [v for _, v in ordered]

    plt.clear_figure()
    plt.bar(labels, values)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel("Count")
    plt.show()

    if show_stats:
        total = sum(counts.values())
        n_cats = len(counts)
        print(f"total={total}  distinct={n_cats}  shown={len(ordered)}")

    return dict(ordered)

def plot_histogram(
      values: Sequence[float]
    , title: str
    , xlabel: str
    , bins: int = 30
    , show_stats: bool = True
) -> dict:
    """
    Plot a terminal histogram of a value distribution.

    :param values: Sequence of numeric values to plot.
    :param title: Plot title.
    :param xlabel: Label for the x-axis.
    :param bins: Number of histogram bins.
    :param show_stats: If True, print summary statistics below the plot.
    :return: Dict of summary statistics (n, mean, median, std, min, max).
    """
    arr = np.asarray(values, dtype=float)

    stats = {
          "n": int(arr.size)
        , "mean": float(np.mean(arr))
        , "median": float(np.median(arr))
        , "std": float(np.std(arr))
        , "min": float(np.min(arr))
        , "max": float(np.max(arr))
    }

    plt.clear_figure()
    plt.hist(arr.tolist(), bins=bins)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel("Count")
    plt.show()

    if show_stats:
        print(
            f"n={stats['n']}  "
            f"mean={stats['mean']:.3f}  "
            f"median={stats['median']:.3f}  "
            f"std={stats['std']:.3f}  "
            f"min={stats['min']:.3f}  "
            f"max={stats['max']:.3f}"
        )

    return stats