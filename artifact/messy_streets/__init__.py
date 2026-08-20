"""MESSY STREETS reproduction artefact.

The command-line interface is deliberately stdlib-only: `doctor` has to be able
to diagnose a broken dependency install, which it cannot do if it depends on
the dependencies it is checking.
"""

__version__ = "1.0.0"

# Bumped when the shipped data changes in a way that invalidates checksums.
DATA_REVISION = "5"
