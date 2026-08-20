"""The replacement for serentec/config.py, written into the vendored tree.

The artefact reads exactly one attribute from SerenTec's global configuration:
`default_missing_data_tokens`, the list of strings a source may use to mean
"no value". The file it lives in is 420 lines describing an entire data
product — warehouse connection strings, forecasting and insight pipelines,
cardinality thresholds, API provider settings, a production hostname.

None of that is needed to reproduce a geocoding benchmark, and SerenTec is a
name its author may yet trade under. So the module is replaced wholesale rather
than vendored and scrubbed: the value is preserved exactly, and nothing else
crosses over.
"""

STUB = '''# -*- coding: utf-8 -*-

"""
Minimal stand-in for SerenTec's global configuration.

The MESSY STREETS artefact reads one value from it — the tokens a data source
may use to mean "no value" — which the dataset generators use when deciding
whether an address component is present. The original module configures an
entire data platform and is not part of this artefact; it was replaced when
vendoring rather than copied. See tools/config_stub.py.

The list below is reproduced verbatim from the configuration that produced the
paper, so generator behaviour is unchanged.
"""


class Config:

    def __init__(self):
        self.missing_data_token = r"#N/A"

        self.default_missing_data_tokens = [
            None,
            self.missing_data_token,
            "None",
            "",
            "-",
            "#N/A",
            "#N/A N/A",
            "#NA",
            "-1.#IND",
            "-1.#QNAN",
            "-NaN",
            "-nan",
            "1.#IND",
            "1.#QNAN",
            "<NA>",
            "N/A",
            "NA",
            "NULL",
            "NaN",
            "n/a",
            "nan",
            "null",
            "#REF!",
            "undefined",
            "(nil)",
            "nil",
            "NAN",
            "?",
            "MISSING",
            "INF",
            "-INF",
        ]
'''
