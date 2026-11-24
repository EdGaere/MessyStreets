# geocoder.ca on MESSY STREETS: our test results

geocoder.ca was not in the paper. We (Geolytica, which runs geocoder.ca and geocode.xyz) tested it against the benchmark ourselves, using the paper's scoring. We would welcome the authors repeating the test, to see whether the results hold up.

## How we tested

- **Records:** the North American records with a `target`: 13,832 in all, of which 1,267 are Canadian. The rankings below use the 1,546 of these that the paper ran on every geocoder.
- **Queries:** each record's `input` was sent verbatim to the free-text endpoint (`https://geocoder.ca/?locate=<input>&geoit=XML&json=1`), with no country hint and no preprocessing.
- **Dates:** the US records on 2026-11-22 and the Canadian records on 2026-11-24. The other geocoders' answers are the paper's own, from June 2026, so the dates differ.
- **Scoring:** as in the paper, a hit is an answer in the same geohash-6 cell as `target`. All scores below use the published `target`, not the corrections in this folder, unless marked.

## Results

On the 1,546 US and Canadian records that the paper ran on every geocoder, geocoder.ca ranks 5th of the 14 geocoders at 86.7%. On the 144 Canadian ones it ranks 2nd, at 93.1% against Google's 93.8%.

| Geocoder | US and Canada (1,546) | US (1,402) | Canada (144) |
| --- | --- | --- | --- |
| Google | 89.7% | 89.3% | 93.8% |
| ArcGIS | 89.3% | 89.0% | 91.7% |
| HERE | 88.5% | 88.4% | 89.6% |
| Mapbox | 87.8% | 88.1% | 84.7% |
| **geocoder.ca** | **86.7%** | **86.0%** | **93.1%** |
| Azure Maps | 85.8% | 85.7% | 86.8% |
| TomTom | 85.5% | 85.4% | 86.1% |
| Geoapify | 82.5% | 82.0% | 86.8% |
| OpenCage | 75.8% | 75.7% | 76.4% |
| Pelias | 74.9% | 76.5% | 59.7% |
| MapQuest | 64.7% | — | 88.5% (113 answered) |
| geocode.xyz | 63.6% | — | — |
| Photon | 55.8% | 54.9% | 65.3% |
| Nominatim | 54.2% | 54.9% | 47.2% |

MapQuest answered only part of the records in the paper's runs, and geocode.xyz was run only on the combined set, so some cells are empty.

**Are the differences real?** On the 144 Canadian records, a paired exact sign test does not separate geocoder.ca from Google (p = 1.0), ArcGIS (p = 0.69) or HERE (p = 0.18). geocoder.ca is ahead of Azure Maps, Geoapify, TomTom, Mapbox and the open-source geocoders at p < 0.05. With 144 records, the 95% intervals are about ±5 points wide.

**On all 13,832 North American records** (which the paper's geocoders were not run on), geocoder.ca scores 83.0%. Against the corrected targets in this folder it scores 83.7%: 86.4% on the Canadian records and 83.4% on the US ones.

## Repeating the test

geocoder.ca has a free endpoint that needs no key, limited to about one request a second. We can share our run scripts and the raw answer for every record.
