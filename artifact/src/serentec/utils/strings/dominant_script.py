"""
dominant_script.py: infer dominant script from a string, e.g. Latin

NOTES
A script is a writing system — the set of characters used to render text. Latin, Cyrillic, CJK (Han/Kana/Hangul), Greek, Arabic, Devanagari. It's a property of the string itself — you can determine it by looking at the characters, which is exactly what the Unicode-range code does. "斯莱顿" is CJK script; "Slatton" is Latin script; the two render the same place name in different writing systems.

A locale is broader — it's a combination of language, region, and cultural formatting conventions, usually written as language_REGION (e.g. en_US, de_CH, fr_FR, pt_BR). It encodes not just the language but regional variants: en_US vs en_GB differ in spelling and date formats; de_DE vs de_CH differ in conventions despite sharing a language. A locale tells you how text is expected to be formatted and interpreted, not just which characters it uses.

CREATED
edward | 2026-05-31

"""
import unicodedata
from collections import Counter

def dominant_script(s: str) -> str:
    """
    Classify a string's dominant script by Unicode character ranges.

    :param s: Input string.
    :return: Script label (Latin, Cyrillic, CJK, Greek, Arabic, etc.).
    """
    counts = Counter()
    for ch in s:
        if not ch.isalpha():
            continue
        name = unicodedata.name(ch, "")
        if "LATIN" in name:
            counts["Latin"] += 1
        elif "CYRILLIC" in name:
            counts["Cyrillic"] += 1
        elif "CJK" in name or "HIRAGANA" in name or "KATAKANA" in name or "HANGUL" in name:
            counts["CJK"] += 1
        elif "GREEK" in name:
            counts["Greek"] += 1
        elif "ARABIC" in name:
            counts["Arabic"] += 1
        else:
            counts["Other"] += 1
    if not counts:
        return "None"
    return counts.most_common(1)[0][0]