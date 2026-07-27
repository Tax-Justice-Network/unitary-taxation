# Manual resource-data sources

Two hand-curated reference tables feed `4_correcting_cbcr_for_resource_payments.py`
(and `1_8_resource_payments_by_hq_source.py`) for source countries with no / thin
EITI or GRD coverage. **Both are STARTER tables — the figures are deliberately rough,
flagged per row with a `confidence` column, and meant to be refined.** This file
records where the numbers came from so they can be checked and improved.

---

## 1. `data/raw/resources/resource_profit_tax_rate.csv`

Combined *effective extractive profit-tax rate* by `source_iso3 × commodity` — used to
convert the "post-profit" resource take (corporate income tax + special petroleum/mining
surtaxes + windfall levies, all levied on profit) into the profit base it was levied on:
`base = post_profit_take ÷ rate`. Royalties / licence & area fees / signature & production
bonuses / production entitlements are **not** in this table — those are pre-profit
(1-for-1 reduction of reported profit) and handled separately. Where a `(source_iso3,
commodity)` pair is absent, `4_…py` falls back to the source country-year's statutory
CIT rate (the `cit` column of `cbcr_main_disaggregated.csv`).

**Sources (general, applied to all rows):**
- IGF/IISD *Global Tax Expenditures / mining & petroleum fiscal-regime* materials, incl.
  the IGF-ATAF 2022 note *"Variable royalties — an answer to volatile mineral prices"*
  (a copy is in `docs/extractive/IGF_ATAF_2022_variable-royalties-an-answer-to-volatile-mineral-prices.pdf`).
- IMF Fiscal Affairs Department country fiscal-regime notes and Article IV staff reports.
- EY / PwC / Deloitte *Global Oil & Gas Tax Guide* and *Mining Tax Guide* series
  (headline ring-fence CT rates, supplementary charges, PRRT, special participation, PPT).
