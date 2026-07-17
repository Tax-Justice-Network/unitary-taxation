<!-- TITLE AND SUBTITLE -->
<br />
<p align="center">
  <h1 align="center">SOTJ Profit Shifting Estimates</h1>
</p>
<p align="center">Profit-shifting and unitary-taxation estimates for the State of Tax Justice (SOTJ) report, with a resource-sector correction.</p>

<br />

<!-- TABLE OF CONTENTS -->
<details open="open">
  <summary><h2 style="display: inline-block">Table of Contents</h2></summary>
  <ol>
    <li><a href="#about-the-project">About the project</a></li>
    <li><a href="#installation">Installation</a></li>
    <li><a href="#configuration">Configuration</a></li>
    <li><a href="#pipeline">Pipeline</a></li>
    <li><a href="#scenarios">Scenarios</a></li>
    <li><a href="#running-it">Running it</a></li>
    <li><a href="#project-organization">Project organization</a></li>
    <li><a href="#documentation">Documentation</a></li>
  </ol>
</details>

<br />

<!-- ABOUT THE PROJECT -->
## About the project

This repository produces profit-shifting and **unitary-taxation (UT) / formulary-apportionment** estimates for the SOTJ report, using the misalignment method on OECD Country-by-Country Reports (CbCR). The base methodology follows [García-Bernardo & Janský (2024)](https://www.sciencedirect.com/science/article/pii/S0305750X23003455).

On top of the standard estimates, the pipeline **corrects for the extractive sector**: in resource-rich countries a large share of reported CbCR profit comes from natural-resource extraction, and apportioning that profit away by a labour/sales/assets formula produces spurious "losses". We therefore strip resource-driven profit and the government's resource take out of the data before running UT — and, as an alternative framing, also offer a version that adds a resource factor to the formula itself. See [`docs/scenarios_methodology.md`](docs/scenarios_methodology.md).

<br />

<!-- INSTALLATION -->
## Installation

```bash
conda env create -f environment.yml
conda activate sotj_profit_shifting_estimates
```

Key dependencies include `tjn_tools` and `tjn_internal` (TJN internal packages installed from GitHub).

In VS Code, select the `sotj_profit_shifting_estimates` interpreter (`F1` → *Python: Select Interpreter*).

<br />

<!-- CONFIGURATION -->
## Configuration

Before running, update [`src/config.py`](src/config.py):

- Set `first_year` and `n_years` for the analysis window.
- Point the raw-data paths (CbCR, CIT rates, ILO wages, World Bank GDP/population, WHO health expenditure, etc.) at the most recent downloads in `data/raw/`. Each path has a comment with its source URL.

All scripts resolve paths relative to the project root, so they can be run from any working directory.

<br />

<!-- PIPELINE -->
## Pipeline

Scripts live in `src/` and run in order. Steps 1–3 prepare the data; step 4 builds the resource-corrected datasets; steps 5–9 estimate UT and produce the report and figures.

| # | Script | Does | Output |
|---|---|---|---|
| 1 | `1_clean.py` | Cleans and merges the raw sources; computes the canonical reported-profit ETR family. | `data/final/cbcr_main.csv` |
| 1b | `1b_destination_based_sales.py` | Builds the destination-based-sales (CFB/ADS) allocation key, merged in step 2. | intermediate |
| 2 | `2_disaggregate_aggregated_values.py` | Distributes "bad reporter" continent/ROW aggregates to specific partners by pooled-median weights. | `data/final/cbcr_main_disaggregated.csv` |
| 3 | `src/3_extractive_prep/` (`1_6` → `1_7a` → `1_7` → `1_8`) | EITI company payments → Orbis HQ match → `(source, HQ, commodity, year)` resource-payment panel (cascade EITI > manual > GRD > rent-proxy). | `data/intermediate/extractive/resource_payments_by_hq_source_yearly.csv` |
| 4 | `4_correcting_cbcr_for_resource_payments.py` | Emits the **three resource-corrected datasets** and recomputes the non-resource ETR family. | `cbcr_main_excl_resource.csv`, `cbcr_main_incl_resource.csv`, `cbcr_main_excl_resource_floored.csv` |
| 5 | `5_estimate_profit_shifting.py` | Runs UT (formulary apportionment + misalignment) on **one** dataset, selected by `RUN_DATASET`, over multiple formula × ETR-spec × rate-mode combinations. | `output/unitary_taxation_<dataset>/` |
| 6 | `6_winners_losers_analysis.py` | Consolidates the per-spec country estimates into per-topic summary tables and headline figures. | `summary_country_year_long.csv` etc. |
| 7 | `7_three_dataset_comparison.py` | Tax-base (misalignment) winners/losers across the three main scenarios. | `output/comparison/` |
| 8 | `8_five_scenario_report.py` | The full five-scenario × four-formula comparison (three main + two alternative). | `output/five_scenarios/` |
| 9 | `9_three_scenario_figures.py`, `9b_country_examples.py` | The focused **three-scenario** figure deliverable + low-income country examples. | `output/three_scenarios/` |
| QA | `src/3_extractive_prep/qa_resource_payment_correction.py` | PASS/FAIL/WARN checks across the resource correction. | stdout |

The **four parallel UT datasets** (the untouched `cbcr_main_disaggregated.csv` baseline plus the three from step 4) differ only in their profit/tax columns:

| Dataset | Meaning |
|---|---|
| `cbcr_main_disaggregated.csv` | Resources ignored — UT on reported figures. |
| `cbcr_main_excl_resource.csv` | Resources excluded — strip resource profit base & post-profit tax. |
| `cbcr_main_excl_resource_floored.csv` | Excluded **+** the IGF-ATAF minimum-royalty floor. |
| `cbcr_main_incl_resource.csv` | Resources included — add pre-profit payments back + a 5th `resource_factor_usd`. |

<br />

<!-- SCENARIOS -->
## Scenarios

The estimates are organised as scenarios. **The three-scenario data-correction route is the main specification**; the two resource-factor scenarios are kept as an **alternative / backup** framing (not deleted, but not headline).

**Main specification (Route A — correct the data):**

1. **Resources ignored** — baseline, `disaggregated`.
2. **Resources excluded** — `excl_resource`.
3. **Resources excluded + minimum-royalty floor** — `excl_resource_floored` (UT revenue + the IGF-ATAF Cat 1 floor add-on, reported as separate streams).

**Alternative / backup (Route B — add a resource factor):**

4. **Resource factor at 30%** within a 5-factor formula — `incl_resource`.
5. **Resource as an equal-weight factor** — `incl_resource`.

`8_five_scenario_report.py` computes all five; scripts `7`/`9`/`9b` produce the focused Route-A deliverable. All UT runs use reported-only data (`is_distributed == 0`). Full detail in [`docs/scenarios_methodology.md`](docs/scenarios_methodology.md).

> The earlier **carve-out-then-UT** approach (`3_resource_contribution.py`, `4_carveout.py`, `5b_carveout_then_ut.py`, …) has been superseded by the dataset-adjustment scheme above and moved to `src/archive/`. It is kept for reference only; see [`docs/extractive/approach_summary.md`](docs/extractive/approach_summary.md).

<br />

<!-- RUNNING IT -->
## Running it

Run the data-prep steps once (`1_clean.py` → `1b` → `2_disaggregate_aggregated_values.py`, then the extractive prep through `1_7`). After that, the resource-correction → UT → report portion is orchestrated end-to-end:

```bash
python src/_run_pipeline.py
```

This runs `1_8 → 4 → 5 (× the four datasets, with and without reported-only) → 6 → 8`. To run a single UT dataset by hand, set `RUN_DATASET` (in code or via the env var) at the top of `5_estimate_profit_shifting.py` to one of `disaggregated | excl_resource | incl_resource | excl_resource_floored | excl_resource_floored_cat2 | excl_resource_floored_cat3`, then run the script.

<br />

<!-- PROJECT ORGANIZATION -->
## Project organization

```
data/
  raw/            <- External downloads / API pulls / hand-curated files only.
  intermediate/   <- Pipeline working files (incl. extractive/ sub-pipeline).
  final/          <- Deliverable UT datasets (cbcr_main_*.csv).
  archive/        <- Previous-year data, for reproducibility.

output/
  <topic>/tables/ , <topic>/figures/   <- e.g. unitary_taxation_*, five_scenarios,
                                           three_scenarios, comparison, extractive.
  archive/        <- Previous-year outputs.

src/
  *.py            <- The pipeline (numbered in run order) + shared _*.py modules.
  3_extractive_prep/  <- Extractive sub-pipeline + shared price/path modules.
  archive/        <- Superseded scripts (incl. the carve-out track), for reference.

docs/             <- Methodology write-ups and source references.
environment.yml   <- Conda environment.
CLAUDE.md         <- Detailed developer/agent guidance.
```

<br />

<!-- DOCUMENTATION -->
## Documentation

- [`CLAUDE.md`](CLAUDE.md) — detailed workflow, formula options, bad-reporter handling, the four-dataset scheme.
- [`docs/scenarios_methodology.md`](docs/scenarios_methodology.md) — the scenario logic (main + alternative).
- [`docs/extractive/resource_payment_correction.md`](docs/extractive/resource_payment_correction.md) — the resource-payment correction pipeline and column reference.
- [`docs/extractive/`](docs/extractive/) — extractive data sources, EITI/Orbis matching, and the (legacy) carve-out approach.

<br />

<!-- BUILT WITH -->
## Built with

* [Python 3.11](https://www.python.org/)
* [pandas](https://pandas.pydata.org/) / [NumPy](https://numpy.org/) / [Matplotlib](https://matplotlib.org/)
