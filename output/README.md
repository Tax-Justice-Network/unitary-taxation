# Output folder structure

The tree mirrors the paper — *"Unitary taxation"* (main document) and
*"Unitary Taxation_Appendix"*. Every folder name says what is inside; each
folder holds a `tables/` and a `figures/` subfolder where applicable.

```
output/
  paper/                  The exhibits exactly as numbered in the documents.
    main_text/              Figures 1–10 and Tables 1–4 of the main paper.
    appendix/               Figures and tables of the Appendix document (B–H).

  estimates/              Full estimation output, one folder per scenario.
    reported_only/          MAIN SAMPLE: directly reported CbCR rows only
                            (is_distributed == 0; no imputation).
    with_imputed_rows/      Full sample: aggregate rows disaggregated with the
                            gravity model (used in Appendix F).
      1_resources_ignored/            scenario 1 — resources treated like any sector
      2_resources_excluded/           scenario 2 — resource rent capture removed
      3_minimum_royalty_added/        scenario 3 — scenario 2 + IGF-ATAF minimum royalty
      resources_included_reference/   reference dataset (not a paper scenario)
      positive_profits_only/          upper bound used for loss consolidation
      # inside each scenario: tables/ holds run_summary.csv, the per-spec
      # country_estimates / misalignment files, and the summary_* tables
      # consolidated by script 6; figures/ holds that run's standard charts.

  analysis/               Cross-scenario and cross-sample analyses feeding the
                          paper sections; each folder is named for what it shows.
    scenario_comparison/    the three resource scenarios side by side
                            (reported_only/, with_imputed_rows/, detail/ = fuller
                            multi-window summaries, tax_base/ = misalignment-only view)
    origin_vs_destination/  origin- vs destination-based sales factor
    country_overview/       per-country metric overview spreadsheets + long table
    loss_consolidation/     cross-border loss-consolidation adjustment (Figure 10)
    haven_leakage/          world revenue loss per $1 a haven collects
    factor_incidence/       single-factor revenue effects (Figure 8)
    resource_correction/    resource-payment correction summary table
    context_comparisons/    UT gains vs IMF credit / Marshall Plan
    classic_sotj_specification/  reference run of the classic SOTJ 15% spec

  extractive/             Resource sub-pipeline outputs (EITI, rents, dossiers).

  checks/                 QA and diagnostics: bootstrap standard errors,
                          destination-sales checks, disaggregation checks,
                          ETR-by-income-group, country profiles, outlier flags.

  other_projects/         Material NOT part of the unitary-taxation paper
                          (US/EU analyses, SOTJ 2026, Germany, …). Kept here so
                          the UT project can be lifted out cleanly for the
                          replication package.

  archive/                Superseded runs, retired specifications, old drafts.
```

`output_dirs(topic)` in `src/config.py` maps the topic strings that scripts
pass into this layout — to relocate a folder, edit the mapping there, not the
scripts. Scripts that *read* another run's estimation output use
`config.estimates_dir(sample, scenario)`.

Most of `estimates/` is regenerable and gitignored (the per-spec files run to
tens of GB); only figures (.png), spreadsheets (.xlsx) and the small summary
tables are committed.
