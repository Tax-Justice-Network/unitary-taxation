<!-- TITLE AND SUBTITLE -->
<br />
<p align="center">
  <h1 align="center">Unitary Taxation Estimates</h1>
</p>
<p align="center">Replication package for<br /><b>"A 500-billion-dollar decision for the world: Revenue impacts of global unitary taxation"</b></p>
<p align="center">Estimates of the effect of unitary taxation — the change in each country's taxable profits and tax revenue under formulary apportionment — from OECD country-by-country reporting data, with two methodological innovations: a <b>correction for the extractive (natural-resource) sector</b> and a <b>destination-based measure of sales</b> (apportioning sales to the market where customers are).</p>

<p align="center">
  <a href="TODO_PAPER_URL"><b>📄 Main paper</b></a> &nbsp;·&nbsp; <a href="TODO_METHODOLOGY_URL"><b>📎 Methodology note</b></a> &nbsp;·&nbsp; <a href="TODO_EXPLORER_URL"><b>🌍 Results explorer</b></a>
</p>
<p align="center"><sub>⚠️ <b>Placeholder links</b> — replace <code>TODO_PAPER_URL</code>, <code>TODO_METHODOLOGY_URL</code> and <code>TODO_EXPLORER_URL</code> with the real URLs before making this repository public.</sub></p>

<br />

<!-- TABLE OF CONTENTS -->
<details open="open">
  <summary><h2 style="display: inline-block">Contents</h2></summary>
  <ol>
    <li><a href="#about-the-project">About the project</a></li>
    <li><a href="#installation">Installation</a></li>
    <li><a href="#configuration">Configuration</a></li>
    <li><a href="#data-sources">Data sources</a></li>
    <li><a href="#the-pipeline">The pipeline</a></li>
    <li><a href="#the-four-datasets-and-three-scenarios">The four datasets and three scenarios</a></li>
    <li><a href="#apportionment-formulas">Apportionment formulas</a></li>
    <li><a href="#revenue-specifications-etrs">Revenue specifications (ETRs)</a></li>
    <li><a href="#the-resource-sector-correction">The resource-sector correction</a></li>
    <li><a href="#reporting-conventions">Reporting conventions</a></li>
    <li><a href="#running-it">Running it</a></li>
    <li><a href="#output-layout">Output layout</a></li>
    <li><a href="#repository-layout">Repository layout</a></li>
  </ol>
</details>

<br />

<!-- ABOUT -->
## About the project

This repository estimates the **effect of unitary taxation (UT)**: the change in each country's taxable profits and corporate-tax revenue if multinational groups were taxed as single firms, with their global profit apportioned to countries by **real economic activity** (formulary apportionment) instead of by where the profit is currently booked.

Estimates use the **misalignment method** on the OECD's aggregated Country-by-Country Reporting (CbCR) data. For each parent country's multinationals, a country's *theoretical* profit share (from a labour/sales/assets formula) is compared with its *reported* profit; the difference is misaligned profit that unitary taxation would reallocate. The base methodology follows [García-Bernardo & Janský (2024)](https://www.sciencedirect.com/science/article/pii/S0305750X23003455).

On top of the standard estimate the pipeline makes two methodological contributions. First, it **corrects for the extractive sector.** In resource-rich countries a large share of reported CbCR profit is natural-resource rent that is, by international norm, taxable where the resource is physically located. Apportioning that profit away by a labour/sales/assets formula would produce spurious "losses" for resource producers. The correction strips resource-driven profit and the government's resource take out of the CbCR data before UT is run, and offers a variant that additionally enforces a minimum resource royalty. See [The resource-sector correction](#the-resource-sector-correction).

