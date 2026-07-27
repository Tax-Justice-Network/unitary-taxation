# A 500-billion-dollar decision for the world — replication package

Replication package for **“A 500-billion-dollar decision for the world:
Revenue impacts of global unitary taxation”** (Tax Justice Network & Public
Services International, 2026).

- 📄 **Main report:** [link to be added]
- 📘 **Methodology note:** [link to be added] — the full description of every
  data source, cleaning step and estimation choice implemented in this code.
- 🌍 **Unitary Taxation Explorer:** [link to be added] — interactive
  country-level results (built by `src/_results_explorer_build.py`; a ready
  copy ships in `unitary_taxation_explorer/`).

## What this estimates

The effect of **unitary taxation with formulary apportionment**: the change in
each country's taxable profits and corporate tax revenue if multinationals
were taxed as single firms, with profits apportioned to countries by their
real economic activity. Estimates are built on the OECD's aggregated
country-by-country reporting (CbCR) data, corrected for dividend double
counting and for countries' existing resource-rent capture, with
destination-based sales measures constructed from OECD Analytical AMNE and
OECD-WTO BaTIS data. All monetary results are in constant 2025 US dollars,
reported as yearly averages over 2016–2022 (2020 excluded).

## Environment

```bash
conda env create -f environment.yml
conda activate unitary_taxation
```

All dependencies are public PyPI packages.

## Data

`data/raw/` contains every **redistributable** input, organised by kind
(`cbcr/`, `tax_rates/`, `macro_variables/`, `destination_based_sales/`,
`country_info/`, `extractive/`, `context/`), with `data/guides/README.md` as
the index of every external database (source, URL, vintage, consumer).

Inputs we may **not** redistribute must be obtained directly from their
providers and dropped into the documented paths:

| Source | Used for | Obtain from |
|---|---|---|
| OECD aggregated CbCR (Table I) | core dataset | OECD Corporate Tax Statistics (free download) |
| OECD-WTO BaTIS (Dec 2025) | digitally deliverable services imports | WTO/OECD (free download) |
| Bureau van Dijk Orbis extracts | resource-payment HQ attribution; nexus matrix | proprietary — Orbis licence required |
| Gravity-model training inputs | disaggregation of aggregate rows | see `data/guides/README.md` |

The pipeline runs end-to-end without the proprietary Orbis inputs for the
reported-only headline sample; the affected intermediate products
(`data/intermediate/extractive/*.csv`) are included pre-computed.

## Pipeline

Run from `src/`, in order (details in the methodology note and each script's
docstring):

1. `1_clean.py` — clean & merge CbCR, rates, macro data; dividend-double-counting correction
2. `1a_destination_based_sales.py` — destination-based sales measures (AAMNE + BaTIS)
3. `2_disaggregate_aggregated_values.py` — gravity-based disaggregation of aggregate rows
4. `3_extractive_prep/` — resource-rent capture panel (numbered stages, `3_11` → `3_39`)
5. `4_correcting_cbcr_for_resource_payments.py` — the three resource-corrected datasets
6. `5_estimate_profit_shifting.py` — unitary-taxation estimation (per dataset; `RUN_DATASET` env)
7. `6_consolidate_country_estimates.py` — per-scenario consolidation
8. `7a`–`7j` — paper figures and tables

`src/_run_pipeline.py` orchestrates steps 5–7 across the three scenarios.

## Questions

Our work is always in progress. If you have any questions, concerns, or
ideas, we would love to hear them — please reach out to
[alison@taxjustice.net](mailto:alison@taxjustice.net).
