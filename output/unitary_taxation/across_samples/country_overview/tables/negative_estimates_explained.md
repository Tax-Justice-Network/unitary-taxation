# Negative country estimates — which formula, and why

Headline view: **baseline scenario, destination-based sales, full (imputed) sample**, average ETR, gains taxed at statutory CIT, cumulative 2016–2022. A negative value = profit is reallocated *away* from the country under unitary taxation. Full per-formula detail is in `negative_estimates_detail.xlsx` (Overview tab) and `negative_estimates_overview.csv`.

**111 countries** lose under at least one formula in the full sample (86 in the reported-only sample); **68** lose under *all five* formulas. The reason a country loses, and whether it loses under every formula or only the sales-weighted ones, follows four patterns:

## A. Investment hubs / tax havens — *intended* losses

Investment hub / tax haven — UT reallocates shifted profit back to where real activity and markets are (intended).

*Countries (19):* IRL, ARE, HKG, CHE, SGP, BMU, CYM, VGB, IMN, MUS, PRI, GIB, BRB, PAN, JEY, BHS, GGY, LIE, IOT

| country | employees + payroll | CCCTB | Three-factor | Double-weighted sales | Sales + employees | loses under all? |
|---|---|---|---|---|---|---|
| IRL | -44,198 | -15,470 | -16,789 | -7,815 | -14,756 | yes |
| ARE | -39,277 | -35,688 | -37,020 | -36,399 | -38,678 | yes |
| HKG | -33,976 | -25,426 | -26,564 | -28,197 | -35,016 | yes |
| CHE | -34,722 | -15,574 | -21,150 | -10,314 | -15,563 | yes |
| SGP | -28,334 | -26,390 | -29,263 | -27,372 | -30,686 | yes |
| BMU | -3,772 | -3,631 | -3,643 | -3,684 | -3,809 | yes |
| CYM | -2,524 | -2,478 | -2,489 | -2,506 | -2,557 | yes |
| VGB | -2,380 | -2,102 | -2,106 | -2,174 | -2,394 | yes |

## B. Commodity exporters — produce, don't consume

Commodity exporter — destination sales send extractive profit to buyer markets; recovers once resources are excluded.

*Countries (14):* AUS, AFG, NGA, COD, TCD, PER, IRQ, MLI, MRT, TTO, ETH, BWA, GUY, SYR

| country | employees + payroll | CCCTB | Three-factor | Double-weighted sales | Sales + employees | loses under all? |
|---|---|---|---|---|---|---|
| AUS | 33,544 | -2,219 | -14,464 | -27,499 | -35,813 | no |
| AFG | -11,370 | -10,363 | -10,192 | -10,211 | -10,562 | yes |
| NGA | -9,512 | 12,991 | 14,586 | 22,382 | 20,377 | no |
| COD | -5,940 | -517 | 390 | -184 | -2,574 | no |
| TCD | -5,316 | -3,711 | -3,080 | -3,714 | -4,508 | yes |
| PER | -4,774 | -564 | 3,729 | 306 | -1,160 | no |
| IRQ | -2,838 | 2,247 | 2,417 | 4,432 | 4,361 | no |
| MLI | -2,248 | -1,185 | -757 | -955 | -1,262 | yes |

## C. Production / MNE-home economies

Production / MNE-home economy — books profit at home; destination apportionment moves it toward consumer markets abroad.

*Countries (70):* SAU, CHN, JPN, NOR, KOR, CAN, LBY, IDN, TKM, IRN, DNK, LAO, NPL, AGO, NCL, TUR, DZA, MYS, TJK, NER, NZL, MDV, KAZ, EGY

| country | employees + payroll | CCCTB | Three-factor | Double-weighted sales | Sales + employees | loses under all? |
|---|---|---|---|---|---|---|
| SAU | -57,307 | -192,530 | -192,668 | -265,687 | -270,692 | yes |
| CHN | -172,275 | -115,329 | -35,217 | -52,129 | -7,841 | yes |
| JPN | -59,174 | -31,741 | -51,304 | -47,407 | -78,444 | yes |
| NOR | -27,456 | -45,037 | -51,868 | -58,214 | -62,243 | yes |
| KOR | -43,574 | -10,360 | -18,460 | -9,010 | -25,094 | yes |
| CAN | 24,178 | -3,521 | -10,647 | -19,279 | -24,845 | no |
| LBY | -15,387 | -12,532 | -12,436 | -11,844 | -12,486 | yes |
| IDN | 10,079 | -11,649 | 7,330 | -4,878 | 13,058 | no |

## D. Imputation artefacts — full (gravity) sample only

Imputation artefact — the gravity model imputes implausibly large activity (>2x GDP, non-haven); read the reported column.

*Countries (8):* MAC, REU, TLS, FSM, PRK, TON, WSM, MHL

| country | employees + payroll | CCCTB | Three-factor | Double-weighted sales | Sales + employees | loses under all? |
|---|---|---|---|---|---|---|
| MAC | -5,103 | -6,413 | -6,667 | -7,231 | -7,341 | yes |
| REU | -3,539 | -4,274 | -4,157 | -4,345 | -4,037 | yes |
| TLS | -1,381 | -1,462 | -1,374 | -1,445 | -1,388 | yes |
| FSM | -862 | -968 | -914 | -950 | -880 | yes |
| PRK | 929 | -528 | 244 | -155 | 966 | no |
| TON | -134 | -135 | -130 | -135 | -135 | yes |
| WSM | -122 | -116 | -107 | -112 | -111 | yes |
| MHL | -7 | -6 | -6 | -6 | -7 | yes |

## How to read the formula columns

- **employees + payroll** and **three-factor** have little or no sales weight, so commodity exporters and consumer markets look very different here than under the sales-weighted formulas.
- **CCCTB**, **double-weighted sales** and **sales + employees** put 33–50% weight on (destination) sales, so they move profit toward large consumer markets and away from producers/exporters — that is where category-B and category-C losses are largest.
- A country that loses under **all five** formulas is a robust loser; one that loses only under the sales-weighted formulas is losing specifically because of the destination-sales reallocation.

**Bottom line.** Robust losers in *both* samples are the tax havens (A), big commodity exporters (B) and large production/HQ economies (C). Category-D negatives appear only in the full (imputed) sample and should be read from the reported columns.