## MESSY STREETS
Edward Gaere and Florian von Wangenheim | June 2026

### Introduction
MESSY STREETS is a benchmark for evaluating geocoders on verbatim web addresses, with existence verification and controlled measurement of surface-form divergence.

MESSY STREETS is released in three tiers of 10K records, each drawn without overlap from the 16.8M retained records filtered from the 2024 Web Data Commons (WDC). See paper for details.

### Viewing a file
The files are JSONL, compressed. It's highly recommended to have 'jq' installed for the viewing each address (JSON).

```
# show the first five records
# NOTE: replace tier as required: gold, silver or raw
gunzip -c release_gold_10k_final.jsonl.gz | head -n5 | jq | less

# for the gold and silver tiers, the source and address for the existence verification can be viwed using the following command
# NOTE: the raw tier is not existence verified, that field will not exist
gunzip -c release_gold_10k_final.jsonl.gz | head -n1 | jq .aux.existence

```

### Gold Tier
The gold tier consists of 10K verbatim addresses, each verified for existence and with key components individually verified for plausibility. Below are the first five examples from the gold tier; note that the Japanese address in row 4 is exactly as found in the Web Data Commons 2024 extract, as are all other addresses.

| streetAddress | country | locality | region | PO box | postalCode |
|---|---|---|---|---|---|
| Salle François Rabelais, Rue des Coteaux | France | Smarves | Vienne | | 86240 |
| Calle Javier Echevarria 6 | ES | Castro-Urdiales | Cantabria | | 39700 |
| Via Vicenza 58 | Italy | Roma | | | 00185 |
| 車屋御池下ル梅屋町358 アーバネックス御池ビル　Ｂ１Ｆ | JP | 京都市中京区 | 京都府 | | 6040000 |
| Lower Goat Lane | United Kingdom | Norwich | | | NR2 1EL |


### Silver Tier
The silver tier contains existence-verified addresses whose components are not individually verified. It follows the same construction methodology as the gold tier but omits the second LLM judgment used to verify component validity. In these first five examples from the silver dataset, the tier's characteristics are readily apparent: missing country fields, street abbreviations, countries rendered using local exonyms (e.g., "España"), abbreviated regions (e.g., "SC"), and locality names expressed in non-canonical forms (e.g., "St-Petersburg").

| streetAddress | country | locality | region | PO box | postalCode |
|---|---|---|---|---|---|
| Viale America Latina, 140 | | Frosinone | Lazio | | 03100 |
| Steinheimer Str. 8 |  Germany | Seligenstadt | Hessen | | 63500 |
| Av. el Ras Gran, 13 | España | Guardamar Del Segura | pomorskie | | 03149 |
| 9 Huguenin Ave. | | Charleston | SC | | 29403 |
| 2245 Central Avenue | United States | St-Petersburg | Florida | | 33713 |

### Raw Tier
The raw tier is sampled randomly from the retained WDC records, subject only to the street-component requirement; it is neither existence-verified nor component-verified. Its addresses may or may not exist and may or may not be reasonably geocodable. The raw tier illustrates the "wild west" nature of web-scale address data: corrupt character encodings, embedded escape sequences and control characters, multiline addresses in the street field, suite and unit designators, missing countries, missing postcodes, and spurious values in administrative fields.

| streetAddress | country | locality | region | PO box | postalCode |
|---|---|---|---|---|---|
| n\t\t\t\t\t\t\t\t\t\tJan van Zutphenstraat 77\n\t\t\t\t\t\t\t\t\t | Nederland | \n\t\t\t\t\t\t\t\t\t\tSchiedam\n\t\t\t\t\t\t\t\t\t | Zuid-Holland | | \n\t\t\t\t\t\t\t\t\t\t3119BN\n\t\t\t\t\t\t\t\t\t |
| Chauss�e de Namur, 32 |  | Gembloux | | | 5030 |
| Rue Romy Schneider\r\nZI Nord 3\r\n87280 Limoges |  |  | | | |
| Room No. 47A 3rd Floor 54/56 Ramwadi Kalbadevi Road | India | Search Result | Maharashtra | 400002 |
| 2406 De Soto Ave Unit A | US | Savannah | GA | | 31401 |


### Main Paper
In progress...

### Citation
In progress...
