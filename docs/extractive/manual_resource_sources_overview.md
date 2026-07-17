# Manual resource-revenue sources — overview & links

This file documents the country-specific sources used to populate
`data/raw/resources/manual_resource_revenue.csv`. Each country has a sub-folder under
`data/raw/resources/country sources/<ISO3>/` containing the raw
PDFs / Excel files cited.

The pipeline cascade (`src/3_extractive_prep/1_8_resource_payments_by_hq_source.py`)
prioritises sources in this order: **EITI bilateral > manual table > GRD > rent-proxy**.
A country can be overridden to `manual > EITI` via the `MANUAL_OVERRIDES_EITI` set
(currently: `{PER, MEX}` — where SUNAT/SHCP data is judged more comprehensive than
EITI bilateral).

A separate ChatGPT conversation (https://chatgpt.com/share/6a04df65-8c38-83eb-9578-ceb1b7ac13b8 —
login-walled; saved by user) collected most of these source links during data sourcing.

---

## United Arab Emirates (ARE) — confidence: **med-high**

Σ 2016–22 ≈ $466B (oil_gas only). Manual entries use IMF Article IV figures
for consolidated UAE hydrocarbon revenue (= Abu Dhabi government share of
ADNOC + tax on oil companies + ADNOC profit transfers). The 6 UAE
Ministry of Finance GFS publications were a useful cross-check but do
**not** separately disclose the hydrocarbon component (Article 14 "Other
revenue" is the upper bound on hydrocarbon take).

Files in `data/raw/resources/country sources/ARE/`:
- `IMF_UAE_2016.pdf` … `IMF_UAE_2022.pdf` — IMF Article IV Consolidated Government Operations tables
- `1areea2025001-source-pdf.pdf` — IMF 2025 Article IV
- `GFS-Data-2025-English-07.04.2026.xlsx` — UAE MoF GFS quarterly 2025 (Q1-Q4)
- `UAE-Government-Finance-Statistics-GFS-data-for-the-Year-2016.pdf` and similar
- Arabic-titled UAE GFS PDFs for 2017, 2018, 2020

Source URLs:
- IMF Article IV (UAE): https://www.imf.org/en/Countries/ARE
- UAE MoF Open Data Portal: https://opendata.mof.gov.ae/

---

## Algeria (DZA) — confidence: **med-high**

Σ 2016–22 ≈ $156B (oil_gas). Anchored on IMF Article IV statistical-appendix
tables. Hydrocarbon revenue includes royalty + special petroleum tax +
Sonatrach dividends (line "Recettes des hydrocarbures" in IMF tables).

Files in `data/raw/resources/country sources/DZA/`:
- `IMF_DZA_2018.pdf` … `IMF_DZA_2025.pdf`

Source URLs:
- IMF Article IV (Algeria): https://www.imf.org/en/Countries/DZA
- Sonatrach annual reports: https://sonatrach.com (FR/AR; English summaries occasional)
- Ministère des Finances (Algeria): https://www.mf.gov.dz

---

## Iran (IRN) — confidence: **low-med to very-low**

Σ 2016–22 ≈ $213B (oil_gas), with high uncertainty due to sanctions opacity.
2016-2017 anchored on IMF Article IV 2018 (pre-sanctions snapback). 2018-2020
estimated under sanctions (rial collapse makes official-rate figures
unreliable). 2021-2022 use EIA OPEC Net Oil Export Revenue series as a
proxy for fiscal revenue.

Files in `data/raw/resources/country sources/IRN/`:
- `IMF_Iran_2018.pdf` — IMF Article IV 2018 (last before sanctions reimposition)
- `EIA_Iran_2024.pdf` — EIA Country Analysis Brief
- `Oil-and-Gas-3_stzatistical_yearbook_iran_2016_2017.pdf` — Iran Statistical Yearbook (Farsi, not parsed)

Source URLs:
- EIA Iran briefs: https://www.eia.gov/international/analysis/country/IRN
- IMF Article IV (Iran): https://www.imf.org/en/Countries/IRN

---

## Libya (LBY) — confidence: **low (2016-2020) / medium (2021-2022)**

Σ 2016–22 ≈ $118B (oil_gas). 2021-2022 are MoF Revenue/Expenditure Statements
(directly sourced). Earlier years are carried-over prior estimates (highly
disrupted period, civil war, oil blockades).

Files in `data/raw/resources/country sources/LBY/`:
- `Libya_2022.pdf` … `Libya_2025.pdf` — Libya MoF Revenue/Expenditure Statements

Source URLs:
- Libya MoF: https://www.mof.gov.ly (Arabic; English partial)
- NOC Libya: https://noc.ly

---

## Turkey (TUR) — confidence: **medium (royalty only)**

Σ 2016–22 ≈ $2B from MAPEG mining royalty + petroleum state-share. This is the
ROYALTY-ONLY component. Real Turkish extractive fiscal take is ~$5-6B over
7 yrs (royalty + sector CIT). The separate `data/raw/resources/country sources/turkey_cit_extractive_extracted.csv`
staging file has rough CIT estimates that haven't been merged. Turkish
extractive sector is genuinely small (mining ~1.36% of GDP, upstream oil/gas
tiny — TÜPRAŞ refining is downstream not extractive).

Files in `data/raw/resources/country sources/TUR/`:
- `MAPEG 2019 YILI FAALİYET RAPORU.pdf` (Mining and Petroleum General Directorate annual report)
- `2020 MAPEG Yıllık Faaliyet Raporu 22.03.2021.pdf`
- `MAPEG 2021 Yılı İdare Faaliyet Raporu 180322.pdf`
- `MAPEG 2022 Yılı İdare Faaliyet Raporu 28.02.2023 16_50.pdf`
- `4yillaragoredevlethakkıbilgileri.png` — image of 4-year state-rights summary (not OCR'd)

Source URLs:
- MAPEG (Maden ve Petrol İşleri Genel Müdürlüğü): https://www.mapeg.gov.tr
- Turkish Treasury: https://www.hmb.gov.tr
- GİB (tax authority) revenue stats: https://www.gib.gov.tr

---

## Lesotho (LSO) — confidence: **medium (extracted; not used in pipeline)**

Σ 2016–22 ≈ $200M (real mining-sector fiscal take). NOT added to
`manual_resource_revenue.csv` because Lesotho's CbCR data has a massive
reporting anomaly (~$38B/yr profit reported vs $2B GDP). Lesotho is
flagged in `DATA_QUALITY_EXCLUSIONS = {LSO, FSM, GUF, BTN}` in
`6_winners_losers_analysis.py` and `8_five_scenario_report.py`.

Real Lesotho mining is Letseng / Mothae / Liqhobong / Kao diamond mines
(Gem Diamonds majority owner). State revenue = $30-43M/year (Diamond Sales
Tax + Royalties + state dividends from Letseng).

Files in `data/raw/resources/country sources/LSO/`:
- `2018-2019 Budget Estimates Book-…_lesotho.pdf` (and similar 2019-2020, 2020-2021, 2021-2022, 2022-23, 2024-25, 2025-2026)
- `Budget-Speech_2020_2021-Final_lesotho.pdf`
- `2022-2023-Budget-Speech-Wednesday-02-03-2022_lesotho.pdf`

Source URLs:
- Lesotho Ministry of Finance: https://www.finance.gov.ls
- Lesotho Revenue Authority: https://www.lra.org.ls

Extracted figures saved to `data/raw/resources/country sources/lesotho_revenue_extracted.csv` for reference.

---

## Brazil (BRA) — confidence: **medium**

Σ 2016–22 ≈ $162B (oil_gas, updated with ANP "Valores Consolidados") + $32B
(minerals via ANM CFEM royalty + estimated sector CIT). Brazil 2019 update
incorporated the $14.84B Cessão Onerosa surplus auction (Búzios/Sépia/
Atapu/Itapu) that the prior manual entry had missed. Brazil 2022 includes
$15.31B Petrobras-to-Union dividends (Tesouro Nacional).

Outstanding refinement: PSC profit-oil from PPSA, private-operator
sector CIT, full Petrobras→Union dividend reconciliation against Tesouro
Nacional.

Files in `data/raw/resources/country sources/BRA/`:
- `valores-consolidados-2016-1_brazil.xlsx` … `valores-consolidados-2025_brazil.xlsx` — ANP government-take consolidated values

Source URLs:
- ANP (Agência Nacional do Petróleo) statistics: https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-estatisticos
- ANM (Agência Nacional de Mineração) CFEM data: https://www.gov.br/anm/pt-br
- Tesouro Nacional (dividends): https://www.tesourotransparente.gov.br/
- PPSA (Pré-Sal Petróleo) profit-oil: https://www.presalpetroleo.gov.br

Staging file: `data/raw/resources/country sources/brazil_anp_extracted.csv` (ANP detail by year);
`data/raw/resources/country sources/petrobras_union_dividends_extracted.csv` (Tesouro dividends).

---

## Peru (PER) — confidence: **med-high** (manual overrides EITI bilateral)

Σ 2016–22 ≈ $27B from Peru SUNAT (Servicio Nacional de Administración
Tributaria) tax revenue from mining + hydrocarbons. SUNAT replaces EITI
bilateral data for Peru because (a) EITI Peru is missing 2021-2022 entirely
and (b) SUNAT 2016-2020 is ~65% larger than EITI for the overlap years.

Files in `data/raw/resources/country sources/PER/`:
- `cdro_A18_peru.xlsx` — SUNAT "Ingreso Tributario Recaudado" by sector (Cuadro A 18); time series 2000-2025

Source URLs:
- SUNAT Estadísticas: https://www.sunat.gob.pe/estadisticasestudios/index.html
- MEF Perú: https://www.mef.gob.pe
- INEI (national statistics): https://www.inei.gob.pe

---

## Mexico (MEX) — confidence: **low-med** (manual overrides EITI bilateral)

Σ 2016–22 ≈ $260B Pemex fiscal contribution. Components: Derecho Petrolero
(oil rights/royalty) + ISR petrolero (CIT on oil sector) + Pemex dividends
to state (equity). Pre-2020 Pemex fiscal regime was royalty-heavy; post-2020
reforms reduced overall take. Manual entries replace EITI bilateral (Pemex
doesn't report to EITI).

Files in `data/raw/resources/country sources/MEX/`:
- `Consulta_20260513-134851930_mexico.xlsx` — SHCP fiscal data query (user-uploaded)

Source URLs:
- SHCP Estadísticas Oportunas: https://www.finanzaspublicas.hacienda.gob.mx
- Pemex 20-F filings: https://www.sec.gov (search "Pemex")
- CNH (Comisión Nacional de Hidrocarburos): https://www.gob.mx/cnh

---

## Saudi Arabia (SAU) — confidence: **med-high**

Σ 2016–22 ≈ $1,016B oil_gas. Anchored on Saudi Ministry of Finance "Interactive Budget Dashboard". The dashboard CSV (in `data/raw/`) provides yearly oil-revenue actuals for 2018-2024.

Source URLs:
- Saudi MoF Budget Dashboard: https://www.mof.gov.sa
- Saudi Vision 2030 / NDMC data: https://www.ndmc.gov.sa

Raw file: `data/raw/Interactive Budget Dashboard 2026_Budget Data_Tabel.csv`

---

## Russia (RUS) — confidence: **med-high**

Σ 2016–22 ≈ $806B (oil_gas + minerals + coal). Anchored on Russian MinFin federal-budget-execution table.

Source URLs:
- Russian MinFin: https://minfin.gov.ru/en/statistics/
- Rosstat: https://eng.rosstat.gov.ru

---

## China (CHN) — confidence: **low-med**

Σ 2016–22 ≈ $491B (oil_gas + coal + minerals). Resource tax line directly
from NBS yearbooks; CIT and SOE dividend components estimated.

Files: see `data/raw/resources/country sources/China_resource_tax_from_statistical_yearbooks.txt`.

Source URLs:
- NBS yearbook (English): https://www.stats.gov.cn/sj/ndsj/YYYY/indexeh.htm
- MoF China: http://www.mof.gov.cn

---

## South Africa (ZAF) — confidence: **low-med**

Σ 2016–22 ≈ $18B mineral royalty. From SARS Mineral Petroleum Resources
Royalty (MPRR) annual reports. Sector CIT estimated.

Source URLs:
- SARS Mineral & Petroleum Royalty Tax: https://www.sars.gov.za
- South African Treasury: https://www.treasury.gov.za

---

## India (IND) — confidence: **med-high (oil&gas) / low (coal & minerals)**

Σ 2016–22 ≈ $179B. Oil & gas from PPAC (Petroleum Planning & Analysis Cell).
Coal (2026-06 sourcing pass): PIB year-wise royalty + Provisional Coal Statistics,
Coal India + SCCL current income tax and Coal-India dividend-to-GoI from audited
annual reports, plus GST compensation cess — med confidence. Non-fuel minerals:
Hindustan Zinc current tax + dividend-to-GoI are audited (high), but the non-fuel
royalty / DMF and NMDC components are reconstructed from IBM Indian Minerals
Yearbook magnitudes and the Tata/JSW/Vedanta mining-segment CIT is not separable
from integrated-steel accounts — so minerals remains low confidence (improved
estimate, not authoritative).

Source URLs:
- PPAC: https://www.ppac.gov.in
- IBM India: https://www.ibm.gov.in
- Min. of Coal: https://www.coal.nic.in

---

## Other countries (lower priority / flagged for refresh)

The following manual entries are still on rough estimates and should be
refined in subsequent passes:

- **Kuwait** (KWT) — confidence low; need KPC + KIA reports
- **Qatar** (QAT) — confidence low; QP consolidated into state budget but split not public
- **Oman** (OMN) — confidence low; PDO + MoF reports
- **Bahrain** (BHR) — confidence low; NOGA + MoF
- **Australia** (AUS) — confidence medium; provincial royalties not harmonised
- **Indonesia** (IDN) — confidence low; Pertamina data
- **Malaysia** (MYS) — confidence low-med; Petronas-contribution headlines

For all of these, the recommended sources are the country's MoF / central
bank statistical bulletins + the IMF Article IV statistical appendix.

---

## Audit trail of source-extraction tools

For each country whose data was extracted by an automated agent, a staging
CSV is preserved alongside `manual_resource_revenue.csv`:

| Country | Staging CSV | Extracted via |
|---|---|---|
| Multi (UAE, DZA, IRN, LBY, TUR) | `resource_revenue_extracted_new.csv` | pymupdf on IMF/MoF PDFs |
| Turkey CIT | `turkey_cit_extractive_extracted.csv` | WebSearch on industry sources |
| Lesotho | `lesotho_revenue_extracted.csv` | pymupdf on Lesotho budget books |
| Brazil ANP | `brazil_anp_extracted.csv` | openpyxl on ANP xlsx |
| Brazil Petrobras | `petrobras_union_dividends_extracted.csv` | WebSearch on Tesouro Nacional reports |

These staging files are inputs to `manual_resource_revenue.csv` but are
preserved for re-derivation if the source files are re-extracted with
refined methodology.
