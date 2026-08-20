"""
lexical_similarity.py: token-Jaccard, character-trigram, and normalised Levenshtein similarity between two strings.

All three return a similarity in [0, 1] where 1.0 is identical.
Dissimilarity is 1 - similarity.

INSTALL
pip3 install rapidfuzz

CREATED
edward | 2026-05-31
"""

from typing import Set


def _normalise(s: str) -> str:
    """
    Lowercase and collapse whitespace.

    :param s: Input string.
    :return: Normalised string.
    """
    return " ".join(s.lower().split())


def jaccard_similarity(a: str, b: str) -> float:
    """
    Token-level Jaccard similarity.

    Tokens are whitespace-delimited after normalisation. The score
    is the token intersection over the token union.

    :param a: First string.
    :param b: Second string.
    :return: Similarity in [0, 1]; 1.0 for two empty strings.
    """
    sa, sb = set(_normalise(a).split()), set(_normalise(b).split())
    if not (sa | sb):
        return 1.0
    return len(sa & sb) / len(sa | sb)


def _trigrams(s: str) -> Set[str]:
    """
    Character trigram set, padded at both ends.

    :param s: Normalised string.
    :return: Set of character trigrams.
    """
    s = f"  {s}  "
    return {s[i:i + 3] for i in range(len(s) - 2)}


def trigram_similarity(a: str, b: str) -> float:
    """
    Character-trigram Jaccard similarity.

    Captures sub-word overlap, so abbreviations and minor spelling
    differences score partial rather than zero similarity.

    :param a: First string.
    :param b: Second string.
    :return: Similarity in [0, 1]; 1.0 for two empty strings.
    """
    ta, tb = _trigrams(_normalise(a)), _trigrams(_normalise(b))
    if not (ta | tb):
        return 1.0
    return len(ta & tb) / len(ta | tb)


def _levenshtein_distance(a: str, b: str) -> int:
    """
    Levenshtein edit distance via dynamic programming.

    Pure-Python fallback used when no compiled library is available.

    :param a: First string.
    :param b: Second string.
    :return: Minimum single-character edits to transform a into b.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            insert = current[j - 1] + 1
            delete = previous[j] + 1
            substitute = previous[j - 1] + (ca != cb)
            current.append(min(insert, delete, substitute))
        previous = current
    return previous[-1]


# prefer a compiled implementation if present
try:
    from Levenshtein import distance as _levenshtein_distance  # type: ignore
except ImportError:
    try:
        from rapidfuzz.distance.Levenshtein import distance as _levenshtein_distance  # type: ignore
    except ImportError:
        pass  # use the pure-Python fallback defined above


def levenshtein_similarity(a: str, b: str) -> float:
    """
    Normalised Levenshtein similarity.

    Edit distance divided by the longer string length, subtracted
    from one. Operates on normalised strings.

    :param a: First string.
    :param b: Second string.
    :return: Similarity in [0, 1]; 1.0 for two empty strings.
    """
    na, nb = _normalise(a), _normalise(b)
    if not na and not nb:
        return 1.0
    d = _levenshtein_distance(na, nb)
    return 1.0 - d / max(len(na), len(nb))


if __name__ == "__main__":
    wdc = "165 East 200 South Salt Lake City UT 84111 USA"
    oa = "E 200 S SALT LAKE CITY UT 84111 us"

    print(f"jaccard     : {jaccard_similarity(wdc, oa):.4f}")
    print(f"trigram     : {trigram_similarity(wdc, oa):.4f}")
    print(f"levenshtein : {levenshtein_similarity(wdc, oa):.4f}")