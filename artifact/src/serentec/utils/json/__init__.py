"""
Stdlib compatibility shim.

Python resolves ``import json`` to this local package because it shares
a name with the standard library module. Any transitive dependency
(e.g. pydantic, httpx, typer) that does ``from json import dumps``
will hit this file instead of the stdlib and fail.

This block locates the real stdlib ``json`` by its installed path,
temporarily installs it as ``json`` in sys.modules so its internal
relative imports resolve, then re-exports its public symbols and
restores ourselves. Downstream code sees the stdlib names it expects;
our own package contents follow below.
"""
import sys as _sys
import sysconfig as _sc
import importlib.util as _ilu
from pathlib import Path as _Path

_stdlib_path = _Path(_sc.get_paths()["stdlib"]) / "json" / "__init__.py"
_spec = _ilu.spec_from_file_location("json", str(_stdlib_path), submodule_search_locations=[str(_stdlib_path.parent)])
_stdlib_json = _ilu.module_from_spec(_spec)

_self = _sys.modules.pop("json", None)
_sys.modules["json"] = _stdlib_json
_spec.loader.exec_module(_stdlib_json)
if _self is not None:
    _sys.modules["json"] = _self

dumps = _stdlib_json.dumps
loads = _stdlib_json.loads
dump = _stdlib_json.dump
load = _stdlib_json.load
JSONDecodeError = _stdlib_json.JSONDecodeError