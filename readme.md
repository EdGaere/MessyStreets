## MESSY STREETS
Edward Gaere and Florian von Wangenheim | June 2026

MESSY STREETS is a benchmark for evaluating geocoders on verbatim web addresses, with existence verification and controlled measurement of surface-form divergence.

MESSY STREETS is released in three tiers of 10K records, each drawn without overlap from the 16.8M retained records filtered from the 2024 Web Data Commons (see paper for details).

### Gold Tier
The gold tier consists of 10K verbatim addresses, each verified for existence, and whose key components have been individually verified for plausibility. In these examples from the gold dataset, note "Italien" in row 3 — that's a live example of the exonym phenomenon occurring in web addresses. 

| streetAddress | country | locality | region | PO box | postalCode |
|---|---|---|---|---|---|
| 21 S Brick Lane | US | Elverson | PA | | 19520 |
| First Fleet Park | AU | Circular Quay | NSW | | 2000 |
| Bichl 43a | Italien | Ratschings | Trentino-Südtirol | | 39040 |
| Neuer Wall 57 | DE | Hamburg | | | 20354 |
| 12614 22 Side Rd | CA | Halton | Ontario | | L7G 4S4 |


### Silver Tier
The silver tier contains existence-verified addresses whose components are not verified. It follows the exact same construction methodology as the gold tier but omits the second LLM judgement verifying component validity. In these examples from the silver dataset, the tier's characteristics emerge: missing country fields, locality misplaced as "Netherlands" instead of a city, and the Oak Bay address with full duplication inside the street field. In the last example, the streetAddress field contains city/region/country instead of an actual street, with a trailing comma.

| streetAddress | country | locality | region | PO box | postalCode |
|---|---|---|---|---|---|
| 626 Monterey Ave, Oak Bay BC V8S 4T9, Oak Bay, BC V8S 4T9 | | Oak Bay | BC | | V8S 4T9 |
| 332 Minnesota St | | St Paul | MN | | 55101 |
| 16 Tadeusza Kościuszki | PL | Sopot | pomorskie | | 81-752 |
| Kerkstraat 7 | | Netherlands | | | 8356DN |
| Cuernavaca, Morelos, Mexico, | MX | Cuernavaca | Morelos | | |

### Raw Tier
The raw tier is sampled uniformly from the retained records, subject only to the street-component requirement; it is neither existence-verified nor component-verified. Its addresses may or may not exist, and may or may not be reasonably geocodable. The raw tier illustrates the 'wild west': missing postcodes, lowercase country codes ("gb"), full country names ("United States", "Spain"), trailing commas and the Spanish "s/n" convention, retail centres instead of street addresses, and a sub-unit embedded in the street field. 

| streetAddress | country | locality | region | PO box | postalCode |
|---|---|---|---|---|---|
| 141 Cherry Springs Lane, Unit 13-B | | Asheville | NC | | 28804 |
| Deerfin Works | gb | Ballymena | County Antrim | | |
| Fulham Broadway Retail Centre | gb | London | | | |
| 1716 Avenue E. | United States | Rosenberg | TX | | 77471 |
| Avda. Ramón Pradera, s/n, | Spain | Valladolid | | | 47009 |


### Main Paper
In progress...

### Citation
In progress...