Second, it **allocates sales by destination** — to the jurisdiction of the final customer, rather than where the sale is booked. Because country-by-country data report only origin-based sales, the pipeline builds a destination measure (the local sales of multinationals plus their remotely-supplied digital services) from the OECD Analytical AMNE and OECD-WTO BaTIS datasets. See [Apportionment formulas](#apportionment-formulas).

This repository is the replication package for **"A 500-billion-dollar decision for the world: Revenue impacts of global unitary taxation"**. (Part of the code was originally written for the *State of Tax Justice* report, hence the repository name.)

<br />

<!-- INSTALLATION -->
## Installation

```bash
conda env create -f environment.yml
conda activate unitary_taxation
```

All dependencies are public PyPI packages (pandas, NumPy, Matplotlib, scikit-learn, pycountry, python-docx, openpyxl, …). No private packages are required — the one country-code helper (`get_iso3`) is vendored in `1_clean.py` via `pycountry`. Requires Python 3.11 or newer.

Scripts resolve every path relative to the project root, so they can be launched from any working directory.

<br />

<!-- CONFIGURATION -->
## Configuration

All configuration lives in [`src/config.py`](src/config.py):

- **Analysis window** — `first_year = 2016` and `n_years = 7` give the 2016–2022 window. (Headline exhibits drop 2020 as a COVID outlier; see [Reporting conventions](#reporting-conventions).)
- **Raw-data paths** — point them at the most recent downloads in `data/raw/`; each path carries a comment with its source URL.
- **`DATA_QUALITY_EXCLUSIONS`** — `{LSO, FSM, GUF, BTN}`, jurisdictions whose CbCR profits are orders of magnitude above their real economy (e.g. Lesotho reports ~$38 bn/yr profit against a ~$2 bn GDP). Excluded from **presentation** outputs (rankings, income-group aggregates) only; the country-level estimate files keep them.
- **Output remap** — `output_dirs(topic)` maps the topic strings scripts pass into the paper-mirroring `output/` layout; to relocate a topic, edit the remap here rather than the scripts.

<br />

<!-- DATA SOURCES -->
## Data sources

| Input | Source |
|---|---|
| CbCR (aggregated Table I) | OECD Corporate Tax Statistics |
| Statutory CIT rates | OECD, Tax Foundation |
| Wages | ILO Wages and Working Time Statistics |
| GDP / population | World Bank WDI |
| Income groups | World Bank classification (pinned snapshot) |
| Resource government revenue | EITI, ICTD Government Revenue Dataset (GRD), World Bank resource rents, EIA, BGS |
| Company-level resource payments | EITI company disclosures matched to headquarters via Orbis |
| Destination-based sales keys | OECD Analytical AMNE, OECD-WTO BaTIS, WTO digitally-delivered trade, UN household consumption, ITU |

Hand-collected macro/CIT/wage overrides and their source URLs live in `data/raw/macro_variables/manual_imputation_values.csv` (consumed by `1_clean.py`). Hand-collected resource rates and their sources are in `data/raw/extractive/resource_profit_tax_rate.csv` (see [The resource-sector correction](#the-resource-sector-correction)).

<br />

<!-- PIPELINE -->
## The pipeline

Scripts live in `src/` and run in numeric order; the number/letter prefix **is** the run order. Steps 1–3 prepare the data, step 4 builds the resource-corrected datasets, steps 5–6 estimate UT and consolidate, and the 7-series scripts produce the paper exhibits.

| # | Script | What it does | Key output |
|---|---|---|---|
| **1** | `1_clean.py` | Corrects the CbCR for **dividend double-counting** in tax havens (following García-Bernardo, Janský & Zucman (2026) and García-Bernardo & Janský (2024)), computes the reported-profit **ETR family** (`_etr_construction.py`), and merges in the other raw sources (CIT, wages, GDP, population, income groups). | `data/final/cbcr_main.csv` |
| **1a** | `1a_destination_based_sales.py` | Builds the destination-based-sales allocation keys — the sales measure used in the **headline specification** (`mne_plus_dds_share`: multinational sales share including digitally-deliverable services), plus origin-based comparison keys. Merged in step 2. | `data/intermediate/destination_based_sales.csv` |
| **1b** | `src/1b_orbis_universe/` | Builds the multinational-group **presence matrix** from Orbis: for each headquarter country × market, the number of in-scope (≥ €750 M revenue) groups that operate there. It tells the destination-sales step how much of a CbCR cell's group population is actually observed in a given market, so the destination sales share can be down-weighted accordingly (the `_nexus` variants). | `data/intermediate/extractive/cbcr_universe_presence.csv` |
| **2** | `2_disaggregate_aggregated_values.py` | Turns "bad reporter" continent / rest-of-world aggregates into individual partner rows: conserves each aggregate, imputes real activity by a **gravity model** and profit by **partner profitability**. Merges in the step-1a sales keys. | `data/final/cbcr_main_disaggregated.csv` |
| **3** | `src/3_extractive_prep/` | Builds the **resource-payment panel**: for each source country, how much of the government's resource take flows to which headquarter country, split into pre-profit / post-profit / equity payments. Assembled in stages that move from raw sources up to a headquarter × source-country × year table (detailed in [Step 3 — extractive prep](#step-3--extractive-prep)). | `data/intermediate/extractive/resource_payments_by_hq_source_yearly.csv` |
| **4** | `4_correcting_cbcr_for_resource_payments.py` | Emits the three resource-corrected datasets and recomputes the non-resource ETR family. | `cbcr_main_excl_resource.csv`, `cbcr_main_excl_resource_floored.csv`, `cbcr_main_incl_resource.csv` |
| **5** | `5_estimate_profit_shifting.py` | Runs UT on **one** dataset (`RUN_DATASET`) over the formula × ETR-spec × rate-mode grid, always as full reapportionment. | `output/estimates/…/country_estimates__<spec>.csv` |
| **6** | `6_consolidate_country_estimates.py` | Concatenates the per-spec estimates into per-scenario summaries + rankings. | `summary_country_year_long.csv` |
| **7** | `7a`…`7j` | Paper exhibits (figures + tables); see [Running it](#running-it). | `output/paper/…` |

### Step 1 — cleaning and the reported-profit ETR family

`1_clean.py` corrects the CbCR for **dividend double-counting** in tax havens (following García-Bernardo, Janský & Zucman (2026) and García-Bernardo & Janský (2024)), computes the canonical **reported-profit ETR family** with `_etr_construction.compute_partner_year_etrs` (partner-year effective tax rates over a rolling window), and merges the cleaned data with the other raw inputs — CIT rates, ILO wages, World Bank GDP / population and income groups.

### Step 2 — disaggregation (single gravity + profitability method)

Countries that report only continent / rest-of-world aggregates instead of country-by-country detail are "bad reporters". Their domestic row is preserved as-is; their **foreign** aggregate is spread across **all structurally-eligible markets** (every real foreign country in the panel). On the resulting distributed rows:

- real activity (`n_employees`, `unrelated_party_revenues`, `tangible_assets_except_cash`) is imputed by the **García-Bernardo & Janský gravity/ML model**; `payroll` follows as employees × wage × 12;
- profit is imputed from each partner country's **own reported profitability** (a multi-factor, sign-preserving yield — loss-making partners keep a negative imputed profit), then rescaled to conserve the reported aggregate;
- all other variables are left blank on distributed rows.

Two guardrails cap implausible micro-state activity (a per-prediction cap and a per-country water-filling cap at 2× GDP / 0.5× population; recognised havens exempt). The headline sample uses **only reported rows** (`is_distributed == 0`), so the imputation never touches it — the imputed rows drive the appendix ("results when imputing missing rows") sample.

### Step 3 — extractive prep

Built in three stages (`3_1x` → `3_2x` → `3_3x`), run in numeric order, each moving to a finer level:

- **`3_1x` — download & clean each raw source.** The three EITI ingests first, each a distinct product — country revenues (`3_11`), production volumes (`3_12`), pre/post-profit/equity payment splits (`3_13`) — then GRD (`3_14`), World Bank rents (`3_15`), EIA (`3_16`), BGS (`3_17`).
- **`3_2x` — combine into a country × year panel** of government resource revenue: clean panel (`3_21`), calibrations (`3_22`/`3_23`), combined rents (`3_24`), consolidated royalty panel (`3_25`), carried-state classification fixes (`3_26`).
- **`3_3x` — bring payments to headquarter × source-country × year rows**: EITI company payments (`3_31`, the fourth EITI product) → Orbis entity universe (`3_32`) → match companies to headquarters (`3_33`) → operator disclosures (`3_34`) → EITI bilateral panel (`3_35`) → Orbis HQ ownership shares (`3_36` global, `3_37` per source country) → the **final cascade `3_38`** merging everything (EITI bilateral > operator > manual > GRD), with documented company payments as absolute anchors.
- **`3_39`** (run **after** step 4) writes a human-readable per-country dossier of the applied correction.

<br />

<!-- FOUR DATASETS / THREE SCENARIOS -->
## The four datasets and three scenarios

Step 4 produces three resource-corrected datasets which, with the untouched disaggregated baseline, form **four parallel inputs** UT can run on. They differ only in their profit/tax columns:

| Dataset | Profit base | UT view |
|---|---|---|
| `cbcr_main_disaggregated.csv` | reported profit | **Resources ignored** — UT on reported figures, extraction treated like any sector. |
| `cbcr_main_excl_resource.csv` | reported − resource profit base | **Resources excluded** — UT on non-extractive corporate income only. |
| `cbcr_main_excl_resource_floored.csv` | excl_resource, plus a minimum-royalty floor | **Resources excluded + minimum royalty** — the floor gap is counted separately as extra royalty revenue alongside UT revenue. |
| `cbcr_main_incl_resource.csv` | reported + pre-profit payments | **Resources included** — a *reference* dataset (compares UT yield with the actual resource take); not a paper scenario. |

The **three paper scenarios** are the first three:

1. **Resources ignored** (`disaggregated`) — the naïve comparison. (Never called "baseline".)
2. **Resources excluded** (`excl_resource`) — the baseline.
3. **Resources excluded + minimum-royalty floor** (`excl_resource_floored`) — UT revenue plus the IGF-ATAF minimum royalty, reported as separate streams.

Select a dataset with `RUN_DATASET` at the top of `5_estimate_profit_shifting.py` (or via the env var); the `DATASET_CONFIGS` dict maps each key to its input file, profit/tax columns, ETR suffix, and output topic.

**Non-resource ETRs are computed once.** The non-resource ETR family — the rate at which non-resource income is actually taxed — is computed on the `excl_resource` (profit, tax) pair via `_etr_construction.compute_partner_year_etrs` (5-year rolling window; reported rows only) and **carried** into the `incl_*` files unchanged, because it is the correct rate to apply regardless of which profit base UT uses.

<br />

<!-- FORMULAS -->
## Apportionment formulas

The formula weights apply to `[n_employees, unrelated_party_revenues, tangible_assets, payroll]`:

| Key | Weights | Description |
|---|---|---|
| `sales_employees` (default) | `[0.5, 0.5, 0, 0]` | 50 % employees, 50 % sales — **the headline formula** |
| `ccctb` | `[1/6, 1/3, 1/3, 1/6]` | EU CCCTB weights |
| `three_factors` | `[1/3, 1/3, 1/3, 0]` | classic three-factor |
| `double_weighted_sales` | `[0.25, 0.5, 0.25, 0]` | sales double-weighted |
| `employees_payroll` | `[0.5, 0, 0, 0.5]` | 50 % employees, 50 % payroll |

**Destination-based sales (the main specification).** The headline apportions sales to the **market where customers are** (destination), using the `destmnedds` measure built in step 1a — the multinational sales share including digitally-deliverable services. Step 5 also produces a `_nexus` version that down-weights the destination share by the covered fraction of the cell's reported multinational groups (from the step-1b Orbis presence matrix). The origin-based factor `unrelated_party_revenues` (where sales are *booked*) and the other destination measures are retained only as comparisons. The full **headline specification** is `sales_employees` with the `destmnedds` destination sales factor.

<br />

<!-- REVENUE SPECIFICATIONS (ETRs) -->
## Revenue specifications (ETRs)

Taxable-profit changes become revenue by valuing gained and lost profit at a tax rate — and the right rate differs for the two. Profit a country **gains** would have faced the rate where the real activity sits; profit it **loses** was reported without real activity and is typically taxed at a favourable rate. ETRs are built from the CbCR data over a five-year window (reported cells only), and in the resource-adjusted datasets are recomputed on non-resource profit and tax. The paper reports three specifications that bracket a range:

- **`cit_etr` (average) — headline.** Profit **gained** is valued at the **statutory CIT** rate; profit **lost** at the country's **average effective rate** on the profits concerned (the domestic-multinational ETR where the lost profit was booked by domestic multinationals, the foreign-multinational ETR otherwise).
- **`cit_etr` (10th percentile) — upper bound.** As the headline, but losses are valued at the low end of the effective-rate distribution across headquarters–partner pairs — closer to the rate shifted profit actually bears, which raises the net gain.
- **`etretr` — lower bound.** The **average effective rate on both** gains and losses (newly-apportioned profit assumed taxed at the current effective rate rather than the statutory rate).

All specifications are full reapportionment (no minimum-ETR threshold). See the methodology note for the exact formulas.

<br />

<!-- RESOURCE CORRECTION -->
## The resource-sector correction

To stop unitary taxation from reallocating profit a resource-producing country already taxes by right, step 4 removes resource-driven profit (and the matching tax) from the CbCR before UT runs. Two approaches are used according to data quality: a **payment-based** approach where government resource payments are well documented (EITI / GRD / hand-collected), and a coarser **tax-mismatch** approach elsewhere (attributing tax above the statutory CIT to extraction). Pre-profit payments (royalties, licence fees, bonuses) already reduce reported profit and are not removed again; only **profit-based resource taxes** and **state-equity capture** overlap the reported pool, and because they often tax the same underlying profit the correction removes the **larger** of the two, never their sum. The removed base is always **capped at the cell's booked profit**, and for a few producers whose headline rates understate the take (Equatorial Guinea, Papua New Guinea, Malaysia) profit is instead removed down to an independent **resource-rent** estimate. The non-resource ETR family is then recomputed on the corrected profit and tax.

A separate **minimum-royalty specification** simulates the IGF-ATAF variable royalty (rising 1 %→10 % of gross production value with the commodity price) for **low- and lower-middle-income** producers only, reported as an additional royalty-revenue stream alongside the UT result — not blended into it.

The full derivation — the two approaches, the equity-versus-tax choice, the rent floors, and the royalty schedule — is in the methodology note.

<br />

<!-- CONVENTIONS -->
## Reporting conventions

- **Headline sample** — reported rows only (`is_distributed == 0`). Parent-years reporting > 50 % of foreign unrelated-party revenue as aggregates are dropped (the *partial-reporter rule*). The imputed-row sample is an appendix robustness result.
- **Window** — per-year **average** over 2016–2022 **excluding 2020** (÷ 6), not the sum.
- **Currency** — constant **2025 US dollars**.
- **Revenue as a share** — expressed against multinational corporate-tax paid / the positive-profit base, never against total government revenue.

<br />

<!-- RUNNING IT -->
## Running it

Run the one-off data-prep steps first (`1_clean.py` → `1a` → `2_disaggregate_aggregated_values.py`, then the extractive prep `3_1x`…`3_38`). Then the resource-correction → UT → consolidation portion is orchestrated end-to-end:

```bash
python src/_run_pipeline.py
```

This runs `3_38 → 4 → 5 (× datasets × reported/imputed) → 6`. To run a single UT dataset by hand, set `RUN_DATASET` (in code or via env) at the top of `5_estimate_profit_shifting.py` to one of `disaggregated | excl_resource | excl_resource_floored | incl_resource | …`, and `REPORTED_ONLY=1` for the headline sample, then run the script.

To rebuild all paper exhibits after the pipeline:

```bash
python src/_run_paper_main.py
```

The 7-series exhibit scripts (each owns one concept and produces its figures + tables for both samples):

| Script | Produces |
|---|---|
| `7a_coverage_scaleup.py` | Figure 1 (global scale-up) + coverage; runs first (feeds ghost bars) |
| `7b_formula_results.py` | Figures 2–4 + Tables 2–3 (results by formula) |
| `7c_resource_rights.py` | Figures 5–7 + Table 4 (the three resource treatments) |
| `7d_factor_incidence.py` | Figure 8 (factor incidence) |
| `7e_destination_sales.py` | Figure 9 (origin vs destination sales) |
| `7f_loss_consolidation.py` | Figure 10 (loss consolidation) |
| `7g_breakeven_and_leakage.py` | Break-even ETRs + haven-leakage ratio (last analysis) |
| `7h`–`7j` | Appendix: gravity (imputed) sample, overview, bootstrap confidence intervals |

Region-grouped twins of the income-group figures go to `output/paper/appendix_b/` (Appendix B). Every figure is also saved as a vector PDF, and every table as a brand-styled LaTeX float, alongside the PNG/CSV.

<br />

<!-- OUTPUT -->
## Output layout

`output/` mirrors the paper:

```
output/
  paper/
    main_text/      <- Figures 1–10, Tables 1–4
    appendix/       <- appendix figures/tables
    appendix_b/     <- region-grouped figure twins
  estimates/
    reported_only/      <- HEADLINE sample (is_distributed == 0)
    with_imputed_rows/  <- gravity-imputed sample (appendix)
      1_resources_ignored/  2_resources_excluded/  3_minimum_royalty_added/
      resources_included_reference/  positive_profits_only/
  analysis/         <- cross-scenario & cross-sample analyses
  checks/           <- QA & diagnostics (bootstrap SEs, disaggregation, ETR by income group)
  archive/          <- superseded runs
```

<br />

<!-- REPO LAYOUT -->
## Repository layout

```
data/
  raw/            <- External downloads / API pulls / hand-curated files only,
                     in <source>_<content>_<date>.<ext> kind-of-data subfolders.
  intermediate/   <- Pipeline working files (incl. the extractive/ sub-pipeline).
  final/          <- Deliverable UT datasets (cbcr_main_*.csv).
  guides/         <- Database codebooks + an index of every external source.

src/
  1_clean.py … 6_consolidate_country_estimates.py   <- the pipeline (run order)
  7a … 7j                                           <- paper exhibits
  _*.py                                             <- shared modules
  1b_orbis_universe/       <- Orbis CbCR-universe passes (destination nexus)
  3_extractive_prep/       <- extractive sub-pipeline + shared price/path modules

unitary_taxation_explorer/  <- the interactive results explorer (single-file web app)
output/           <- see Output layout above (generated by running the pipeline)
environment.yml   <- conda environment
```

<br />

<!-- BUILT WITH -->
## Built with

* [Python 3.11](https://www.python.org/) · [pandas](https://pandas.pydata.org/) · [NumPy](https://numpy.org/) · [scikit-learn](https://scikit-learn.org/) · [Matplotlib](https://matplotlib.org/)