- National budget documents and revenue-authority publications where available.
- The `source_note` column on each row states the specific regime components used
  (e.g. NOR = "CIT 22% + special petroleum tax 56%"; GBR = "ring-fence CT 30% +
  supplementary charge 10–32% (+ energy profits levy from 2022)"; NGA = "PPT 50%
  deepwater PSCs to 85% onshore JVs"). Rates are period-average headline regime rates,
  **not** statutory-year-by-year — `confidence` is `high` only for NOR/GBR-type
  well-documented regimes and `low`/`very-low` for opaque NOC states.

Rows with `source_iso3` ∈ {`oil_gas`,`minerals`,`coal`} are commodity-wide *default*
fallbacks (0.45 / 0.32 / 0.30) for the rent-proxy step in `1_8`; `4_…py` ignores them
(it merges on real ISO3 codes only).

---

## 2. `data/raw/resources/manual_resource_revenue.csv`

Resource-related *government revenue* (USD billions, per `source_iso3 × commodity × year`,
2016–2022), split into `frac_pre_profit` / `frac_post_profit` / `frac_equity` (sum to 1),
with a `domestic_share` (the fraction lands on the source country's own NOC/state firms,
i.e. the `parent == partner` CbCR cell; the rest is distributed to IOC HQ countries by
`hq_share_<commodity>` in `1_8`).

**These per-year totals are ballpark estimates** assembled from the headline figures
below plus general knowledge of each fiscal regime; treat anything tagged
`low` / `very-low` confidence as order-of-magnitude only. The split fractions are
regime-based judgement calls (royalty vs CIT-type vs state-dividend), not measured.
Each row's `source_note` summarises the regime; this list records the headline data
points behind the levels:

| Country (commodity) | Conf. | Headline figures / sources used |
|---|---|---|
| CHL minerals | low-med | COCHILCO (Comisión Chilena del Cobre) and CEIC "Chile government mining revenue" series; copper-price-driven; pre-2024 *Impuesto Específico a la Actividad Minera* on operating margin. Web search 2026-05: COCHILCO/CEIC headline figures. |
| SAU oil_gas | med-high for 2018–22 (precise dataset); medium for 2016–17 (chart) — split estimated throughout | **Saudi Ministry of Finance.** 2018–2022 oil revenue from the machine-readable budget dashboard export — `data/raw/context/sau_mof_budget_dashboard_2026.csv` (rows: Category="Oil Revenue & Non-oil Revenue", Classification="Oil Revenue", Type="Actual"): SAR bn 2018 **611.239** / 2019 **594.424** / 2020 **413.05** / 2021 **562.191** / 2022 **857.272** (also 2023 754.562 / 2024 756.624 / 2025E 590.131). 2016–2017 (SAR **334** / **436** bn) read off the "Oil and Non-Oil Revenues" chart on p.37 of the FY2026 Budget Statement PDF (`https://www.mof.gov.sa/en/budget/2026/BudgetStatementDocs/Eng_2026.pdf` — that chart's full series: oil SAR bn 2010 670 / 2011 1,034 / 2012 1,145 / 2013 1,035 / 2014 913 / 2015 446 / 2016 334 / 2017 436 / 2018 611 / 2019 594 / 2020 413 / 2021 562 / 2022 857 / 2023 755 / 2024 757 / 2025E 590; totals 2016 519 / 2017 692 / 2018 906 / 2019 927 / 2020 782 / 2021 965 / 2022 1,268). Converted at the pegged SAR 3.75/USD → oil USD bn 2016–22 ≈ **89 / 116 / 163 / 158 / 110 / 150 / 229**. This "oil revenues" line is the government's *total* oil take (Aramco royalties + the 20% corporate income tax, cut from 50/85% in 2017 + state dividends; dividend payout ≈ 36% in 2017–18 rising toward ≈ 48% under the 2020–24 commitment). The **0.25 / 0.20 / 0.55** pre/post/equity split (retuned 2026-06 toward equity — Aramco is ~98% state-owned, so the dominant flow is dividends + royalties and the CIT is only 20%; the prior post-heavy split drove `profit_loss_excl_resource` negative) is a regime-based estimate, not from the source. |
| RUS oil_gas | med-high (total sourced; split estimated) | **Russian Ministry of Finance, "Brief annual information on federal budget execution (bln. rub.)"** (`https://minfin.gov.ru/en/statistics/fedbud?id_4=119255-brief_annual_information_on_federal_budget_execution_bln._rub.`; data file `…/2026/05/main/3_fedbud_month_eng_—_year.xlsx`). "Oil & gas revenues" line, bln RUB: **2016 4,844.0 / 2017 5,971.9 / 2018 9,017.8 / 2019 7,924.3 / 2020 5,235.2 / 2021 9,056.5 / 2022 11,586.2** (2023 8,822.3). Converted at average-year USD/RUB (≈ 67.0 / 58.3 / 62.7 / 64.7 / 72.1 / 73.7 / 68.5) → oil&gas USD bn 2016–22 ≈ 72 / 102 / 144 / 122 / 73 / 123 / 169. **Important scope note:** this federal line = mineral-extraction tax (НДПИ/MET) + oil/gas/products export duties (both revenue/volume-based ⇒ pre-profit) + the profit-based hydrocarbon "additional income tax" (НДД, since 2019). It **excludes** the regional profit tax on oil & gas companies and Gazprom/Rosneft state dividends (those sit in the budget's "non-oil&gas revenues" line). Hence the split here is set ≈ 0.88 pre / 0.12 post / 0.0 equity — and the equity/regional-profit-tax slice of Russia's resource take is *not* captured by this row. |
| AUS minerals / coal / oil_gas | medium | Australian state royalty collections (esp. WA iron-ore royalty, NSW/Qld coal royalties) + Commonwealth Petroleum Resource Rent Tax + company tax. Web search 2026-05: WA iron-ore royalties ≈ AUD 7.6 bn (2019–20); PRRT ≈ AUD 1–2 bn/yr (spiking later); 2022 coal-royalty windfall (Qld progressive tiers). |
| KWT / ARE / QAT / IRN / DZA / OMN / LBY oil_gas | low / very-low | OPEC Annual Statistical Bulletin (production & export values), IMF Article IV reports (fiscal oil revenue), and national budget data where published. NOC ownership shares and JV partner structures from EY/PwC oil & gas guides and company reports (ADNOC concessions, Qatari LNG JVs, PDO 60/34/4, Sonatrach ≥51%, NOC Libya JVs). |
| BRA oil_gas / minerals | low-med | ANP (Agência Nacional do Petróleo) royalty + special-participation + signature-bonus statistics; ANM (Agência Nacional de Mineração) CFEM royalty collections; Petrobras and Vale annual reports for the state-dividend side. CIT 34%. |
| CAN oil_gas / minerals | low / low-med | Alberta Energy / provincial royalty & Crown-lease revenue reports; provincial mining-tax data; federal + provincial CIT. Very price-volatile (2020 collapse, 2022 spike). |
| USA oil_gas / coal / minerals | low | DOI/ONRR (Office of Natural Resources Revenue) federal royalties, bonuses, rents + state severance-tax collections; federal CIT 21% + state CIT. Hardrock mining has ≈ no federal royalty (General Mining Act 1872). |
| CHN oil_gas / coal / minerals | low-med (resource tax sourced; CIT/dividends grossed up) | **NBS *China Statistical Yearbook*, table 7-2** ("Government Finance — revenue by item", general public budget = central + local), **"Resource Tax / 资源税"** row, in ¥100 million (yearbook YYYY covers FY YYYY−1; URL pattern `https://www.stats.gov.cn/sj/ndsj/YYYY/indexeh.htm`; figures saved in `data/raw/resources/CHN_resource_tax_statistical_yearbooks.txt`): 2016 **950.83** / 2017 **1,353.32** / 2018 **1,629.90** / 2019 **1,821.64** / 2020 **1,754.76** / 2021 **2,288.16** / 2022 **3,388.61** (¥100 mn). FY2018 also confirmed from the MoF final-accounts page (`https://www.mof.gov.cn/en/data/202011/t20201126_3630386.htm`, "Resource Taxes Final 1,629.90"). ÷ average RMB/USD → resource tax ≈ USD **14.3 / 20.0 / 24.6 / 26.4 / 25.4 / 35.5 / 50.3 bn** for 2016–22. The resource tax is the **pre-profit** royalty-like component (a revenue-based extraction tax, ~1.5–6 % of value). The **post-profit** (sector corporate income tax, 25 %, on CNPC/Sinopec/CNOOC/Shenhua/etc.) and **equity** (State-Capital-Operation budget — extractive-SOE dividend remittances, low payout) components are *not separately sourced*: the row's total is grossed up assuming resource tax ≈ 40 % of the total take (⇒ frac_pre 0.40 / frac_post 0.45 / frac_equity 0.15), and the resource tax is split across commodities oil_gas / coal / minerals ≈ 0.42 / 0.43 / 0.15. `domestic_share` 0.92 (China's extractive sector is overwhelmingly Chinese-SOE-headquartered ⇒ most of this nets out inside China's own CbCR diagonal cell). **UPDATED 2026-06:** the post-profit component is now sourced from extractive-SOE current income-tax (PetroChina/Sinopec/CNOOC/Shenhua/Yankuang/Zijin/Chalco annual reports) and the equity component from the MoF central state-capital-operation budget "resource-type" remittance (a sector-wide proxy incl. power/telecom; 2017 not separately published → equity 0 that year), replacing the old 40/45/15 assumption. Per-commodity split stays the 0.42/0.43/0.15 NBS allocation. |
| TKM oil_gas | very-low | IMF Article IV and EITI-adjacent estimates; Turkmengaz/Turkmennebit 100% state; gas exports largely to China. Highly uncertain. |
| BHR oil_gas | low | Bahrain budget data; Bapco/Banagas state ownership; includes Bahrain's share of the Abu Sa'fa field (operated by Saudi Aramco). |
| MAR minerals | low | OCP Group annual reports (phosphates; ≈ 95% state-owned) — mostly CIT + dividends to the state, small revenue-based royalties. |
| VEN oil_gas | very-low | OPEC ASB + IMF estimates; PDVSA; production and fiscal capacity collapsed over 2016–2022. Highly uncertain. |
| ZAF minerals | low-med (royalty sourced; CIT estimated) | **SARS** "Mineral and Petroleum Resources Royalty" (MPRR) collections from the SARS *Tax Statistics* series (`https://www.sars.gov.za/types-of-tax/mineral-and-petroleum-resource-royalty/`): ZAR 2.1 bn in 2016/17, ZAR 14.3 bn in 2020/21, ZAR 28.5 bn in 2021/22 (doubled on PGM/iron-ore/coal prices), ZAR 25.3 bn 2022/23, ZAR 16.0 bn 2023/24 — interpolated to a calendar-year MPRR series of roughly ZAR 3/4/7/7/14/28/25 bn for 2016–22. The mining-sector corporate income tax (the bulk of the take — South Africa has no large mining SOE, so equity ≈ 0) is an *estimate* of ≈ ZAR 10/15/18/18/25/50/50 bn (low CIT in the 2016 commodity trough, big jump in the 2021–22 PGM boom). Total ÷ average ZAR/USD → ≈ USD 0.9/1.4/1.9/1.7/2.4/5.3/4.6 bn. Replaces the rent-proxy estimate, which was running ≈ 2× too high for ZAF. **UPDATED 2026-06:** the mining-sector CIT is now sourced (not estimated) from SARS *Tax Statistics* Table A3.4.2 "company tax assessed by economic activity — Mining & quarrying", and the MPRR royalty from Table 6.7/6.9, all years except 2016 MPRR (not published by commodity). High confidence. |

**Data-gap countries still on the rent-proxy fallback (low confidence) — candidates for a manual figure:** India (≈ $18 bn/yr rent-proxy; real production-side resource revenue — oil/gas royalties + crude-oil cess + PSC profit-petroleum + coal royalties + coal GST-compensation cess + metal royalties + ONGC/OIL/Coal-India/NMDC dividends — is closer to ≈ $10–15 bn/yr; the IISD "2.3% of GDP / 11.3% of govt revenue in 2017" figure includes petroleum-product *excise*, a consumption tax, and must NOT be used as-is — see `https://www.iisd.org/system/files/publications/beyond-fossil-fuels-india.pdf`), South Africa (now done — see above), Poland (coal + KGHM copper), Uzbekistan (gold/gas/copper), Zimbabwe (PGMs/gold). And the GRD-distributed ones worth upgrading: Malaysia (Petronas — huge; GRD figure ≈ $10 bn/yr), Angola & Egypt (oil; GRD covers them but the pre/post/equity split is rough), Brunei, Equatorial Guinea, Botswana (diamonds, Debswana 50/50 with De Beers).

**Primary documents pulled directly (2026-05):**
- Saudi MoF FY2026 Budget Statement PDF — p.37 "Oil and Non-Oil Revenues" chart (numbers read off the chart). URL in the SAU row above.
- Russian MinFin "brief annual federal budget execution" page + its `3_fedbud_month_eng_—_year.xlsx`. URL in the RUS row above.

**Web searches performed (2026-05-11/12) and what they returned:**
1. *Chile government mining revenue 2016–2022 copper* → COCHILCO / CEIC headline series; specific mining-tax structure.
2. *Saudi Arabia oil revenue government budget 2016–2022* → 2022 oil revenue ≈ SAR 857.3 bn; Aramco fiscal terms (later confirmed & extended from the MoF p.37 chart — see SAU row above).
3. *Russia oil and gas budget revenue 2016–2022 rubles* → 2022 oil & gas budget revenue ≈ RUB 11.6 tn; MET/export-duty vs profit-tax split (later confirmed & extended from the MinFin table — see RUS row above).
4. *Australia mineral royalties / petroleum resource rent tax revenue 2016–2022* → WA iron-ore royalties ≈ AUD 7.6 bn (2019–20); PRRT ≈ AUD 1–2 bn/yr; Qld coal-royalty tiers.

Everything else in the table is general fiscal-regime knowledge (OPEC ASB, IMF Article IV,
EY/PwC/Deloitte tax guides, company annual reports) rather than a single citable figure —
which is exactly why these rows carry `low`/`very-low` confidence and should be replaced
with EITI- or GRD-sourced numbers wherever those become available.

---

## 2026-06 sourcing pass — estimates replaced with primary sources

A dedicated pass replaced most of the `low`/`very-low` flagged rows with figures from
official fiscal documents. The authoritative per-row source now lives in the
`source_note` column of `manual_resource_revenue.csv`; this is the summary.

**Now sourced (confidence raised):**
- **Gulf / OPEC oil & gas** — IMF Article IV fiscal-hydrocarbon tables and national budgets:
  **UAE** (CR19/35, CR23/223 — oil income tax / royalty / ADNOC transfers), **Qatar**
  (CR19/146, CR22/175, CR24/44), **Algeria** (CR18/168, CR23/69 — post-profit TRP/IBS
  dominant), **Oman** (Central Bank of Oman Fiscal Performance Paper), **Libya 2018–22**
  (CR23/201 + CBL/NOC actuals), **Kuwait** (MoF closing accounts). **Iran** derived from
  EIA export value × IMF government-take share (still low conf).
- **China** — post = extractive-SOE current income tax (company ARs); equity = MoF
  state-capital-operation budget resource-type remittance (proxy). Replaces 40/45/15.
- **South Africa** — SARS MPRR royalty + mining-sector CIT assessed.
- **Australia** — state coal/iron-ore royalties (QLD/NSW budgets, WA DMIRS Digest) + ATO
  Taxation Statistics company tax by industry + Commonwealth PRRT.
- **Canada oil & gas** — StatCan Table 25-10-0065-01 (royalties + fed/prov income tax;
  negative in 2016/17/20 loss years).
- **Mexico** — Pemex 20-F income-taxes-and-duties note (DUC/derechos + ISR petrolero;
  no dividend → equity 0). Materially lower than the prior estimate.
- **Morocco** — OCP Group IFRS statements (current tax + state dividends at 94.12%).
- **India coal** — PIB year-wise royalty + Provisional Coal Statistics + Coal India/SCCL
  income tax + Coal-India dividend-to-GoI + GST compensation cess.
- **Russia** — equity slice ADDED = Gazprom (state 50.23%) + Rosneft (40.4%) dividends,
  on top of the existing MinFin MET/export-duty/NDD total.

**Could NOT be sourced (kept as estimate / flagged for manual collection):**
- **Turkmenistan** — no published government hydrocarbon fiscal data (only China gas-import
  values, which are not fiscal cash). Prior very-low estimate retained.
- **Venezuela 2019–2022** — fiscal take not recoverable post-sanctions (export proxies only,
  much never reached the treasury). 2016–2018 sourced from OPEC ASB.
- **Bahrain** — no better source found; prior estimate retained.
- **USA sector CIT** — federal royalties/bonuses are exact (ONRR) but the oil/gas/coal/mineral
  corporate income tax is not cleanly available per commodity; prior estimate retained.
- **Brazil oil & gas private-operator CIT** — ANP royalties (pre) and Petrobras→Union
  dividends (equity) are sourced, but the private-operator income tax (post) could not be
  isolated. **Brazil minerals** post is a Vale-20-F proxy (upper bound).
- **India non-fuel minerals** — Hindustan Zinc tax+dividend audited, but the non-fuel
  royalty/DMF + NMDC figures are reconstructed and the Tata/JSW/Vedanta mining-segment CIT
  and dead rent are not separable.
- **China 2017 SOE dividends** — no MoF category breakdown that year (equity set 0).
- **Canada minerals**, **Laos**, **Lesotho** — no clean annual primary series (Lesotho has a
  separate `LSO_revenue_extracted.csv`).

---

## How these feed the pipeline

`1_8_resource_payments_by_hq_source.py` builds `resource_payments_by_hq_source_yearly.csv`
with a source-priority cascade per `(source country, commodity, year)`:
1. **EITI bilateral** — matched company payments → HQ country (scripts `1_6`→`1_7`).
2. **EITI summary** — country-year totals from the EITI API summary endpoint, split to
   HQs by `hq_share_<commodity>` with `domestic_share`.
3. **GRD** — `grd_resource_revenue.csv` (UNU-WIDER Government Revenue Dataset), same split.
4. **Manual** — `manual_resource_revenue.csv` (this file), same split.
5. **Rent proxy** — estimated rent × assumed rate, same split (last resort).

`4_correcting_cbcr_for_resource_payments.py` then uses `resource_profit_tax_rate.csv`
to turn the post-profit take into a profit base, and writes the corrected-profit
columns onto the three resource-corrected datasets (`cbcr_main_excl_resource.csv`,
`cbcr_main_incl_resource.csv`, `cbcr_main_excl_resource_floored.csv` — see the
four-dataset scheme in CLAUDE.md; the old combined `cbcr_main_resource_corrected.csv`
is retired).

## Angola (AGO) — oil & gas  [added 2026-07-19]

Angola joined EITI in 2022 and backfilled FY2020–2022, so it is **absent from our
EITI API pull** (which predates accession) — the reports live only in
`data/raw/resources/eiti_reports/Angola/`. The manual entry uses:
- **Stream split** from the EITI Summary Data (`Part 4 - Government revenues`,
  State General Account): `FY2020-2021 Angola Summary Data.xlsx` (FY2021) and
  `2022_Summary-Data_ITIE-AO.xlsx` (FY2022). Mapping: **concessionary sales /
  PSA profit-oil + mining royalties → pre-profit**; **petroleum income tax →
  post-profit**; **Angola LNG participation → equity**. FY2021 = pre .68 / post
  .29 / eq .03; FY2022 = pre .56 / post .44 (petroleum income tax rises with the
  high 2022 oil price). The FY2021 split is applied to 2016–2021; FY2022 to 2022.
- **Total** = the GRD LCU+FX magnitude (GRD's own gdp_lcu × %, ÷ period-average
  FX), i.e. GRD magnitude + EITI split — the GRD figure alone had misclassified
  Angola's PSA/concession revenue as "resource_taxes" (→ would have been ~all
  post-profit; the EITI streams show it is ~68% pre-profit rent).
- **`domestic_share` = 0.45** (Sonangol; Angolan production is majority
  foreign-major-operated under PSAs) — medium confidence.

## Bolivia (BOL) — gas  [added 2026-07-19]

Not an EITI member; the split is read from **IMF Article IV fiscal tables**
(*Operations of the Combined / Nonfinancial Public Sector*) and the 2010 Selected
Issues chapter "Hydrocarbon Revenue Sharing Arrangements":
- The IMF defines hydrocarbon revenue as **IDH + royalties (→ pre-profit)** plus the
  **YPFB / public-enterprise operating balance (→ equity)**. IDH (32%) + royalty (18%)
  = ~50% of gross gas value, a production-based rent. **Hydrocarbon corporate income
  tax (IUE) is not separately tracked** by the IMF and is folded into general Direct
  Taxes → **post ≈ 0**.
- **Year-varying split** (PRE / EQUITY) straight from the tables, POST = 0:
  2016 .80/.20, 2017 .77/.23, 2018 .74/.26, 2019 .74/.26, 2020 .76/.24, 2021 .86/.14,
  2022 .62/.38 (YPFB's surplus swings with gas prices). Sources: `BOL_IMF4_2018.pdf`
  Table 3 (p33); `BOL_IMF4_2024.pdf` Tables 4a/4b (p34-35); `BOL_IMFSI_2010.pdf`
  ch.II (p9). Files in `data/raw/resources/resource_profits_manual_sources/imf/` (BOL_IMF4_*, BOL_IMFSI_*) and `government/` (BOL_InformeAT_2025).
- **Total** = GRD LCU+FX magnitude. **`domestic_share` = 0.50** (YPFB-aggregated,
  private JV operators Petrobras/Repsol/Total) — medium-high confidence.

## Egypt (EGY) — oil & gas  [added 2026-07-19]

Not an EITI member; split from **IMF Budget Sector Operations tables** (identical
oil-revenue footnote across vintages). Streams: EGPC CIT, foreign-partner CIT,
royalties, petrol-product excises, EGPC dividends.
- Mapping: **royalties + petrol excises → pre-profit (0.40)**; **EGPC CIT +
  foreign-partner CIT → post-profit (0.53)**; **EGPC dividends → equity (0.07)**.
  EGPC's payment is *collected as a corporate income tax*, so it is classified as
  POST rather than re-labelled equity; the correction's
  `resource_profit_base = max(post/effective_rate, equity)` prevents the state
  production-share profit from being double-counted across the two channels.
- Constant split (the identifiable oil-revenue block is stable ~1.2–2.0% of GDP).
  Sources: `EGY_IMF4_2021.pdf` T3a/3b (p28-29, footnote 5); `EGY_IMF4_2017.pdf`
  T4 (p35); `EGY_IMF4_2025.pdf` T3a (p46-47). Files in `.../resource_profits_manual_sources/imf/` (EGY_IMF4_*, EGY_IMFSI_*).
- **Total** = GRD LCU+FX magnitude. **`domestic_share` = 0.50** (EGPC + foreign majors
  Eni/BP/Apache/Shell) — medium confidence.

## Vietnam (VNM) — oil & gas  [added 2026-07-19]

Not an EITI member; split from **IMF General Government fiscal tables** (the oil-revenue
line decomposes into exactly two sub-lines, stable across 2013–2024):
- **Natural-resource tax → pre-profit (0.26)** + **oil corporate income tax →
  post-profit (0.74)**. **PetroVietnam's production share is NOT in the oil-revenue
  line** (it flows through PVN as ordinary SOE dividends in non-tax "Other revenue",
  not oil-attributed) → **equity = 0**. The Selected Issues papers contain no oil
  fiscal chapter.
- Constant split. Sources: `VNM_IMF4_2018.pdf` Tables 4a/4b (p37-38); corroborated
  in `VNM_IMF4_2022.pdf` (p38-39) and `VNM_IMF4_2024.pdf` (p37-38). Files in
  `.../resource_profits_manual_sources/imf/` (VNM_IMF4_*, VNM_IMFSI_*).
- **Total** = GRD LCU+FX magnitude. **`domestic_share` = 0.55** (PetroVietnam +
  Vietsovpetro JV + foreign contractors) — high confidence on the split.

## Manual foreign HQ shares (`manual_foreign_hq_shares.csv`)  [added 2026-07-21]

Hand-curated splits of the **foreign** slice (1 − `domestic_share`) of a source
country's resource take across HQ countries, used by `1_8` when neither EITI
bilateral nor operator P2G data cover the `(source, commodity, year)` cell —
without them the foreign take is spread by the **global** Orbis HQ-share table,
which sends corrections to HQ countries with no presence in the source country
(and no CbCR line to correct), while the actual operators' HQ countries keep
their resource profits uncorrected.

| Source | Foreign split | Basis / sources |
|---|---|---|
| SSD oil_gas | CHN 0.50 / MYS 0.35 / IND 0.10 / EGY 0.05 | DPOC (blocks 3/7, ~80% of output): CNPC 41% + Sinopec 6%, Petronas 40%, Tri-Ocean (EGY) 5%, Nilepet 8 (domestic); GPOC (1/2/4): CNPC 40, Petronas 30, ONGC 25; SPOC (5A): Petronas 68, ONGC 24. Production-weighted. EIA South Sudan Country Analysis Brief; IMF CR 19/153. Confidence: medium. |
| SDN oil_gas | CHN 0.55 / MYS 0.30 / IND 0.15 | CNPC-led GNPOC / PetroEnergy consortia post-2011; EIA Sudan brief. Confidence: low-med. |
| GNQ oil_gas | USA 0.75 / GBR 0.20 / FRA 0.05 | ExxonMobil (Zafiro, sold to Trident Energy (GBR) 2021), Marathon (Alba/EG LNG), Noble→Chevron, Kosmos; EIA GNQ brief; World Oil 2024. Confidence: low-med. |
| BWA minerals | GBR 0.90 / USA 0.05 / ZAF 0.05 | Debswana = 50/50 GoB–De Beers; De Beers 85% Anglo American plc (GBR). Khoemacau = Cupric Canyon (US PE) in window. Confidence: medium. |
| BRN oil_gas | GBR 0.85 / FRA 0.10 / MYS 0.05 | Brunei Shell Petroleum 50% Shell plc; TotalEnergies Maharaja Lela. (In practice mostly superseded by the Shell/Total operator-P2G override, which outranks it.) Confidence: medium. |

Shares are renormalised within the foreign slice; blank `year` = all years
2016–2022. Extend this table whenever script 4's
`resource_correction_unmatched_cells.csv` shows material foreign volume being
dropped for a source country with a documented operator mix — candidates
remaining: SAU / KWT / IRN foreign slivers (arguably ≈100% domestic → a
`domestic_share` question, not a split question), UZB (Lukoil/CNPC), NAM
(De Beers + CNNC/Paladin/Orano uranium), LAO (MMG/PanAust).
