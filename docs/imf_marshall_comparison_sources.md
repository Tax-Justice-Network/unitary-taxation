# Context comparisons (9t): UT gains vs IMF debt and the Marshall Plan — sources & method

Script: `src/9t_ut_gains_vs_imf_debt_marshall.py`
Output: `output/unitary_taxation/reported_only/context_comparisons/{tables,figures}/`

Both comparisons are framed as revenue **gains** from unitary-taxation (UT)
reform, using the headline spec: reported-only sample, `excl_resource` dataset,
formula `sales_employees_destmnedds`, `domfor` ETR, ETR-CIT rate mode
(`loss_cit_gain_etr`, threshold `inf`), years 2016–2022 excluding 2020.
Per-country gain = net `revenue_gain_from_ut`, deflated per-year with
`config.deflator_to_base()` (US GDP deflator) to constant 2025 USD; annual
average = deflated sum ÷ 6.

## 1. Outstanding IMF credit (Global South)

- **Data**: World Bank International Debt Statistics indicator
  **`DT.DOD.DIMF.CD`** — *Use of IMF credit (DOD, current US$)*, the
  outstanding **stock** of credit owed to the IMF, per country-year. This is
  the same stock concept as the IMF's "Total IMF Credit Outstanding" page
  (<https://www.imf.org/external/np/fin/tad/balmov2.aspx?type=TOTAL>), which
  blocks scripted access (Akamai) — hence the WB mirror.
- **Cache**: `data/raw/imf_credit_outstanding_wb.csv` (fetched 2026-07-17,
  2019–2025 window; 120 debtor countries with data, latest year mostly 2024).
  Delete the file and re-run 9t to refresh. WB regional/aggregate rows are
  dropped (iso3 filtered against pycountry).
- **Method**: latest non-null stock per country, converted from its (nominal)
  stock year to 2025 USD with the config GDP deflator. `years_to_repay` =
  stock ÷ annual UT gain; undefined (flagged) where the country has no net
  gain. Aggregate rows cover all IDS debtors *with UT estimates* and each
  `wb_income_group`.
- **Decisions** (user, 2026-07-17): IMF credit **stock only**. Explored and
  rejected: IMF debt service `DT.TDS.DIMF.CD` (~$45bn/yr), all-creditor debt
  service `DT.TDS.DECT.CD` (~$1.29tn/yr, gains ≈13%), all-creditor stock
  `DT.DOD.DECT.CD` (~$8.9tn, too diluted). Scope = all IDS debtors (not only
  LIC/LMIC).

## 2. Marshall Plan aid (European recipients)

- **Primary source (totals)**: Congressional Research Service (2018), *The
  Marshall Plan: Design, Accomplishments, and Historic Significance*, CRS
  Report **R45079**, **Table 2** ("European Recovery Program Recipients,
  April 3, 1948 – June 30, 1952"), itself citing **USAID, Bureau for Program
  & Policy Coordination, November 17, 1971**.
  Cite: <https://crsreports.congress.gov/product/pdf/R/R45079>
  (mirror: <https://www.everycrsreport.com/reports/R45079.html>).
  Chosen over the older ECA/textbook series (UK 3,297 / France 2,296 /
  Sweden 347 …) for official provenance and internal sum-consistency.
- **Grants/loans split (supplementary)**: Wikipedia, "Marshall Plan",
  table *Economic aid, 3 April 1948 to 30 June 1952*
  (<https://en.wikipedia.org/wiki/Marshall_Plan>). That table matches CRS
  line-for-line **except Italy**: it shows 1,208.8, under which its own
  columns sum to 13,025.8 instead of the stated 13,325.8; CRS's **1,508.8**
  restores the total, so CRS totals are authoritative and Italy's
  grants/loans split is flagged `confidence=low`. Note the wiki grand totals
  (grants 11,820.7 / loans 1,505.1) also do not exactly match their own
  column sums (11,610.7 / 1,535.1 incl. the German $200M grants→loans
  conversion); the 9t aggregate uses the column sums for transparency.
- **Data file**: `data/raw/marshall_plan_aid.csv` (nominal $M of the time,
  with per-row `confidence`, `source_url`, `note`). ISO mapping: FRG→DEU,
  Italy incl. Trieste→ITA, Belgium-Luxembourg→`BEL+LUX` (compared against
  the two countries' combined UT estimate; aid was reported jointly),
  Netherlands→NLD (includes $101.4M for the Dutch East Indies pre-1950,
  per footnote). The `Regional` row (EPU $361.4M + freight $33.5M +
  technical assistance $12.1M) has no iso3 and enters aggregates only.
- **Inflation adjustment**: US **CPI-U** annual averages (BLS series
  `CUUR0000SA0`), hand-curated in `data/raw/us_cpi_annual.csv`. Factor =
  CPI(2025)/CPI(1950) = 321.943/24.1 ≈ **13.36** — 1950 is the mid-period
  anchor of the 1948–52 disbursements (per-year per-country disbursements
  are not available in the source). 2025's annual average is an 11-month
  average (October 2025 missing, BLS lapse in appropriations). Total
  $13,325.8M ≈ **$178bn** in 2025 USD; grants-only $11,610.7M ≈ $155bn.
  The pipeline's own `US_GDP_DEFLATOR_2017100` starts in 2016 and cannot
  reach 1948; CPI is also the adjustment most popular sources quote.
- **Index-consistency sensitivity**: the estimates side uses the US GDP
  deflator, so the CPI-adjusted plan is an index mismatch — a **deliberate,
  conservative** one. With the GDP deflator (BEA/FRED `A191RD3A086NBEA`,
  1950 = 12.195, 2025 = 128.979, factor ≈ **10.58**, now a column in
  `us_cpi_annual.csv`) the plan is only ≈ **$141bn**, and the group's
  six-year gain equals **2.95** Marshall Plans (vs the CPI headline 2.34;
  one plan every 2.0 vs 2.6 years). Carried in the table as
  `aid_total_2025bn_gdpdef` / `marshall_plans_per_6yr_gdpdef` and in the
  aggregate-figure note. CPI remains the headline (gives the plan its
  largest 2025-USD value, so the ratio cannot be accused of inflation-
  trickery).
- **Framing** (user, 2026-07-17): headline = the **aggregate** across all 16
  recipient economies, so haven-side losses (IRL, NLD, DNK, NOR) net out
  within the group: recipients gain ≈$69bn/yr → cumulative ≈$416bn over the
  six headline years ≈ **2.3 Marshall Plans**, i.e. a full inflation-adjusted
  Marshall Plan roughly every **2.6 years**. Per-recipient ratios (incl.
  grants-only variants) are carried as detail columns/figure. Comparisons
  use **total aid** as headline with **grants-only** alongside.

## Output files

- `tables/ut_gains_vs_imf_credit.csv` — per-country + aggregate/income-group
  rows: IMF credit (bn 2025 USD), annual UT gain, years-to-repay. Aggregate
  rows carry THREE averages: the pooled ratio `years_to_repay` (Σcredit ÷
  Σgain — the headline), plus the unweighted `years_to_repay_country_median`
  and `_mean` over the `n_countries_in_avg` countries with positive gain AND
  debt. The mean is outlier-dominated (near-zero-gain countries: Haiti
  ~1,700 yrs) — quote the pooled figure or the median, never the mean.
- `tables/ut_gains_vs_marshall_plan.csv` — per-recipient + aggregate: nominal
  and 2025-USD aid (total & grants & GDP-deflator sensitivity), annual &
  cumulative gain, Marshall Plans per 6 years, years per Marshall Plan
  (total & grants-only). The aggregate row also carries
  `years_per_plan_country_median` / `_mean` over the 11 recipients with
  positive gains (mean pulled up by Greece 23.3 / Austria 7.3).
- `figures/fig_ut_gains_vs_imf_credit.png` — years-to-repay, 15 largest
  debtors with positive gains.
- `figures/fig_ut_gains_vs_marshall_aggregate.png` — headline aggregate bars.
- `figures/fig_ut_gains_vs_marshall_by_recipient.png` — per-recipient detail.
