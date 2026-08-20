"""stats — recompute the dataset-level figures from the released tiers.

Covers Table 3 (component existence) and the Biases paragraph (script and
continent distributions).

Table 3 needs care. The paper's numbers were not computed over the released
tiers: each cell is a 1,000-observation sample drawn from a benchmark slice,
and the silver row was drawn from mq_1000, a 1,000-record pre-release database
rather than the released silver tier. Six of the fifteen cells also differ from
the analysis outputs that the paper's own method produced.

So this command reports three columns — the released tiers, the analysis
output, and what the paper prints — rather than asserting one of them. What it
computes is the truth about the data being released; the other two are shown
so the difference is visible instead of buried.
"""

from collections import Counter
from json import dumps, loads
from typing import Dict, List, NamedTuple

from messy_streets import paths, tiers, workspace


class Row(NamedTuple):
    component: str
    tier: str
    released: float          # computed here, over all 10,000 records
    analysis: float          # the paper's method, 1,000-observation sample
    published: float         # what the paper prints

    @property
    def released_vs_published(self) -> float:
        return round(self.released - self.published, 1)


def component_existence() -> Dict[str, Dict[str, float]]:
    """Share of records with a non-empty value, over every released record."""
    results = {}
    for tier in tiers.TIERS:
        records = tiers.load(tier)
        results[tier] = {
            name: round(100.0 * sum(tiers.present(tiers.address(r).get(field))
                                    for r in records) / len(records), 1)
            for name, field in tiers.COMPONENTS.items()
        }
        results[tier]["_records"] = len(records)
    return results


def distributions() -> Dict[str, Dict[str, Dict[str, float]]]:
    """Script shares, over every released record.

    Script is classified from the address string itself, by Unicode range —
    the same classifier the paper used.

    Continent shares are deliberately absent. The paper resolves a country
    string to a continent via `normalise_country`, a custom normaliser in the
    dataset generator; substituting country_converter's fuzzy matching
    resolves the same strings differently and would produce a number that
    looks authoritative while answering a different question. The generator
    arrives with `sample`, and the continent figures with it.
    """
    from serentec.utils.strings.dominant_script import dominant_script

    results = {}
    for tier in tiers.TIERS:
        records = tiers.load(tier)
        scripts = Counter(dominant_script(str(r.get("input", ""))) for r in records)
        total = len(records)
        results[tier] = {
            "script": {k: round(100.0 * v / total, 1) for k, v in scripts.most_common()},
            "records": total,
        }
    return results


def rows() -> List[Row]:
    reference = loads((paths.data() / "expected/table3.json").read_text(encoding="utf8"))
    computed = component_existence()
    return [
        Row(component, tier,
            computed[tier][component],
            reference["analysis_output"][component][tier],
            reference["published"][component][tier])
        for component in tiers.COMPONENTS
        for tier in tiers.TIERS
    ]


def run(as_json: bool = False, verbose: bool = False) -> int:
    from messy_streets.cli import EXIT_OK

    reference = loads((paths.data() / "expected/table3.json").read_text(encoding="utf8"))
    table = rows()

    with workspace.vendored_tree():
        spread = distributions()

    if as_json:
        print(dumps({
            "layer": "L0",
            "paper_tables": [3],
            "component_existence": [r._asdict() for r in table],
            "distributions": spread,
            "method_note": reference["method"],
            "paper_vs_its_own_analysis": reference["disagreements"],
            "exit_code": EXIT_OK,
        }, indent=2))
        return EXIT_OK

    print("\nTable 3 — address component existence, in percent")
    print("computed over all 10,000 records of each released tier\n")
    print(f"  {'component':<11}{'tier':<9}{'released':>10}{'analysis':>10}{'paper':>8}   note")
    print("  " + "-" * 66)
    for row in table:
        note = ""
        if abs(row.analysis - row.published) > 0.05:
            note = "paper differs from its own analysis output"
        elif abs(row.released_vs_published) > 0.05:
            note = f"{row.released_vs_published:+.1f} pp vs paper"
        print(f"  {row.component:<11}{row.tier:<9}{row.released:>10.1f}{row.analysis:>10.1f}"
              f"{row.published:>8.1f}   {note}")

    print(f"\n  released : this artefact, all 10,000 records per tier")
    print(f"  analysis : the paper's method — {reference['provenance']['gold']['observations']} "
          f"observations sampled from a benchmark slice")
    print(f"  paper    : as printed in Table 3")
    print("\n  Source databases differ by tier: "
          + ", ".join(f"{tier} from {meta['database']}"
                      for tier, meta in reference["provenance"].items()))

    print("\n\nBiases — script distribution over all 10,000 records of each tier")
    print("the paper reports Latin at 98% gold, 96% silver, 94% raw\n")
    for tier in tiers.TIERS:
        scripts = spread[tier]["script"]
        top = ", ".join(f"{k} {v}%" for k, v in list(scripts.items())[:5])
        print(f"  {tier:<8} {top}")
    print("\n  Continent shares are not computed. The paper resolves them through a")
    print("  normaliser built inside the dataset generator's constructor, which cannot be")
    print("  used standalone without the generator's full environment; substituting plain")
    print("  fuzzy matching answers a different question. See TODO.md.")

    print(f"\n{len(reference['disagreements'])} of {len(table)} Table 3 cells differ between "
          "the paper and the analysis output that produced it.")
    print("See ARTIFACT.md, Known deviations.")
    return EXIT_OK
