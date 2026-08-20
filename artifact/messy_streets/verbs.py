"""The command table, parsed from verbs.tsv.

The same file is read by the ./messy-streets wrapper, so the wrapper's decision
about --network none and the CLI's own idea of what a verb does cannot drift
apart.
"""

from typing import Dict, List, NamedTuple

from messy_streets import paths


class Verb(NamedTuple):
    name: str
    network: str      # "none" (air-gapped) or "host"
    layer: str        # reproducibility layer, or "-"
    slice: int        # build slice that implements it; 0 = not yet built
    description: str

    @property
    def implemented(self) -> bool:
        return self.slice > 0 and self.slice <= IMPLEMENTED_THROUGH

    @property
    def offline(self) -> bool:
        """Touches no network. True for host-side verbs too — they write a file."""
        return self.network != "host"

    @property
    def needs_network(self) -> bool:
        return self.network == "host"

    @property
    def host_side(self) -> bool:
        """Runs outside the container: it writes where the container cannot reach."""
        return self.network == "host-side"


# Bumped as each slice lands. Verbs above this are listed but refuse to run,
# so `messy-streets --help` always shows the whole intended surface.
IMPLEMENTED_THROUGH = 9


def load() -> Dict[str, Verb]:
    verbs: Dict[str, Verb] = {}
    for line in paths.verbs_file().read_text(encoding="utf8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, network, layer, slice_, description = line.split("\t")
        verbs[name] = Verb(name, network, layer, int(slice_), description)
    return verbs


def names() -> List[str]:
    return list(load())
