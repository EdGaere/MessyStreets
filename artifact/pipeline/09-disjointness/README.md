# Stage 9 — disjointness repair

The one stage of the pipeline that was never code.

`v0/readme.md` records it as roughly thirty DuckDB statements, run by hand,
per tier: find duplicate ids, back them up to a `deleted` table, delete them,
select *n* replacements from the corresponding 1,000-record tier that overlap
nothing, insert them, re-check the count. Gold needed 5 replacements, silver
15, raw 2.

Two consequences, both visible in the released data:

**The replacements were not deterministic.** The statements select with
`LIMIT n` and no `ORDER BY`, so which records were inserted depended on scan
order at the moment they ran.

**The pass came after the benchmark slices were cut.** Nine addresses appear in
a shipped slice but not in the tier it was drawn from; two of them are still
sitting in the gold tier's own `deleted` table. `messy-streets sample` reports
this.

`repair.py` is the same procedure written down — ordered by id, seeded,
idempotent, and reporting what it would change before changing anything. It
does not reconstruct the original repair; that is not recoverable from what
survives. It makes the method inspectable, and it means the next tier built
this way does not inherit the same problem.

```sh
python3 repair.py --data-dir /path/to/tier/databases
```

`--apply` is guarded against the released tiers: they are already repaired, and
re-running the pass would produce a different tier from the one the paper
describes.
