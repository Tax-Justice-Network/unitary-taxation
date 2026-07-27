# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository calculates profit shifting estimates for the State of Tax Justice (SOTJ) report using the misalignment method based on OECD Country-by-Country Reports (CbCR). The methodology is documented in [this paper](https://www.sciencedirect.com/science/article/pii/S0305750X23003455).

## Environment Setup

```bash
conda env create -f environment.yml
conda activate sotj_profit_shifting_estimates
```

Key dependencies include `tjn_tools` and `tjn_internal` (TJN internal packages installed from GitHub).

## Configuration

Before running analysis, update `src/config.py`:
- Set `first_year` and `n_years` for the analysis period
- Update file paths for raw data sources when new data is available (CbCR, CIT rates, wages, GDP, health expenditure, etc.)

### Tax-haven lists (config.py)

Two lists, with the representation list a strict **superset** of the cleaning
list (one consistent core; the lists never disagree on a shared jurisdiction):
- **`TAX_HAVENS_CLEANING`** — the **exact** haven list of García-Bernardo, Janský &
  Zucman (2026, IMF Econ. Review, §4): 11 "profit centres" (`_GB_PROFIT_CENTRES`)
  + 6 "coordination centres" (`_GB_COORDINATION_CENTRES`) = 17, grouped per Reurink
  & García-Bernardo (2020). Drives the GB dividend double-counting correction in
  `1_clean.py` (10% of haven profits, non-US MNCs, 2016–2019). **Changing it changes
  the cleaned profit figures.** (`tax_havens` is a backward-compatible alias.)
- **`TAX_HAVENS_REPRESENTATION`** (29) — drives the `investment_hub` income-group
  classification in figures/tables. **Rule (2026-07-18):** the GB cleaning list,
  UNIONed with every jurisdiction that has a **CTHI-2025 Haven Score ≥ 65**
  (`data/raw/country_info/tjn_cthi_2025_scores.csv`) AND booked **inward-shifted profit
  (reported − theoretical profit > 0) in at least TWO years** (2016–2022 excl
  2020, current headline reported-only / excl_resource / sales_employees_**destmnedds**
  / etrdef_domfor), plus the manual substance keep **`_EXTRA_MANUAL` = {IOT}**
  (BIOT, unscored). Puerto Rico and Barbados are GB profit centres, so the GB
  leg keeps them despite having no CTHI score. No general FSI fallback —
  **Saudi Arabia stays out (HOME-BIAS, ~98% home-booked)**. The non-GB outcome
  set `_EXTRA_CTHI_GE65_2YR_SHIFT` = Monaco, Panama, Curaçao, Seychelles, Cyprus,
  Aruba, UAE, **Liberia**, Guernsey, Liechtenstein, Anguilla. Vs the 2026-07-11
  rule (CTHI-2024>65 + *pooled* net-recipient) this **ADDS Liberia** (3 shift
  years) and **DROPS Cook Islands** (no CTHI, no shift year); **Guernsey** now
  qualifies on outcome (no longer a manual add). **Hungary is EXCLUDED** — CTHI 69
  but a single inward-shift year (2016), a large net loser (~−28bn) otherwise;
  the ≥2-year gate exists to reject such single-year outliers (Anguilla is the
  thinnest keeper, exactly 2 years).
  `TAX_HAVENS_REPRESENTATION_NARROW` is a deprecated alias of the main list.
  Purely presentational (no effect on estimates). See `docs/tax_haven_lists.md`.
  Misalignment haven ID in script 5 is **ETR-threshold-based** (15%), not
  list-based, so neither list gates it.
