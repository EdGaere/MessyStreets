# Errata: Canadian ground truth

`canada_truth_corrections_v1.csv` lists 31 records whose `target` disagrees with Canada's official address register, the National Address Register (Statistics Canada, June 2026 edition). They are 31 of the 1,267 Canadian records in the three tiers (2.4%): 20 raw, 6 gold and 5 silver.

| Status | Rule | Records |
| --- | --- | --- |
| `confirmed` | The `target` is 5 km or more from the register's point for the address, and an independent source is within 1 km of the register point. Also smaller gaps confirmed by looking at the map. | 16 |
| `probable` | The same, but the gap is 1–5 km. These should get a second look before they are used. | 15 |

A register match needs the civic number, the street name and the municipality to agree. Two candidates were dropped because the register matched a different street (gold-1483) or the opposite east–west side (silver-295).

## Columns

| Column | Meaning |
| --- | --- |
| `tier`, `idx` | The record, as in `release_<tier>_10k_final.jsonl.gz` |
| `input` | The record's `input`, unchanged |
| `target` | The current geohash |
| `corrected_target` | The register point as a geohash of the same length |
| `corrected_lat`, `corrected_lon` | The register point |
| `km_off` | Distance from the current `target` to the register point |
| `status` | `confirmed` or `probable` |
| `problem`, `evidence`, `date_checked` | What is wrong, the register record and other sources, and when it was checked |

## What the errors have in common

- **In the wrong country:** 5 targets are in the United States (Massachusetts, Washington State twice, Kansas, Indiana). Four of them are 1,000–4,000 km from the address.
- **Unit number first:** 13 of the 31 inputs start with a unit, for example `205 - 9780 197B St Langley BC  CA`, against about 11% of all Canadian records. The unit looks to have been read as the civic number.
- **No postal code:** 17 of the 31 have none, against 12% of all Canadian records.
- **Rounded coordinates:** 2 targets sit on a 0.05° grid (raw-3342, raw-7948), which suggests a town-level fallback.

## Inputs that cannot be scored as street addresses

These records are not in the CSV, because their `target` may be right. A street-level score on them says little about a geocoder.

| Problem | Records |
| --- | --- |
| City or town only, no street | 13, including gold-1092 `Powell River Powell River British Columbia V8A 1B1 Canada` and raw-4648 `Kitchener, ON, Canada ON  Canada ` |
| Four addresses in one input | raw-5859 |
| A US address in the Canadian set | raw-5611 `844 E 3 Mile Rd, Sault Ste. Marie, MI 49783, United States ...` |
| Programming placeholder in place of the address | raw-6692 ``System.Func`1[System.String] Vancouver British Columbia  CA`` |
| Conflicting province | raw-4863 `2560 Boulevard Marcel-Laurin, Montreal, QC Montreal ON  ` |
| Damaged characters | raw-4864, raw-6093 |
| City name in Chinese | raw-483, raw-1329 |
| Canadian address ending in "US" | gold-1483, gold-2960, gold-4768 |

## Suggestions for a revised release

1. Check every Canadian `target` against the National Address Register, and every US `target` against the US Census geocoder. Flag any point more than 1 km from its match.
2. Strip a leading unit number before geocoding the truth, and reject any truth point outside the stated province or state.
3. Reject truth points on a coarse grid, or at a town centroid, for street addresses.
4. Move city-only inputs to a city-level set, and drop or split the multi-address and placeholder inputs.
5. Release corrections as a versioned errata file, so results on both versions can be reproduced.

## Disclosure

This file was prepared by Geolytica, which runs geocoder.ca, one of the geocoders evaluated in the paper. Every correction rests on the official register, not on geocoder.ca's answers. On the corrected points, geocoder.ca's score on the Canadian records rises from 84.1% to 86.4%. Its answers are mentioned in the evidence column only as supporting evidence.