- **`TAX_HAVENS_FUNCTIONAL`** — FROZEN pre-2026-07-11 set (GB ∪ CTHI≥67 ∪ COK/IOT),
  used by the two steps where a haven set changes NUMBERS: the script-2
  imputed-activity cap exemption and the script-4 resource-dominated ETR-floor
  exclusion (plus 9h's inflation flag). Keeps the representation re-definition
  presentational: SAU keeps its script-4 "Saudi fix" floor; the six dropped
  jurisdictions (HUN/CRI/LVA/LBN/EST/LBR) keep their old functional treatment.
  **NB:** changing this list changes the `wb_income_group` (`investment_hub`) column,
  which propagates from `1_clean.py` through the whole pipeline — re-run to update figures.

An **outcome-based** alternative (haven iff pooled period-average ETR < threshold)
was **explored but not adopted** — it drops marquee havens (IRL/LUX/MLT/CHE/HKG/
NLD/MUS/GGY/COK) and pulls in loss-year/tiny-profit non-havens. The candidate
jurisdictions are documented in `docs/tax_haven_lists.md`; reproduce with
`python src/_build_etr_haven_list.py [threshold]`. No such constant lives in `config.py`.

## Script Workflow

Run scripts sequentially from `src/`:

1. **Data cleaning** (`1_clean.py`): Cleans and merges raw data sources (CbCR, CIT rates, wages, GDP, etc.). Computes the canonical reported-profit ETR family via `_etr_construction.compute_partner_year_etrs`. Writes `data/final/cbcr_main.csv` and `cbcr_main_allsubgroupsonly.csv`.
   - **1b. Destination-based sales** (`1b_destination_based_sales.py`): standalone prep (runs **after** script 1 — reuses its filled GDP/population), following OECD (2020) ch.2. Builds a per-`(iso_partner, year)` market allocation key: **CFB** (Analytical AMNE `F + D_MNE` turnover−exports over consumer-facing ISIC sectors; `destination/oecd_aamne_mne_xvem_2026-06.csv`), **ADS** (ITU internet penetration × UN household consumption), and the headline **combined** CFB + WTO digitally-delivered-services imports (`cfb_plus_digital_share`). Missing countries extrapolated by regression (log GDP/GDPpc/trade), remittance/aid adjusted; 2021–2022 reuse 2019 ratios; pop < 250k & missing → 0. Writes `data/intermediate/destination_based_sales.csv` (`cfb_share, ads_share, cfb_plus_digital_share, …`).
     **Broadened HEADLINE measure (2026-07-12)**: `mne_plus_dds_share` (tag **`destmnedds`**) = `mne_share` (same construction over **all 41 AAMNE sectors incl. finance** — matches the CbCR sales variable's scope; globally ≈2.4× CFB) + **the MNE share of digitally-DELIVERABLE services imports** (IMF-OECD-UNCTAD-WTO Handbook definition, from raw **BaTIS**; WTO "digitally delivered" = loud fallback; per the G24 paper BaTIS deliverable > WTO delivered). The MNE share = AAMNE (F+D_MNE) fraction of EXGR in the deliverable-producing ISIC sectors, per year ≈53–58% (last AAMNE year rolled forward); the headline DDS leg **excludes SH / charges for IP** (ex-IP promoted to headline 2026-07-12 — SH ≈15% of the aggregate, largely intra-group royalties; the IP-inclusive full aggregate = `destmneddsinclip` sensitivity); scaled ex-IP DDS leg ≈3.1–3.7% of the global key. **The former `destmneddsads` third leg (0.20 × ITU-internet × consumption ADS proxy) was RETIRED 2026-07-12** — paid ADS is already inside BaTIS (ADS ⊂ deliverable), and the proxy's consumption scale gave the ad-funded free slice ~14% of the key vs a realistic <1%; the free slice is excluded, not proxied. Hierarchy: ADS ⊂ digitally delivered (WTO) ⊂ digitally deliverable (Handbook/BaTIS). **Part D bilateral variant** (gated on `data/raw/destination_based_sales/oecd_aamne_bilateral_output_2026-07.csv`, host×owner output): parent-specific factor = market `mne_sales` × parent's ownership fraction of the market's MNE output (D_MNE → host as owner; uncovered pairs → parent's global share) → `destination_based_sales_bilateral.csv`, merged in script 2 on `(iso_parent, iso_partner, year)`; formula tag `destmnebilat` (no `_nexus` — ownership already encodes nexus). Script-5 tags: `destmne`, `destmnedds` (+`_nexus` each), `destmneddsexip` (ex-IP sensitivity, plain only). See `docs/destination_based_sales.md`.
   - **1d. Origin-vs-destination diagnostic** (`1d_compare_unrelated_vs_destination_sales.py`): correlates each jurisdiction's share of global unrelated-party revenue (origin) with the destination shares → `output/destination_sales/`.
   - **1e. Orbis nexus matrix**: the throwback nexus used by script 5 is a **per-`(hq_iso3, market_iso3)` distinct-group count**, `data/intermediate/extractive/cbcr_universe_presence.csv` (`hq_iso3, market_iso3, n_groups, n_entities`) — `n_groups` = number of distinct in-scope (≥€750M consolidated revenue) GUO groups headquartered in `hq` with ≥1 Orbis subsidiary in `market`. Built by the CbCR-universe Orbis passes: **Pass 1** (`build_cbcr_universe_pass1_financials.py`) filters `Key_financials-EUR.txt` to C1/C2 turnover ≥ €750M → `cbcr_inscope_groups.csv`; **Pass 2 assemble** (`build_cbcr_universe_pass2_assemble.py`) expands those GUOs via the `Links_current.txt` GUO-50 filter to the member-entity universe `cbcr_universe_entities.csv`; **Pass 2 presence** (`build_cbcr_universe_pass2_presence.py`) group-bys that to the distinct-group matrix. The matrix deliberately carries **no** `n_cbcr` column — the coverage denominator is the OECD CbCR cell count, which lives in the CbCR dataset (propagated by script 2), so there is no ambiguity about which group count the nexus divides by. The legacy `1e_orbis_presence_matrix.py` → `data/intermediate/orbis_hq_subsidiary_presence.csv` (`n_links`, full-universe link **count**) is kept only as a binary-presence fallback when the group-count file is absent.
2. **Disaggregation** (`2_disaggregate_aggregated_values.py`): Disaggregates bad-reporter continent / WXD aggregates across **all eligible markets**, imputing activity by the **gravity model** and profit by **partner profitability** (the single method — see "Disaggregation: the single gravity + profitability method"). Writes `data/final/cbcr_main_disaggregated.csv` (one row per `(iso_parent, iso_partner, year)` cell, with `is_distributed ∈ {0, 1}`); also **merges in the destination-based sales columns** from step 1b on `(iso_partner, year)`. The pair ETR (`etr_parent_partner_corrected`) is NaN on distributed rows by design.
3. **Extractive prep** (`src/3_extractive_prep/1_6 → 1_7a → 1_7 → 1_8`): Pulls EITI company payments, matches to Orbis HQs, aggregates to `(source, hq, commodity, year)` resource-payment buckets cascading EITI > manual > GRD > rent-proxy. Writes `data/intermediate/extractive/resource_payments_by_hq_source_yearly.csv`.
4. **Resource correction** (`4_correcting_cbcr_for_resource_payments.py`): Reads the disaggregated CbCR + the resource-payment panel and emits three deliverable datasets — see "Four-dataset scheme" below. Recomputes the **non-resource ETR family** on the (excl_resource profit, excl_resource tax) pair via `_etr_construction.compute_partner_year_etrs` and carries it across the output files.
5. **Unitary-taxation estimation** (`5_estimate_profit_shifting.py`): Reads ONE of the four CbCR datasets, runs UT formulary apportionment under multiple formula × ETR-spec × tax-rate-mode combinations. The active dataset is selected by `RUN_DATASET = "..."` (or env var) at the top of the file (one of `disaggregated` / `excl_resource` / `incl_resource` / `excl_resource_floored` / `excl_resource_floored_cat2` / `excl_resource_floored_cat3`). `REPORTED_ONLY` (env, default 1) toggles reporter-only (`is_distributed==0`; output `…_reported/`) vs full disaggregated incl. imputed rows (output `…/`). For parallel runs, copy `5_estimate_profit_shifting.py` and change the single `RUN_DATASET` line.
   - **Origin vs destination sales factor**: the default sales factor `unrelated_party_revenues` is *origin*-based. A loop after `FORMULAS` (using `DEST_MEASURES`) auto-generates *destination* variants of the 4 sales-using families (ccctb, double_weighted_sales, sales_employees, three_factors), swapping the sales slot for a destination **share** column — `destcombined` (CFB+digital), `destcfb`, `destads` — each with a `_nexus` version that **down-weights the share by the covered fraction of the cell's reported MNE groups** — `coverage = min(n_groups / n_cbcr, 1)`, where `n_groups` is the distinct in-scope Orbis groups present in the market (step 1e's `cbcr_universe_presence.csv`) and `n_cbcr` is the cell's CbCR MNE-group count (propagated through script 2 as pair-year metadata); home market and `is_distributed==1` imputed rows (no `n_cbcr`) fall back to binary presence (built by `_attach_destination_factors`). The old binary on/off (`share × {0,1}`) was wrong because Orbis presence reflects only *some* of the groups aggregated into a CbCR cell, not all of them. Formulas whose columns are absent are auto-skipped, so destination/nexus formulas stay inert on datasets lacking those columns (only the disaggregated dataset carries them unless script 4 is rerun to propagate). The within-parent normalisation in `_compute_share_economy` turns the share column into the destination distribution, so no per-parent rescaling is needed.
6. **Winners/losers consolidation** (`6_winners_losers_analysis.py`): Concatenates per-spec `country_estimates__*.csv` outputs into `summary_country_year_long.csv` per topic, plus headline tables and figures. Consumed by scripts 7, 8 and 9.
7. **Three-dataset comparison** (`7_three_dataset_comparison.py`): Tax-base (misalignment) winners/losers across the three **main** scenarios (disaggregated / excl_resource / excl_resource_floored). Outputs to `output/comparison/`.
8. **Five-scenario report** (`8_five_scenario_report.py`): Side-by-side comparison of the UT samples × four formula families across all **five** scenarios — three main (Route A) + two alternative resource-factor (Route B). Both rate-mode choices for the recovery metric. Outputs to `output/five_scenarios/`.
9. **Three-scenario figure deliverable** (`9_three_scenario_figures.py`, `9b_country_examples.py`): The focused headline deliverable — Route A only, reusing `8`'s machinery; plus Chad / South Sudan / Burkina Faso examples. Outputs to `output/three_scenarios/`.
   - **9c. Gravity + destination comparison** (`9c_gravity_destination_comparison.py`): extends the three-scenario deliverable to the **gravity-imputed full sample** and **destination-based sales**. Part 1 = gravity per-scenario figures (reuses `9`'s `make_scenario_figures` via `build_summary(...)` on the canonical `cbcr_main_*.csv` files); Part 3 = origin-vs-destination sales (`sales_employees` vs `sales_employees_destcombined`) by income group + a low-income country-level figure/table flagging which LICs still lose under destination. (The former Part 2, trimmed-mean-vs-gravity comparison, was removed when trimmed-mean disaggregation was retired — there is one method now.) Outputs to `output/three_scenarios/{gravity,comparison}/`. **Persistent LIC destination losers: NER, MWI, BFA** (commodity exporters with tiny consumer markets — destination apportionment sends their profit abroad; the loss *grows* under excl_resource).
   - **9d. Gravity full overview** (`9d_gravity_overview.py`): one consolidated CSV of net / LIC / #LIC-losers / DRC across every (scenario × formula × etr × rate) gravity spec → `output/three_scenarios/comparison/gravity_full_overview.csv`.
   - **9e. Attach bootstrap SEs** (`9e_attach_bootstrap_ses.py`): joins `run_bootstrap.py`'s `gravity_bootstrap_SEs__<spec>.csv` onto the gravity baseline per-country net gain → `headline_{country,lic}_with_ses.csv` (+ `ci_excludes_zero` flag).
10. **QA** (`src/3_extractive_prep/qa_resource_payment_correction.py`): PASS/FAIL/WARN checks across the resource-correction pipeline and the corrected CbCR files.
11. **Figures** (`6_1_figures_sotj25.ipynb`, etc.): Notebook visualisations for the report.

The resource-correction → UT → report portion is orchestrated by `src/_run_pipeline.py` (`1_8 → 4 → 5 × datasets × reported-flag → 6 → 8`). **The three-scenario data-correction route (scenarios 1–3) is the main specification; the two 5-factor resource-factor scenarios (4–5) are an alternative / backup framing.** The earlier carve-out-then-UT scripts (`3_resource_contribution.py`, `4_carveout*.py`, `5b_carveout_then_ut.py`, `5c_suffering_by_formula.py`, `3_validate_resource_contribution.py`) are **superseded** and live in `src/archive/`.

### Formula Options

The misalignment formula weights can be configured. Vars are `[n_employees, unrelated_party_revenues, tangible_assets, payroll, resource_factor_usd]`.

4-factor families (no resource term — used in scenarios 1–3):
- **SOTJ (default) `employees_payroll`**: 50% employees, 50% payroll → `weights=[0.5, 0, 0, 0.5]`
- **CCCTB `ccctb`**: 1/6 employees, 1/6 payroll, 1/3 sales, 1/3 assets → `weights=[1/6, 1/3, 1/3, 1/6]`
- **Three-factor `three_factors`**: 1/3 each → `weights=[1/3, 1/3, 1/3, 0]`
- **Double-weighted sales `double_weighted_sales`**: 25% employees, 50% sales, 25% assets → `weights=[0.25, 0.5, 0.25, 0]`
- **Sales + employees `sales_employees`**: 50% employees, 50% sales → `weights=[0.5, 0.5, 0, 0]`

5-factor families with `resource_factor_usd` (alternative/backup scenarios 4–5 — `incl_resource` only):
- `employees_payroll_resource_{10,20,30,50}pct` — 4-factor SOTJ + resource weighted x%, the other two factors share the remainder equally.
- `ccctb_with_resources_30pct`, `three_factors_with_resources_30pct`, `double_weighted_sales_with_resources_30pct` — each 4-factor family scaled by 0.7, with the resource factor adding 0.3.

## Key Data Sources

- **CbCR data**: OECD Corporate Tax Statistics Database
- **CIT rates**: OECD and Tax Foundation
- **Wage data**: ILO Wages and Working Time Statistics
- **GDP/Population**: World Bank
- **Health expenditure**: WHO

## Folder Structure

```
data/
  guides/                    # Database codebooks/metadata + README.md INDEX of every
                             #   external database (source, URL, vintage, consumer).
                             #   No pipeline inputs live here.
  raw/                       # Datasets obtained from elsewhere ONLY — external
                             #   downloads, API pulls, hand-curated files. Nothing
                             #   here is produced by a transformation step.
                             #   Reorganised 2026-07-22 into kind-of-data subfolders,
                             #   files named <source>_<content>_<date>.<ext>:
    cbcr/                    #   OECD CbCR Table I (gitignored) + reporters list + pcbcr/
    tax_rates/               #   OECD CIT rates, Tax Foundation, OECD RSGLOBAL CIT revenue
    macro_variables/         #   WB WDI bundles, ILO wages, WHO health, BLS US CPI,
                             #   manual_imputation_values.csv
    destination_based_sales/          #   AAMNE, BaTIS (gitignored), WTO DDS, UN consumption, ITU
    country_info/             #   CTHI/FSI/portal exports, G77
    context/                 #   IMF credit, Marshall plan, debt, climate finance, ODA
    resources/               #   extractive sub-pipeline (incl. eiti_reports/ and
                             #   resource_profits_manual_sources/)
    orbis/                   #   proprietary Orbis pulls (gitignored)
    gravity/                 #   gravity-imputation model inputs (gitignored)
                             #   (rename map: data/guides/_raw_reorg_manifest_2026-07-22.txt)
  intermediate/              # Pipeline working files derived from raw inputs.
    extractive/              #   Extractive sub-pipeline: EITI-cleaned panels,
                             #   calibrated rent fractions, BGS scaling,
                             #   combined/per-mineral rents, the consolidated
                             #   royalty panel, HQ shares, GRD revenue.
  final/                     # Deliverable analysis datasets.
                             #   cbcr_main_disaggregated.csv (baseline)
                             #   cbcr_main_excl_resource.csv (resources excluded)
                             #   cbcr_main_incl_resource.csv (resources included)
                             #   cbcr_main_excl_resource_floored.csv (excl + IGF-ATAF floor)
  archive/                   # Previous-year folders for reproducibility.

output/                      # Organised by SAMPLE and ROLE (see output/README.md).
                             #   config.output_dirs() remaps the flat topic
                             #   strings scripts pass into this nested layout, so
                             #   scripts keep their original topic names.
  unitary_taxation/
    gravity/                 # MAIN — gravity-imputed FULL sample (the single
                             #   disaggregation method). Per-spec UT (baseline /
                             #   excl_resource / excl_resource_floored / incl_resource)
                             #   PLUS the sample's figure deliverables embedded here:
                             #   three_scenario_figures/, imputation_comparison/,
                             #   country_overview/ (per-sample overview xlsx).
    reported_only/           # recorded profits only (is_distributed==0, no imputed rows).
                             #   baseline / excl_resource / excl_resource_floored / incl_resource
                             #   PLUS three_scenario_figures/, five_scenario_figures/,
                             #   origin_vs_destination/, country_overview/.
    across_samples/          # cross-sample / sample-agnostic RESULTS:
                             #   country_overview/ (tidy long table + 9h negatives),
                             #   resource_correction/ (9f), comparison/ (7 — 3-scenario
                             #   tax-base winners/losers).
    diagnostics/             # QA / supporting analysis, now under the UT tree:
                             #   destination_sales/ (1d + bootstrap SEs),
                             #   etr_ut_income_groups/, disaggregation/,
                             #   country_profiles/, gravity_boot/, gravity_boot_reported/
  extractive/                # extractive sub-pipeline outputs
  archive/                   # unitary_taxation_legacy/, redundant/, previous-year
                             #   folders. (There is one disaggregation method now —
                             #   gravity — so no trimmed-mean full-mode sample and no
                             #   trimmed-vs-gravity split.)

src/
  3_extractive_prep/         # Extractive sub-pipeline (1_*, 2_*, 3_* scripts)
                             #   + _paths.py, _reference_prices.py shared modules.
  archive/                   # Legacy notebooks for reference.
```

### Reference-price tables

`src/3_extractive_prep/_reference_prices.py` is the single source of truth for
all commodity reference prices (`MINERAL_PRICES`, `HS_PRICE_UNIT`,
`MINERAL_VOL_TO_PRICE_MULT`, Brent/Henry-Hub/coal). It's importable from any
`src/` script (config.py puts `src/3_extractive_prep/` on `sys.path`). Don't
copy these tables into individual scripts.

### Figure styling (TJN brand)

All deliverable figure scripts (`6`, `8`, `9`, `9b`, both `9c`) import
`src/_brand.py` and call `apply_tjn_style()` at module load. It registers the
bundled **Work Sans** TTFs (`assets/fonts/`, SIL OFL — the brand publication
font, since it isn't installed system-wide) and sets the brand colour palette
(Gold `#FFD371`, Earth green `#50805E`, Red `#AD756C`, Teal `#45636C`, Brown
`#AE8D6C`, Blue `#586AAD`), clean spines, light y-grid, white background.
Semantic helpers: `POSITIVE`/`NEGATIVE` (green/red), `ORIGIN_DEST_NEXUS`
(blue/gold/green). Don't hard-code hex colours in figure
scripts — pull from `_brand`. Montserrat Black (slogans) and Catamaran Black
(logo) are intentionally NOT used in charts (brand guide).

### Manual macro / CIT / wage values (`macro_variables/manual_imputation_values.csv`)

The values that used to be **hard-coded** in `1_clean.py` — small-territory
GDP/population (§2.3a), the flat CIT overrides, and the hand-collected wages
(§2.4) — now live in a single hand-maintained file alongside their source URLs:
`data/raw/macro_variables/manual_imputation_values.csv`
(`iso_partner, year, variable, value, mode, source_url, note`). The script
consumes it via `load_manual_imputation_values()` / `apply_manual_values()`
(defined near the top of `1_clean.py`).
- `variable` is the target column (`gdp_current_usd`, `population`, `cit`,
  `wage_monthly`) — applied to `gdp_population`, `cits`, and `wages` respectively.
- `mode`: `fill_if_missing` writes only where the cell is currently NaN
  (GDP/pop and the `.isna()`-gated CITs); `override` writes unconditionally
  (wages and the flat CITs like GIB=0, CAF=0.3).
- Blank `year` applies to **every** row for that jurisdiction (year-agnostic:
  wages, the CIT overrides, BIOT GDP/pop).
- **Embedded arithmetic / FX** from the old code (e.g. `287988e3 × 0.69`,
  `× eur_usd_2022`) is **precomputed** into the stored `value`; the raw figure
  is preserved in `note`. **Editing a value changes the cleaned data.**
- **Derived CITs stay in code** (not in the CSV): `MTQ←FRA`, `BVT←NOR`
  (copied per year) and `MLT *= 1/7` (multiplicative refund adjustment).
The human-readable overview is `docs/manual_macro_imputation_sources.md`. The
one-time migration generator is `src/_build_manual_imputation_values.py` (guarded
against clobbering the now-authoritative CSV).

### Output paths in code

Use `output_dirs(topic)` from `config.py` — returns `(tables_dir, figures_dir)`
Path objects (auto-created). It **remaps** the flat topic string into the nested
`output/` layout via `_TOPIC_REMAP_EXACT` / `_TOPIC_REMAP_PREFIX` (e.g.
`unitary_taxation_disaggregated` → `output/unitary_taxation/gravity/baseline`,
`unitary_taxation_excl_resource_reported` → `output/unitary_taxation/reported_only/excl_resource`,
`three_scenarios` → `output/unitary_taxation/reported_only/three_scenario_figures`,
`deliverables/resource_correction` → `output/unitary_taxation/across_samples/resource_correction`,
`destination_sales` → `output/unitary_taxation/diagnostics/destination_sales`, etc.). **Scripts keep
their original topic strings** — to relocate a topic, edit the remap in `config.py`,
not the scripts. Any script that builds an output path by hand must go through
`output_dirs()` (the two that did — `9c_destination_vs_origin_figures.py` and
`gravity/run_bootstrap.py` — were updated accordingly).

## Core Logic

### Misalignment Calculation
The `calculate_misalignment()` function:
1. Calculates each jurisdiction's share of economic activity based on weighted formula variables
2. Computes theoretical profit allocation vs reported profits
3. Identifies misaligned profits (positive = tax haven receiving, negative = country losing)
4. Applies ETR threshold filter (default 15%) to identify tax havens
5. Balances positive/negative misalignment within each parent country group

### Bilateral Estimation
Bilateral links (who shifts profit FROM whom) are an **optional** deliverable,
produced by the standalone `5b_bilateral_links.py` run **after** `5_estimate_profit_shifting.py`
(it reads that run's `run_summary.csv` + per-spec misalignment files, honouring the
same `RUN_DATASET` / `REPORTED_ONLY`). They are deliberately not part of the
headline pipeline. (This replaced an in-script `RUN_BILATERALS` toggle.) For each
reporting country's MNEs:
- Tax havens (iso_responsible): Countries with positive misalignment
- Sufferers (iso_affected): Countries with negative misalignment
- Bilateral tax loss = (haven's share of positive) × (sufferer's share of negative) × total tax loss

### Four-dataset scheme (resource-payment correction)

Script 4 (`4_correcting_cbcr_for_resource_payments.py`) emits three resource-corrected datasets that, together with the untouched `cbcr_main_disaggregated.csv` baseline, form four parallel inputs the UT can run on:

| File | Profit column | Tax column | ETR family | UT view |
|---|---|---|---|---|
| `cbcr_main_disaggregated.csv` | `profit_loss_before_income_tax_corrected` | `income_tax_paid_on_cash_basis` | `etr_*_corrected` | Resources ignored — UT on reported figures, extractive activity like any other sector. |
| `cbcr_main_excl_resource.csv` | `profit_loss_excl_resource` (= reported − `resource_profit_base_usd`) | `income_tax_paid_on_cash_basis_excl_resource` (= reported − `post_profit_payments_usd`) | `etr_*_excl_resource` (recomputed on this pair) | Resources excluded — normal UT on the non-extractive corporate income only. |
| `cbcr_main_incl_resource.csv` | `profit_loss_incl_resource` (= reported + `pre_profit_payments_usd`) | `income_tax_paid_on_cash_basis_incl_resource` (= reported + `pre_profit_payments_usd`) | `etr_*_excl_resource` (carried over) | Resources included — UT yield compared to `actual_resource_contribution_usd` (= pre + post + equity). |
| `cbcr_main_excl_resource_floored.csv` | `profit_loss_excl_resource_floored` (cat1 alias) plus `_cat1` / `_cat2` / `_cat3` | `income_tax_paid_on_cash_basis_excl_resource_floored` (= excl_resource tax; the floor is a hypothetical royalty, not a CIT counterfactual) | `etr_*_excl_resource` (carried over) | Resources excluded + IGF-ATAF minimum royalty enforced. Pre-profit pool shrinks by `floor_add_on_{cat}_usd` (= the gap to the floor) — that gap is counted separately as additional royalty revenue alongside UT-derived revenue. No `incl_resource_floored.csv` is emitted: the 5-factor UT in scenario 4 substitutes for the resource regime entirely, so a minimum-royalty floor on top of it is meaningless. |

Selecting a dataset in `5_estimate_profit_shifting.py`:

```python
RUN_DATASET = "excl_resource"   # at the top of the file
```

The `DATASET_CONFIGS` dict at the top of script 5 maps each key to `(input_file, profit_var, tax_var, etr_suffix, output_topic)`. The output topic flows through `output_dirs(...)` so each dataset writes to its own `output/unitary_taxation_<dataset>/` folder.

**Why the ETRs are recomputed only once.** The non-resource ETR family represents the rate at which non-resource corporate income is actually taxed. It is computed on the `excl_resource` (profit, tax) pair via `src/_etr_construction.py:compute_partner_year_etrs` (5-year rolling window, partner-year aggregations of pair-specific ETRs into median / p25 / min / average) using only `is_distributed == 0` rows so imputed tax/profit values never enter the ETR construction. The resulting family is the right rate to apply in UT *regardless* of whether the profit base used is reported, exclusive of resource, or inclusive of resource — so the `incl_*` files simply carry the same ETR columns rather than recomputing them.

**Pair ETR (`etr_parent_partner_*`) is a diagnostic, not a UT input.** Both in the disaggregated baseline and in the three resource-corrected files, the pair ETR is NaN on `is_distributed == 1` rows by design (no real (parent, partner, year) report exists). It is kept in the file for inspection / QA but is never an `ETR_SPECS` entry in script 5.

### Bad Reporters Handling

Countries that only report aggregates (continents/ROW) instead of country-by-country data are treated as "bad reporters". They are handled as follows:

1. Preserve domestic data (iso_partner == iso_parent) as-is from bad reporters
2. Calculate shares from FOREIGN data only (exclude domestic from good reporters)
3. Distribute only FOREIGN aggregates using the shares
4. Combine: good reporters + preserved domestic + distributed foreign
5. Run final misalignment

**Why domestic is preserved**: domestic operations (e.g., Ireland's operations in Ireland) should not be redistributed, so only foreign aggregates are distributed.

#### Disaggregation: the single gravity + profitability method (`2_disaggregate_aggregated_values.py`)

There is **one** disaggregation method (the former `IMPUTE_METHOD` / trimmed-mean
vs gravity toggle and the weight-based / sales-only profit variants were removed on
**2026-06-23** — see `docs/disaggregation_method_change.md`). On distributed
(`is_distributed==1`) rows:
- **Real economic activity** — `n_employees`, `unrelated_party_revenues`,
  `tangible_assets_except_cash` — is imputed by the **García-Bernardo & Janský (2024)
  gravity/ML model** (`data/intermediate/gravity/gravity_imputed_activity.csv`).
  `payroll` follows automatically (= imputed employees × wage × 12).
- **Profit** (`profit_loss_before_income_tax_corrected` and the raw
  `profit_loss_before_income_tax`) is imputed from each partner's **reported
  profitability** (multi-factor yield — see below), sign-preserving.
- **`total_revenues`** is floored to the imputed `unrelated_party_revenues`
  (related-party revenue is not imputed).
- **Every other variable is NOT imputed** — `related_party_revenues`,
  `stated_capital`, `n_entities`, `holding_or_managing_ip`, and both `income_tax_*`
  columns are left **blank** on distributed rows.

**Recipient set = BROAD.** Each bad reporter's aggregate (continent `_O` /
single-letter / `W_O` / `WXD` residual) is spread across **all structurally-eligible
markets** (every real foreign country observed in the CbCR panel), not just the
partners good reporters happened to report. The structural eligibility/residual/
conservation skeleton in `distribute_aggregates_per_reporter` is retained, but the
phase-1 weights are now a flat `build_uniform_recipient_weights` table (uniform =
selects the recipient set + conserves each aggregate); the real within-group split
of the three activity factors is set by the gravity predictions afterwards.

**Two activity guardrails** keep imputed micro-state activity plausible:
- **Per-prediction cap** (`CAP_MULT=10`): each `(parent, partner)` prediction is
  capped at 10× the market's largest *observed* value for that factor.
- **Per-country total activity cap**: after redistribution, the *summed* imputed
  activity a country receives across all parents is capped by iterative
  water-filling at **2× GDP** (`unrelated_party_revenues`,
  `tangible_assets_except_cash`) and **0.5× population** (`n_employees`).
  Recognised havens (`TAX_HAVENS_REPRESENTATION`) are **exempt**. Conservation-safe
  because `val = weight/group_sum × aggregate`; GDP/pop anchored on a complete
  `(iso × year)` grid with per-country ffill/bfill. Residual non-haven micro-states
  (e.g. Marshall Is) are flagged `gravity_imputation_inflated` in the country
  deliverable → read those from the reported-only sample.

**Negative imputed profit is preserved**: a market whose reported profitability is
negative keeps a correctly-signed **negative** imputed profit (the
post-distribution clip exempts the signed profit/tax vars; the profitability
recompute uses a sign-robust share denominator).

**Conservation** is checked only for the imputed variables (the three activity
factors + the two profit columns); `total_revenues` (floored) and the un-imputed
variables are excluded by design.

**Output**: the single canonical `cbcr_main_disaggregated.csv` (bootstrap draws add
a `__boot{seed}` suffix via `GRAVITY_BOOT_SEED`). The **reported-only sample is
unchanged** — it filters to `is_distributed==0`, so the imputation method never
touches it.

#### Stateless entities (`STLS`)

OECD CbCR reports a per-reporter **`STLS` (Stateless)** partner row for sub-entities
the parent couldn't assign to a jurisdiction (~US$1.48tn profit 2016–2022, 94% US
MNEs — classic "stateless income"). **They are dropped entirely** in `1_clean.py`
(same filter as `W`/`ANT_F`/`BVT`) and never redistributed: stateless profit has no
real location, and the OECD flags it as a known source of **double counting** with
the partner rows, so dropping it is part of dealing with duplicate profits. The
misalignment/UT method then operates only on profit booked in identifiable
jurisdictions.

#### Imputed-row profit: multi-factor partner profitability

Profit on distributed (`is_distributed==1`) rows is imputed from each **partner
country's** own profitability, applied to the row's imputed factors —
`_impute_profit_multifactor` in `2_disaggregate_aggregated_values.py`. For each
factor in **`PROFIT_IMPUTATION_FACTORS`** (`unrelated_party_revenues`, `n_employees`,
`tangible_assets_except_cash`), the partner yield = Σ reported profit ÷ Σ reported
factor (**grouped by `iso_partner`, pooled over all parents and years** — per
partner country, not per parent-partner, and not year-specific); the row's imputed
profit = the **mean** of `row_factor × partner_yield` across those factors, then
rescaled within each `(year, parent, source_aggregate_code)` group (sign-robust
denominator) to conserve the reported aggregate profit. Loss-making partners keep a
**negative** imputed profit.
Partner yields are made robust by **winsorizing each partner's own yield across
partners at the 1st/99th percentile** (`PROFIT_YIELD_WINSOR = 0.01`): only the
explosive thin-denominator outliers (near-zero reported activity → exploding/
sign-flipping raw yield) are clipped, while every partner in the p1–p99 range keeps
its **own** profitability. This is **sign-preserving** — a partner that reported
losses keeps a negative yield (so a negative imputed profit), and a structurally
high-profitability jurisdiction keeps its high yield. (The earlier
shrinkage-toward-the-global-yield was removed because pulling every yield toward the
positive global mean flipped thin-activity loss-makers to a positive imputed profit.)
Profit
follows labour and asset bases too, not just consumer-sales markets — materially
raising imputed profit for asset-heavy extractive LICs. The earlier weight-distributed
and sales-margin-only profit variants were removed on 2026-06-23. Reported-only runs
are unaffected (no imputed rows).

### Bad Reporter Exclusions

Defined in `EXCLUSION_CONDITIONS` by country and year range:
- AUT (2016-2022), BGR (2022), BHR (2022), CAN (2022), COL (2022)
- CZE (2019-2022), FIN (2016-2022), GRC (2017-2019), GBR (2017-2022)
- HUN (2018-2022), IMN (2017-2020), IRL (2016-2022), KOR (2016-2022)
- LTU (2022), MAC (2019-2021), MAR (2021-2022), MUS (2019-2022)
- NLD (2016-2017, 2022), NOR (2016-2017), NZL (2018-2022)
- POL (2019-2021), SVN (2022), SWE (2016-2022), UKR (2022)
