# %%
"""
5 — Estimate profit shifting via unitary-taxation formulary apportionment.

For ONE input dataset per run (RUN_DATASET: the baseline, resources-excluded,
resources-included or minimum-royalty-floored file — see DATASET_CONFIGS), this
script computes, for every specification in the grid (formula x ETR definition x
tax-rate mode), each jurisdiction's misaligned profit (reported minus
formula-implied) and the tax-revenue change from taxing profits where the real
activity is. Destination sales-factor variants down-weight the market share by
the covered fraction of a cell's reported MNE groups using the Orbis nexus
matrix (cbcr_universe_presence.csv, step 1b).

HEADLINE SPECIFICATION of the paper. The full grid is reported alongside it —
the other formula families and scenarios are equally valid policy designs run
for comparison, not mere robustness checks:
  dataset   = excl_resource (scenario 2, resources excluded)
  sample    = reported-only (REPORTED_ONLY=1, is_distributed == 0; parent-years
              with > 50% of foreign unrelated-party revenues in aggregates are
              dropped — the partial-reporter rule)
  formula   = sales_employees_destmnedds  (50% employees, 50% sales, with the
              sales slot filled by the DESTINATION-based key: all-sector MNE
              local sales + the MNE share of digitally-deliverable services
              imports, built in 1a_destination_based_sales.py)
  ETR       = domfor (cell-matched domestic/foreign effective rate)
  rate mode = loss_cit_gain_etr (UT gainers priced at max(CIT, ETR), UT losers
              at the ETR)
  threshold = etrmax_inf (always: full reapportionment, no minimum-rate filter —
              the naming tag is fixed; see the ETR_THRESHOLD note)
The paper reports per-year averages over 2016-2022 excluding 2020, in constant
2025 USD (both applied downstream, 7d and the exhibit scripts).

Pipeline step 5 — after 4 (resource correction), before 6 (consolidation).

Reads:
  data/final/cbcr_main_<dataset>.csv                          — the ONE dataset selected by RUN_DATASET (DATASET_CONFIGS input_file)
  data/intermediate/extractive/cbcr_universe_presence.csv     — Orbis (hq, market) group-count nexus for destination _nexus variants (step 1b)
  data/intermediate/orbis_hq_subsidiary_presence.csv          — legacy binary-presence fallback when the group-count matrix is absent

Writes (per spec, into the run's output topic + "_reported" when REPORTED_ONLY):
  output/<topic>/tables/<sample>/country_estimates__<spec>.csv — per-country UT gain/loss & revenue change
  output/<topic>/tables/<sample>/misalignment__<spec>.csv      — cell-level misalignment detail
  output/<topic>/tables/<sample>/aggregate_results__<spec>.csv — world/income-group aggregates
  output/<topic>/tables/<sample>/run_summary.csv               — specs of this run; gates what script 6 consumes (merged, not overwritten)

Usage:
  python 5_estimate_profit_shifting.py                         — headline: RUN_DATASET=disaggregated, REPORTED_ONLY=1
  RUN_DATASET=excl_resource REPORTED_ONLY=1 python 5_estimate_profit_shifting.py — pick a dataset / sample via env
  (RUN_DATASET is one of the DATASET_CONFIGS keys; each writes to its own
   output/unitary_taxation_<dataset>[_reported]/ topic. For parallel runs, copy
   this file and change the single RUN_DATASET line.)

Author: Alison Schultz (based on Javier Garcia-Bernardo's work).
Created: 2026-07-17.  Last updated: 2026-07-25.
"""

# %% MARK: 1. Imports
import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from itertools import product

# On Windows, stdout defaults to cp1252 and crashes when any printed line
# embeds the Arabic characters from the project path (the long run_summary
# table at the end prints rows containing the absolute file paths). Use
# UTF-8 with error-replacement so the run reaches the figure / summary
# export stages.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import *

pd.set_option("display.max_columns", None)
pd.options.display.float_format = "{:,.2f}".format


# %% MARK: 2. Dataset configuration (RUN_DATASET)
# [1] Dataset configuration — which input file this run estimates on
#
# The script reads ONE input file per run, configured by `RUN_DATASET` below.
# Each entry of `DATASET_CONFIGS` is self-contained: it names the input file,
# the profit and tax columns to use, the ETR-column suffix (the four
# partner-year ETR columns and the diagnostic pair-ETR column are derived
# from this), and the output topic that drives `output_dirs(...)`.
#
# To run on a different dataset, change `RUN_DATASET` to a key of
# `DATASET_CONFIGS` and re-run the script. For parallel runs on different
# datasets, copy this file (e.g. `5_run_excl_resource.py`) and change the
# single line.
DATASET_CONFIGS = {
    # Baseline full sample: bad-reporter aggregates disaggregated by the gravity/ML
    # imputation (the single method; `cbcr_main_disaggregated.csv` IS the gravity
    # output). REPORTED_ONLY=1 drops imputed rows for the reported-only view.
    "disaggregated": {
        "input_file": "cbcr_main_disaggregated.csv",
        "profit_var": "profit_loss_before_income_tax_corrected",
        "tax_var": "income_tax_paid_on_cash_basis",
        "etr_suffix": "corrected",
        "output_topic": "unitary_taxation_disaggregated",
    },
    "excl_resource": {
        "input_file": "cbcr_main_excl_resource.csv",
        "profit_var": "profit_loss_excl_resource",
        "tax_var": "income_tax_paid_on_cash_basis_excl_resource",
        "etr_suffix": "excl_resource",
        "output_topic": "unitary_taxation_excl_resource",
    },
    "incl_resource": {
        "input_file": "cbcr_main_incl_resource.csv",
        "profit_var": "profit_loss_incl_resource",
        "tax_var": "income_tax_paid_on_cash_basis_incl_resource",
        "etr_suffix": "excl_resource",  # ETRs carried over from excl_resource
        "output_topic": "unitary_taxation_incl_resource",
    },
    "excl_resource_floored": {
        # Resources excluded AND the IGF-ATAF Cat 1 floor assumed to have been
        # captured. The comparison is
        #   IS  = today's system, NO royalty (reported leg = profit_loss_
        #         excl_resource — the profit countries actually book & tax now)
        #   vs COUNTERFACTUAL = UT on the FLOORED pool (pool_var — the royalty
        #         gap is deductible, shrinking the apportionable pool) + the
        #         royalty itself as a separate revenue stream (addon).
        # Using the floored column for BOTH legs would implicitly assume the
        # royalty already existed in the "IS" — double-crediting source
        # countries (they would get the royalty AND a UT "recovery" of profit
        # they in fact already tax today).
        "input_file": "cbcr_main_excl_resource_floored.csv",
        "profit_var": "profit_loss_excl_resource",
        "pool_var": "profit_loss_excl_resource_floored",
        "addon_var": "floor_add_on_cat1_usd",
        "tax_var": "income_tax_paid_on_cash_basis_excl_resource_floored",
        "etr_suffix": "excl_resource",
        "output_topic": "unitary_taxation_excl_resource_floored",
    },
    "excl_resource_floored_allrowsalloc": {
        # SENSITIVITY: same Cat-1 floor, but the
        # floor add-on stays allocated across ALL rows (reported + imputed)
        # instead of being re-allocated onto reporters. Run reported-only like
        # the headline: the estimation then carries only the slice of each
        # country's floor that fell on directly-reported rows — the counterpart
        # to the default file, which loads a source's WHOLE floor onto whichever
        # parents report it directly. Bracket the allocation choice with the two.
        "input_file": "cbcr_main_excl_resource_floored_allrows.csv",
        "profit_var": "profit_loss_excl_resource",
        "pool_var": "profit_loss_excl_resource_floored",
        "addon_var": "floor_add_on_cat1_usd",
        "tax_var": "income_tax_paid_on_cash_basis_excl_resource_floored",
        "etr_suffix": "excl_resource",
        "output_topic": "unitary_taxation_excl_resource_floored_allrowsalloc",
    },
    "excl_resource_floored_cat2": {
        "input_file": "cbcr_main_excl_resource_floored.csv",
        "profit_var": "profit_loss_excl_resource",
        "pool_var": "profit_loss_excl_resource_floored_cat2",
        "addon_var": "floor_add_on_cat2_usd",
        "tax_var": "income_tax_paid_on_cash_basis_excl_resource_floored_cat2",
        "etr_suffix": "excl_resource",
        "output_topic": "unitary_taxation_excl_resource_floored_cat2",
    },
    "excl_resource_floored_cat3": {
        "input_file": "cbcr_main_excl_resource_floored.csv",
        "profit_var": "profit_loss_excl_resource",
        "pool_var": "profit_loss_excl_resource_floored_cat3",
        "addon_var": "floor_add_on_cat3_usd",
        "tax_var": "income_tax_paid_on_cash_basis_excl_resource_floored_cat3",
        "etr_suffix": "excl_resource",
        "output_topic": "unitary_taxation_excl_resource_floored_cat3",
    },
}

RUN_DATASET = os.environ.get("RUN_DATASET", "disaggregated")
# <-- change RUN_DATASET (in code or env var) per run.

# REPORTED_ONLY toggle: when True, filter input CbCR rows to
# `is_distributed == 0` — i.e., keep only directly-reported country rows and
# drop all rows that came from disaggregating bad-reporter aggregates. This
# gives a "no imputation" sensitivity view of every scenario. Bad reporters
# (Ireland, UK, Korea, Sweden, etc.) whose non-domestic data is entirely in
# aggregates will essentially disappear from the analysis. The output goes
# to a `_reported` suffixed topic so it doesn't overwrite the standard run.
REPORTED_ONLY = os.environ.get("REPORTED_ONLY", "1") not in ("0", "false", "False", "")

# Partial-reporter rule, reported-only sample:
# a parent-year whose AGGREGATE-reported share of foreign unrelated-party
# revenues exceeds this threshold is dropped entirely — keeping only its few
# real partner rows would misrepresent a mostly-aggregated filing as a
# bilateral one (Netherlands 2018-22 held 81-98% of its foreign revenues in
# aggregates). The share is measured on the distributed (is_distributed == 1)
# rows, which carry exactly the aggregate-origin activity. Headline impact of
# the rule: world −0.4%, low/lower-middle income unchanged.
PARTIAL_REPORTER_MAX_AGG_SHARE = float(os.environ.get("PARTIAL_REPORTER_MAX_AGG_SHARE", "0.5"))

_cfg = dict(DATASET_CONFIGS[RUN_DATASET])
# Floored datasets are written in two allocations of the minimum-royalty floor
# (script 4): the default file re-allocates the floor onto reported rows (for
# the reported sample, where it is the headline); the `_allrows` file splits it
# across all rows (correct for the gravity / full-disaggregation sample). Pick
# the file that matches the sample so neither allocation contaminates the other.
if RUN_DATASET.startswith("excl_resource_floored") and not REPORTED_ONLY:
    _cfg["input_file"] = _cfg["input_file"].replace(
        "cbcr_main_excl_resource_floored.csv",
        "cbcr_main_excl_resource_floored_allrows.csv",
    )
# Overrides for the bootstrap driver (run_bootstrap.py): feed a per-draw input
# file and a per-draw output topic without adding a DATASET_CONFIGS entry.
if os.environ.get("RUN_INPUT_FILE"):
    _cfg["input_file"] = os.environ["RUN_INPUT_FILE"]
if os.environ.get("RUN_OUTPUT_TOPIC"):
    _cfg["output_topic"] = os.environ["RUN_OUTPUT_TOPIC"]
PROFIT_VAR = _cfg["profit_var"]
# Floored datasets apportion a DIFFERENT (smaller) pool than the reported "IS"
# leg: POOL_VAR is the floored profit column (royalty gap deducted), PROFIT_VAR
# the excl_resource reported leg. None for all other datasets (pool == reported).
POOL_VAR = _cfg.get("pool_var")
ADDON_VAR = _cfg.get("addon_var")
TAX_VAR = _cfg["tax_var"]
ETR_SUFFIX = _cfg["etr_suffix"]
_OUTPUT_TOPIC = _cfg["output_topic"] + ("_reported" if REPORTED_ONLY else "")

# Partner-year ETR columns derived from the active suffix. The
# parent-partner pair ETR is a diagnostic (never used in UT) — kept available
# in column ordering and validation, but not in ETR_SPECS.
ETR_FAMILY_PARTNER = [
    f"etr_average_{ETR_SUFFIX}",
    f"etr_partner_median_{ETR_SUFFIX}",
    f"etr_partner_p25_{ETR_SUFFIX}",
    f"etr_partner_p10_{ETR_SUFFIX}",
    f"etr_partner_min_{ETR_SUFFIX}",
]
ETR_COL_PAIR = f"etr_parent_partner_{ETR_SUFFIX}"
ETR_COL_DOMESTIC = f"etr_domestic_{ETR_SUFFIX}"
ETR_COL_FOREIGN = f"etr_foreign_{ETR_SUFFIX}"
ETR_COL_AVERAGE = f"etr_average_{ETR_SUFFIX}"
ETR_COL_MEDIAN = f"etr_partner_median_{ETR_SUFFIX}"
ETR_COL_P25 = f"etr_partner_p25_{ETR_SUFFIX}"
ETR_COL_P10 = f"etr_partner_p10_{ETR_SUFFIX}"
ETR_COL_MIN = f"etr_partner_min_{ETR_SUFFIX}"
# Cell-matched domestic/foreign rate (derived in ensure_tax_rate_columns): the
# partner's DOMESTIC ETR on own-MNE home cells (iso_parent == iso_partner), its
# FOREIGN ETR on foreign-MNE cells — i.e. the rate the profit in that cell
# actually bears — with the average-ETR family (then CIT) as fallback.
ETR_COL_DOMFOR = f"etr_domfor_{ETR_SUFFIX}"

# The UT estimation is always FULL reapportionment: no minimum-ETR threshold.
# The `etrmax_inf` tag in file names and the `etr_threshold` metadata column
# (constant inf) are kept for continuity with the output naming scheme and the
# downstream consumers that filter on them. The finite-threshold machinery
# (minimum-rate haven gating, ETR_THRESHOLDS env grid) lives only in
# src/archive/5_estimate_profit_shifting_full.py — run that copy for
# minimum-ETR-threshold recovery experiments.
ETR_THRESHOLD = np.inf

OUTPUT_TABLES, OUTPUT_FIGURES = output_dirs(_OUTPUT_TOPIC)
# OUTPUT_ROOT keeps backward-compatible naming as the per-sample tables root.
OUTPUT_ROOT = OUTPUT_TABLES

# %% MARK: 3. Formula specifications
# [2] Formula specifications — the HEADLINE family first, then the
# other formula families (equally relevant policy options, run for comparison).
# Weights refer to [n_employees, unrelated_party_revenues (sales),
# tangible_assets_except_cash, payroll].
FORMULAS = [
    # HEADLINE family: 50% employees + 50% sales. The paper's headline is the
    # DESTINATION variant sales_employees_destmnedds (generated in [3]);
    # this origin-based version is its comparison.
    {
        "name": "sales_employees",
        "formula_vars": [
            "n_employees",
            "unrelated_party_revenues",
            "tangible_assets_except_cash",
            "payroll",
        ],
        "weights": [0.5, 0.5, 0.0, 0.0],
    },
    # Comparison formula families — alternative apportionment designs, each a
    # policy option in its own right (reported throughout the paper):
    {
        "name": "employees_payroll",  # 50% employees, 50% payroll
        "formula_vars": [
            "n_employees",
            "unrelated_party_revenues",
            "tangible_assets_except_cash",
            "payroll",
        ],
        "weights": [0.5, 0.0, 0.0, 0.5],
    },
    {
        "name": "ccctb",  # EU CCCTB: 1/6 employees, 1/6 payroll, 1/3 sales, 1/3 assets
        "formula_vars": [
            "n_employees",
            "unrelated_party_revenues",
            "tangible_assets_except_cash",
            "payroll",
        ],
        "weights": [1 / 6, 1 / 3, 1 / 3, 1 / 6],
    },
    {
        "name": "double_weighted_sales",  # 25% employees, 50% sales, 25% assets
        "formula_vars": [
            "n_employees",
            "unrelated_party_revenues",
            "tangible_assets_except_cash",
            "payroll",
        ],
        "weights": [0.25, 0.5, 0.25, 0.0],
    },
    {
        "name": "three_factors",  # 1/3 employees, 1/3 sales, 1/3 assets
        "formula_vars": [
            "n_employees",
            "unrelated_party_revenues",
            "tangible_assets_except_cash",
            "payroll",
        ],
        "weights": [1 / 3, 1 / 3, 1 / 3, 0.0],
    },
]


# %% MARK: 4. Destination-based sales (headline)
# [3] Destination-based sales — the HEADLINE sales measure.
# The paper's headline sales factor is DESTINATION-based: where the customers
# are, not where the selling entity sits. The plain `unrelated_party_revenues`
# factor in the base families above is *origin*-based and serves as the
# comparison. For each sales-using 4-factor family we generate the destination
# variants by swapping the sales slot for a destination share column (built in
# 1a_destination_based_sales.py and merged into the dataset):
#   - destmnedds   : all-sector MNE sales + MNE-share DDS imports — HEADLINE
#   - destcfb      : consumer-facing only (cfb_share)
#   - destads      : automated digital services user proxy (ads_share)
# and, for each, a `_nexus` version applying the physical-establishment
# requirement: the market's destination share is down-weighted by the fraction
# of the cell's reported MNE groups that actually have an establishment there
# (coverage = min(n_groups / n_cbcr, 1); columns built in [3.1]
# `_attach_destination_factors`; `_nexus` is kept as the compact file tag).
# Formulas whose columns are absent
# from the active dataset are auto-skipped downstream, so these stay inert on
# samples that lack the destination columns. Prune DEST_MEASURES / the family
# list below to cut run count.
DEST_MEASURES = {
    # HEADLINE destination measure: ALL-sector AAMNE MNE destination sales
    # (incl. finance — matches the CbCR sales variable's scope) + the MNE share
    # of BaTIS digitally-DELIVERABLE services imports (Handbook definition,
    # excluding SH / charges for IP; WTO-DDS is the loud fallback when the
    # BaTIS download is absent). No separate ADS-proxy leg — paid ADS is
    # already inside the BaTIS leg.
    "destmnedds": "mne_plus_dds_share",
    # The local-sales leg of the headline in isolation.
    "destmne": "mne_share",
    # IP-INCLUSIVE sensitivity: the full Handbook aggregate (SH / charges for
    # IP kept in the DDS leg). The HEADLINE destmnedds excludes SH (largely
    # intra-group royalties, at odds with unrelated-party sales).
    # Plain variant only (not in dest_cols, so no _nexus).
    "destmneddsinclip": "mne_plus_dds_inclip_share",
    # Comparison measures (OECD 2020 constructions):
    "destcfb": "cfb_share",
    "destads": "ads_share",
    # WTO digitally-delivered-services imports only (the "digital" leg in
    # isolation). Normalised within-parent
    # downstream, so the raw import magnitude is a valid destination factor.
    "destdigital": "digital_share",
    # Down-weighted digital blends: cfb_sales + w*digital_imports (w<1), a
    # sensitivity on how much weight the (China-unreliable) WTO digital measure
    # carries. w=0 == destcfb, w=1 == the full CFB+digital combined key.
    "destcfbdig25": "cfbdig25_share",
    "destcfbdig50": "cfbdig50_share",
    "destcfbdig75": "cfbdig75_share",
    # Explicit convex weight on the two normalised shares: 0.75*CFB + 0.25*digital
    # (a *literal* 25% weight on the digital leg — note this is ABOVE digital's
    # ~14% implicit weight in the CFB+digital combined measure).
    "dest7525": "dest7525_share",
}
_SALES_FAMILIES = ["ccctb", "double_weighted_sales", "sales_employees", "three_factors"]

# Optional: restrict destination measures to a comma-separated subset (env
# DEST_SUBSET) to shrink the spec grid for a fast partial run. Empty = all
# measures (default, unchanged). The deliverables consume only destmnedds,
# destcfb, destmne (+ their _nexus), so the rest are optional.
_dest_subset = os.environ.get("DEST_SUBSET", "").strip()
if _dest_subset:
    _keep = {s.strip() for s in _dest_subset.split(",") if s.strip()}
    DEST_MEASURES = {k: v for k, v in DEST_MEASURES.items() if k in _keep}
    print(f"[dest] DEST_SUBSET active -> {sorted(DEST_MEASURES)}")

_dest_formulas = []
for _base in FORMULAS:
    if _base["name"] not in _SALES_FAMILIES:
        continue
    if "unrelated_party_revenues" not in _base.get("formula_vars", []):
        continue
    _sidx = _base["formula_vars"].index("unrelated_party_revenues")
    for _tag, _col in DEST_MEASURES.items():
        for _nexus in (False, True):
            _fv = list(_base["formula_vars"])
            _fv[_sidx] = _col + ("_nexus" if _nexus else "")
            _dest_formulas.append(
                {
                    "name": f"{_base['name']}_{_tag}{'_nexus' if _nexus else ''}",
                    "formula_vars": _fv,
                    "weights": list(_base["weights"]),
                }
            )
FORMULAS = FORMULAS + _dest_formulas


# %% MARK: 4.1 Physical-establishment requirement
# [3.1] The physical-establishment requirement (file tag `_nexus`): a market's
#       destination share is down-weighted by the fraction of the cell's
#       reported MNE groups that actually have an establishment there
#       (Orbis presence), so profit is only assigned where a taxable
#       presence exists. Built here, next to the measures it applies to.

# %%
def _attach_destination_factors(df):
    """Prepare destination-based sales factor columns for the UT formulas.

    The destination share columns (mne_plus_dds_share, cfb_share, ads_share)
    come from 1a_destination_based_sales.py and are merged into the
    dataset in script 2. Here we (a) coerce them and (b) build `*_nexus`
    versions that down-weight the share by the **fraction of a cell's reported
    MNE groups that actually have a subsidiary in the partner** (WIFO throwback
    rule).

    Coverage fraction:

        coverage = min(n_groups / n_cbcr, 1)

      * n_groups  — number of *distinct in-scope (>=EUR 750M consolidated) GUO
        groups* headquartered in iso_parent with >=1 active Orbis subsidiary in
        iso_partner. Built by the CbCR-universe Orbis pass into
        data/intermediate/extractive/cbcr_universe_presence.csv
        (columns hq_iso3, market_iso3, n_groups).
      * n_cbcr    — number of CbCR-reporting MNE groups in this
        (parent, partner, year) cell (propagated from cbcr_main.csv through
        script 2 as pair-year metadata).

    A binary presence switch would be wrong: Orbis presence in a market reflects
    only *some* of the groups aggregated into a CbCR cell, not all of them, so
    the full destination share would be credited (or fully zeroed) on the
    strength of a single group's subsidiary. Scaling by the covered fraction credits a
    cell with the share of its destination sales that the reporting groups
    plausibly route through a real presence in the market.

    Fallbacks (coverage cannot be a true fraction):
      * Home market (iso_parent == iso_partner): coverage = 1.
      * n_cbcr missing (is_distributed==1 imputed rows; no real cell) or <=0:
        fall back to the binary rule — coverage = 1 where n_groups>0 else 0.
      * If the cbcr_universe_presence.csv matrix is absent, fall back to the
        legacy full-universe link matrix (orbis_hq_subsidiary_presence.csv) with
        the binary rule, so runs without the group-count file still work.

    The within-parent normalisation in `_compute_share_economy` turns whichever
    share column is used into a destination distribution over that parent's
    partners, so no rescaling to the parent's CbCR total is needed here.
    """
    # Digital-only (WTO) destination factor = raw digitally-delivered-services
    # imports (within-parent normalisation makes the global scaling irrelevant).
    if "digital_share" not in df.columns and "digital_imports_usd" in df.columns:
        df["digital_share"] = pd.to_numeric(df["digital_imports_usd"], errors="coerce")

    # Down-weighted digital blends (cfb_sales + w*digital_imports) for the
    # digital-weight sensitivity. Raw magnitudes; renormalised within-parent.
    if "cfb_sales" in df.columns and "digital_imports_usd" in df.columns:
        _cfb = pd.to_numeric(df["cfb_sales"], errors="coerce")
        _dig = pd.to_numeric(df["digital_imports_usd"], errors="coerce").fillna(0.0)
        for _w in (25, 50, 75):
            df[f"cfbdig{_w}_share"] = _cfb + (_w / 100.0) * _dig

        # Magnitude blend: keep 75% of the CFB dollars + 25% of the digital
        # dollars, then renormalise. Equivalent to CFB + (1/3)*digital, so digital's
        # effective pool weight drops from ~14% to ~5% (a genuine down-weight of
        # the coarse WTO digital leg). NaN where CFB is undefined (like combined).
        df["dest7525_share"] = 0.75 * _cfb + 0.25 * _dig

    dest_cols = ["cfb_share", "ads_share", "digital_share",
                 # Broadened all-sector MNE measure: market-level keys get
                 # _nexus variants like the others.
                 "mne_share", "mne_plus_dds_share"]
    for c in dest_cols:
        if c not in df.columns:
            df[c] = np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")

    groups_path = os.path.join(
        data_intermediate, "extractive", "cbcr_universe_presence.csv"
    )
    legacy_path = os.path.join(data_intermediate, "orbis_hq_subsidiary_presence.csv")

    if os.path.exists(groups_path):
        pres = pd.read_csv(groups_path).rename(
            columns={"hq_iso3": "iso_parent", "market_iso3": "iso_partner"}
        )
        pres["n_groups"] = pd.to_numeric(pres["n_groups"], errors="coerce")
        merge_cols = ["iso_parent", "iso_partner", "n_groups"]
        # Prefer the presence file's OWN per-HQ group total as the denominator so
        # numerator (n_groups) and denominator come from the SAME universe. The
        # df's existing `n_cbcr` column is a different (smaller) Orbis vintage and
        # would make the coverage ratio n_groups/n_cbcr inconsistent (often >1).
        if "n_cbcr" in pres.columns:
            pres = pres.rename(columns={"n_cbcr": "n_cbcr_grp"})
            pres["n_cbcr_grp"] = pd.to_numeric(pres["n_cbcr_grp"], errors="coerce")
            merge_cols.append("n_cbcr_grp")
        df = df.merge(pres[merge_cols], on=["iso_parent", "iso_partner"], how="left")
        df["n_groups"] = df["n_groups"].fillna(0.0)

        if "n_cbcr_grp" in df.columns:
            # n_cbcr_grp is per-HQ (constant across a parent's markets) but only
            # populated on present cells; broadcast via max so foreign cells with
            # no presence still see the parent's denominator.
            n_cbcr = pd.to_numeric(
                df.groupby("iso_parent")["n_cbcr_grp"].transform("max"),
                errors="coerce",
            )
        elif "n_cbcr" in df.columns:
            n_cbcr = pd.to_numeric(df["n_cbcr"], errors="coerce")
        else:
            n_cbcr = pd.Series(np.nan, index=df.index)
        is_home = df["iso_parent"] == df["iso_partner"]

        # True fraction where we have a real cell group count (n_cbcr > 0);
        # otherwise fall back to the binary presence rule.
        has_denom = n_cbcr > 0
        coverage = np.where(
            has_denom,
            np.minimum(df["n_groups"] / n_cbcr.where(has_denom, np.nan), 1.0),
            (df["n_groups"] > 0).astype(float),  # binary fallback (imputed rows)
        )
        coverage = pd.Series(coverage, index=df.index).fillna(0.0)
        coverage.loc[is_home] = 1.0  # parent always present in its home market
        df["nexus_coverage"] = coverage

        for c in dest_cols:
            df[c + "_nexus"] = df[c] * df["nexus_coverage"]

        frac_fallback = float((~has_denom & ~is_home).mean())
        print(
            f"  Nexus coverage from cbcr_universe_presence.csv: "
            f"mean coverage on foreign cells = "
            f"{df.loc[~is_home, 'nexus_coverage'].mean():.3f}; "
            f"binary fallback used on {frac_fallback:.1%} of rows "
            f"(no n_cbcr denominator)."
        )
    elif os.path.exists(legacy_path):
        # Legacy binary behaviour (full-universe link matrix, no group count).
        pres = pd.read_csv(legacy_path).rename(
            columns={"hq_iso3": "iso_parent", "market_iso3": "iso_partner"}
        )
        pres["orbis_presence"] = 1
        df = df.merge(
            pres[["iso_parent", "iso_partner", "orbis_presence"]],
            on=["iso_parent", "iso_partner"],
            how="left",
        )
        df.loc[df["iso_parent"] == df["iso_partner"], "orbis_presence"] = 1
        df["orbis_presence"] = df["orbis_presence"].fillna(0)
        df["nexus_coverage"] = df["orbis_presence"]
        for c in dest_cols:
            df[c + "_nexus"] = df[c] * df["orbis_presence"]
        print(
            f"  cbcr_universe_presence.csv not found; using legacy binary "
            f"presence matrix: {int(df['orbis_presence'].sum()):,} of "
            f"{len(df):,} rows have a subsidiary."
        )
    else:
        print("  No Orbis presence matrix found; nexus destination formulas "
              "will be skipped (build cbcr_universe_presence.csv).")
    return df


# %% MARK: 5. ETR specifications
# [4] ETR specifications — built from the active ETR_SUFFIX.
# etr_parent_partner_{suffix} is intentionally NOT a UT spec: it is missing
# on distributed (is_distributed=1) rows by design. The column still flows
# through the pipeline as a diagnostic — kept in validate_input_data,
# load_input_samples, and output column ordering — but not as an ETR over
# which UT estimates are computed.
ETR_SPECS_FULL = [
    # HEADLINE: cell-matched rate — domestic ETR on the domestic cell, foreign
    # ETR on foreign-MNE cells, i.e. the rate each cell's profit actually bears
    # rather than the partner-wide average.
    {"name": "domfor",  "etr_col": ETR_COL_DOMFOR},
    {"name": "average", "etr_col": ETR_COL_AVERAGE},
    {"name": "median",  "etr_col": ETR_COL_MEDIAN},
    {"name": "p25",     "etr_col": ETR_COL_P25},
    {"name": "minimum", "etr_col": ETR_COL_MIN},
]
ETR_SPECS_MINIMAL = [
    # HEADLINE cell-matched rate (see ETR_SPECS_FULL) + the average as backup.
    {"name": "domfor",  "etr_col": ETR_COL_DOMFOR},
    {"name": "average", "etr_col": ETR_COL_AVERAGE},
]


# %% MARK: 5.1 ETR fallback substitution
# [4.1] ETR fallback substitution (method, not plumbing): an undefined ETR —
#       negligible or non-positive profit base — is replaced by the partner's
#       mean measured rate, then by the statutory CIT, so no jurisdiction
#       enters the estimation with a spurious rate.

# %%
def ensure_tax_rate_columns(df):
    """Fill missing values on the partner-year UT ETR columns from each
    other (and cit as last resort) so UT can run on every row, and derive the
    cell-matched domestic/foreign rate (`etr_domfor_*`). The pair-ETR column is
    a diagnostic and is NEVER imputed here — distributed rows keep NaN by
    design."""
    out = df.copy()

    out = fill_column_with_fallbacks(
        out,
        ETR_COL_MEDIAN,
        [ETR_COL_P25, ETR_COL_MIN, ETR_COL_AVERAGE, "cit"],
    )
    out = fill_column_with_fallbacks(
        out,
        ETR_COL_P25,
        [ETR_COL_MEDIAN, ETR_COL_MIN, ETR_COL_AVERAGE, "cit"],
    )
    out = fill_column_with_fallbacks(
        out,
        ETR_COL_MIN,
        [ETR_COL_P25, ETR_COL_MEDIAN, ETR_COL_AVERAGE, "cit"],
    )
    out = fill_column_with_fallbacks(
        out,
        ETR_COL_AVERAGE,
        [ETR_COL_MEDIAN, ETR_COL_P25, ETR_COL_MIN, "cit"],
    )

    # Cell-matched rate: the partner's DOMESTIC ETR on its own MNEs' home cell,
    # its FOREIGN ETR on foreign-MNE cells — the rate that cell's profit
    # actually bears. Where the matched rate is unmeasured (non-reporters have
    # no domestic ETR; thin partners no foreign ETR) fall back to the already
    # back-filled average (which ends in CIT), so no row is left without a rate.
    _dom = (pd.to_numeric(out[ETR_COL_DOMESTIC], errors="coerce")
            if ETR_COL_DOMESTIC in out.columns else pd.Series(np.nan, index=out.index))
    _for = (pd.to_numeric(out[ETR_COL_FOREIGN], errors="coerce")
            if ETR_COL_FOREIGN in out.columns else pd.Series(np.nan, index=out.index))
    out[ETR_COL_DOMFOR] = np.where(out["iso_parent"] == out["iso_partner"], _dom, _for)
    out = fill_column_with_fallbacks(out, ETR_COL_DOMFOR, [ETR_COL_AVERAGE, "cit"])

    return out


def ensure_current_tax_source_column(df):
    out = df.copy()

    if TAX_VAR not in out.columns:
        out[TAX_VAR] = np.nan
    else:
        out[TAX_VAR] = pd.to_numeric(out[TAX_VAR], errors="coerce")

    return out


# %% MARK: 6. Tax rates applied to reallocated profit
# [5] Which tax rate turns misaligned profit into revenue effects. Each mode
#     pairs two choices: the rate at which a country that GAINS profit under
#     unitary taxation would tax what returns to it (`loss_rate_kind` — priced
#     on its negative misalignment), and the rate at which a country that
#     LOSES profit (a haven) forgoes revenue (`gain_rate_kind` — priced on its
#     positive misalignment). Headline mode: loss_cit_gain_etr — gainers tax
#     returning profit at max(statutory CIT, own ETR); havens forgo only their
#     observed effective rate.
RATE_MODE_TEMPLATES_FULL = [
    {
        "name": "loss_cit_gain_etr",
        "loss_rate_kind": "cit",
        "gain_rate_kind": "etr",
    },
    {
        "name": "loss_etr_gain_etr",
        "loss_rate_kind": "etr",
        "gain_rate_kind": "etr",
    },
    {
        "name": "loss_cit_gain_cit",
        "loss_rate_kind": "cit",
        "gain_rate_kind": "cit",
    },
]
RATE_MODE_TEMPLATES_MINIMAL = [  # ETR-CIT + ETR-ETR only
    {"name": "loss_cit_gain_etr", "loss_rate_kind": "cit", "gain_rate_kind": "etr"},
    {"name": "loss_etr_gain_etr", "loss_rate_kind": "etr", "gain_rate_kind": "etr"},
    # CIT/CIT (both legs statutory CIT) is only in the FULL set — a comparator
    # for jurisdictions with a degenerate ETR (e.g. South Sudan).
]

# Headline-only sensitivity rate modes: three additional UT-loser/UT-gainer
# rate pairings run ONLY for the MAIN specification (excl_resource dataset,
# reported-only sample, headline formula, "average" ETR spec) so the grid
# doesn't explode:
#   UT LOSERS at the partner MEDIAN pair-ETR,     UT GAINERS at the average ETR
#   UT LOSERS at the partner BOTTOM-10% pair-ETR, UT GAINERS at the average ETR
#   UT LOSERS at the partner BOTTOM-10% pair-ETR, UT GAINERS at the statutory CIT
#
# SLOT SEMANTICS (easy to get backwards): `loss_rate_kind` prices the base of
# countries with NEGATIVE misalignment — those currently LOSING to shifting,
# i.e. the countries that GAIN under UT; `gain_rate_kind` prices POSITIVE
# misalignment — the haven side, i.e. the countries that LOSE under UT. So
# "UT gainers" → loss_rate_kind and "UT losers" → gain_rate_kind. The names
# below use the paper's UT-loser/UT-gainer language directly.
# "median"/"p10" kinds resolve to the partner-level ETR-family columns
# regardless of the etr_spec (see resolve_rate_mode).
HEADLINE_SENSITIVITY_FORMULA = "sales_employees_destmnedds"
RATE_MODE_TEMPLATES_HEADLINE_ONLY = [
    {"name": "losers_median_gainers_avgetr", "loss_rate_kind": "etr", "gain_rate_kind": "median"},
    {"name": "losers_p10_gainers_avgetr",    "loss_rate_kind": "etr", "gain_rate_kind": "p10"},
]
if not (RUN_DATASET == "excl_resource" and REPORTED_ONLY):
    RATE_MODE_TEMPLATES_HEADLINE_ONLY = []

# The p10-CIT "optimistic" pairing (UT losers priced at the bottom-10% pair
# ETR, UT gainers at statutory CIT) runs for EVERY formula and dataset — the
# results explorer offers it as its Optimistic rate option on the full spec
# grid (2026-07-27; it was previously headline-only). Both its rate columns
# are independent of the etr_spec, so it is attached to the "average" spec
# only — one run per formula, no duplication on "domfor".
RATE_MODE_TEMPLATE_OPT_ALL = {
    "name": "losers_p10_gainers_cit", "loss_rate_kind": "cit", "gain_rate_kind": "p10",
}


# Toggle: trim ETR × rate-mode combinations to only what the
# scenario report (7d) actually consumes. Switching to MINIMAL
# reduces the spec count per formula from 12 → 2 (6× faster UT runs).
# Set MINIMAL = False if you need the full set (e.g., for the
# winners-losers / loss-sensitivity tables that span more specs).
MINIMAL = True
ETR_SPECS = ETR_SPECS_MINIMAL if MINIMAL else ETR_SPECS_FULL
RATE_MODE_TEMPLATES = RATE_MODE_TEMPLATES_MINIMAL if MINIMAL else RATE_MODE_TEMPLATES_FULL


# %% MARK: 7. Input samples
# [6] Input samples — single sample per run, driven by RUN_DATASET.
INPUT_SAMPLES = {
    RUN_DATASET: Path(data_final) / _cfg["input_file"],
}


# %% MARK: 8. Technical helpers
# [7] Technical helpers — naming, formatting, validation and I/O only; the
#     functions with methodological content live in their concept sections
#     above ([3.1] physical-establishment requirement, [4.1] ETR fallbacks).
def check_duplicates(df, name):
    if df.duplicated().any():
        print(f"Warning: {name} contains duplicate rows.")
    else:
        print(f"No duplicates found in {name}.")


def make_file_stub(formula_name, etr_name, rate_mode_name):
    # "etrmax_inf" is a fixed naming component (full reapportionment — see the
    # ETR_THRESHOLD note above).
    return (
        f"{formula_name}"
        f"__etrdef_{etr_name}"
        f"__etrmax_inf"
        f"__{rate_mode_name}"
    )


def ensure_output_dir(sample_name):
    output_dir = OUTPUT_ROOT / sample_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _longpath(p):
    """On Windows, prefix paths > 240 chars with the \\\\?\\ long-path namespace
    so open() bypasses the legacy 260-char MAX_PATH limit. The OneDrive +
    Arabic-character project root pushes some country_estimates filenames
    over the limit. A no-op on non-Windows."""
    s = os.fspath(p)
    if sys.platform == "win32" and len(s) > 240 and not s.startswith("\\\\?\\"):
        s = "\\\\?\\" + os.path.abspath(s)
    return s


def _rate_col_for_kind(kind, etr_spec):
    """Map a rate 'kind' to the column that carries the rate.

    "etr" follows the active etr_spec; "cit" is the statutory rate;
    "median"/"p10" pin the partner-level pair-ETR statistics irrespective of
    the etr_spec (used by the headline-only sensitivity modes)."""
    if kind == "etr":
        return etr_spec["etr_col"]
    if kind == "cit":
        return "cit"
    if kind == "median":
        return ETR_COL_MEDIAN
    if kind == "p10":
        return ETR_COL_P10
    raise ValueError(f"Unknown rate kind: {kind!r}")


def resolve_rate_mode(rate_mode_template, etr_spec):
    loss_rate_col = _rate_col_for_kind(rate_mode_template["loss_rate_kind"], etr_spec)
    gain_rate_col = _rate_col_for_kind(rate_mode_template["gain_rate_kind"], etr_spec)

    return {
        "name": rate_mode_template["name"],
        "loss_rate_col": loss_rate_col,
        "gain_rate_col": gain_rate_col,
        "loss_rate_kind": rate_mode_template["loss_rate_kind"],
        "gain_rate_kind": rate_mode_template["gain_rate_kind"],
    }


def classify_income_group(value):
    if pd.isna(value):
        return "other_or_missing"

    s = str(value).strip().lower()
    s = s.replace(" ", "_").replace("-", "_")

    if s == "low_income":
        return "low_income"

    if s in {"lower_middle_income", "upper_middle_income", "middle_income"}:
        return "middle_income"

    if s == "high_income":
        return "high_income"

    return "other_or_missing"


AGGREGATE_INCOME_GROUPS = [
    "global",
    "low_income",
    "middle_income",
    "high_income",
    "other_or_missing",
]


INCOME_LABELS = {
    "global": "Global",
    "low_income": "Low income",
    "middle_income": "Middle income",
    "high_income": "High income",
    "other_or_missing": "Other / missing",
}


def safe_series_sum(series):
    return series.sum(min_count=1)


def make_aggregate_row(
    df,
    year,
    formula_name,
    etr_name,
    etr_col,
    etr_threshold,
    threshold_rate_col,
    rate_mode_name,
    loss_rate_col,
    gain_rate_col,
    sample_name,
    income_group_bucket,
):
    if df.empty:
        n_countries = 0
        total_shifted_musd = 0
        total_tax_loss_musd = 0
        total_tax_gain_musd = 0
        total_revenue_gain_from_ut_musd = 0
        mean_revenue_gain_from_ut_musd = np.nan
        total_current_tax_paid_cash_musd = np.nan
        revenue_gain_from_ut_pct_of_current_tax_paid = np.nan
        tax_revenue_loss_pct_of_current_tax_paid = np.nan
        tax_revenue_gain_pct_of_current_tax_paid = np.nan
    else:
        n_countries = df["iso_partner"].nunique()
        total_shifted_musd = df["positive_misalignment"].sum()
        total_tax_loss_musd = df["tax_revenue_loss"].sum()
        total_tax_gain_musd = df["tax_revenue_gain"].sum()
        total_revenue_gain_from_ut_musd = df["revenue_gain_from_ut"].sum()
        mean_revenue_gain_from_ut_musd = df["revenue_gain_from_ut"].mean()
        total_current_tax_paid_cash_musd = safe_series_sum(
            df["current_tax_paid_cash_musd"]
        )

        if (
            pd.notna(total_current_tax_paid_cash_musd)
            and total_current_tax_paid_cash_musd > 0
        ):
            revenue_gain_from_ut_pct_of_current_tax_paid = (
                100 * total_revenue_gain_from_ut_musd / total_current_tax_paid_cash_musd
            )
            tax_revenue_loss_pct_of_current_tax_paid = (
                100 * total_tax_loss_musd / total_current_tax_paid_cash_musd
            )
            tax_revenue_gain_pct_of_current_tax_paid = (
                100 * total_tax_gain_musd / total_current_tax_paid_cash_musd
            )
        else:
            revenue_gain_from_ut_pct_of_current_tax_paid = np.nan
            tax_revenue_loss_pct_of_current_tax_paid = np.nan
            tax_revenue_gain_pct_of_current_tax_paid = np.nan

    return {
        "sample_name": sample_name,
        "formula_name": formula_name,
        "etr_name": etr_name,
        "etr_col": etr_col,
        "etr_threshold": etr_threshold,
        "threshold_rate_col": threshold_rate_col,
        "rate_mode": rate_mode_name,
        "loss_rate_col": loss_rate_col,
        "gain_rate_col": gain_rate_col,
        "year": year,
        "income_group_bucket": income_group_bucket,
        "n_countries": n_countries,
        "total_shifted_musd": total_shifted_musd,
        "total_tax_loss_musd": total_tax_loss_musd,
        "total_tax_gain_musd": total_tax_gain_musd,
        "total_revenue_gain_from_ut_musd": total_revenue_gain_from_ut_musd,
        "mean_revenue_gain_from_ut_musd": mean_revenue_gain_from_ut_musd,
        "total_current_tax_paid_cash_musd": total_current_tax_paid_cash_musd,
        "revenue_gain_from_ut_pct_of_current_tax_paid": revenue_gain_from_ut_pct_of_current_tax_paid,
        "tax_revenue_loss_pct_of_current_tax_paid": tax_revenue_loss_pct_of_current_tax_paid,
        "tax_revenue_gain_pct_of_current_tax_paid": tax_revenue_gain_pct_of_current_tax_paid,
    }


def build_aggregate_rows(
    country_results,
    year,
    formula_name,
    etr_name,
    etr_col,
    etr_threshold,
    threshold_rate_col,
    rate_mode_name,
    loss_rate_col,
    gain_rate_col,
    sample_name,
):
    df = country_results.copy()
    df["income_group_bucket"] = df["wb_income_group"].apply(classify_income_group)

    rows = []

    rows.append(
        make_aggregate_row(
            df=df,
            year=year,
            formula_name=formula_name,
            etr_name=etr_name,
            etr_col=etr_col,
            etr_threshold=etr_threshold,
            threshold_rate_col=threshold_rate_col,
            rate_mode_name=rate_mode_name,
            loss_rate_col=loss_rate_col,
            gain_rate_col=gain_rate_col,
            sample_name=sample_name,
            income_group_bucket="global",
        )
    )

    for bucket in AGGREGATE_INCOME_GROUPS:
        if bucket == "global":
            continue

        subset = df.loc[df["income_group_bucket"] == bucket].copy()

        rows.append(
            make_aggregate_row(
                df=subset,
                year=year,
                formula_name=formula_name,
                etr_name=etr_name,
                etr_col=etr_col,
                etr_threshold=etr_threshold,
                threshold_rate_col=threshold_rate_col,
                rate_mode_name=rate_mode_name,
                loss_rate_col=loss_rate_col,
                gain_rate_col=gain_rate_col,
                sample_name=sample_name,
                income_group_bucket=bucket,
            )
        )

    return pd.DataFrame(rows)


# %% MARK: 8.1 Validation helpers
def validate_formula_spec(formula_spec):
    if "name" not in formula_spec:
        raise ValueError("Each formula specification must have a 'name'.")
    if "formula_vars" not in formula_spec or "weights" not in formula_spec:
        raise ValueError(
            f"Formula '{formula_spec.get('name', 'UNKNOWN')}' must define "
            "'formula_vars' and 'weights'."
        )
    if len(formula_spec["formula_vars"]) != len(formula_spec["weights"]):
        raise ValueError(
            f"Formula '{formula_spec['name']}' has different lengths for "
            "'formula_vars' and 'weights'."
        )
    if sum(formula_spec["weights"]) <= 0:
        raise ValueError(
            f"Formula '{formula_spec['name']}' must have at least one positive weight."
        )


def validate_etr_spec(etr_spec):
    if "name" not in etr_spec or "etr_col" not in etr_spec:
        raise ValueError("Each ETR specification must define 'name' and 'etr_col'.")


def validate_input_data(cbcr_data, sample_name):
    required_cols = [
        "year",
        "iso_parent",
        "iso_partner",
        "partner_jurisdiction",
        PROFIT_VAR,
        ETR_COL_AVERAGE,
        ETR_COL_MEDIAN,
        ETR_COL_P25,
        ETR_COL_MIN,
        ETR_COL_PAIR,
        "cit",
        "n_employees",
        "unrelated_party_revenues",
        "tangible_assets_except_cash",
        "payroll",
        "region_tjn",
        "wb_income_group",
        "ukt",
        "oecd",
        "oecd_oct",
        "eu27",
        "wage_monthly",
    ]

    missing_cols = [col for col in required_cols if col not in cbcr_data.columns]
    if missing_cols:
        raise ValueError(
            f"Missing required columns in sample '{sample_name}': {missing_cols}"
        )


# %% MARK: 8.2 Sample preparation helpers
def keep_actual_country_rows(df):
    out = df.copy()

    out = out.loc[out["iso_partner"].notna()].copy()
    out = out.loc[~out["iso_partner"].isin(non_countries)].copy()

    if "year" in out.columns:
        out["year"] = pd.to_numeric(out["year"], errors="coerce")

    return out


def coerce_numeric_columns(df, columns):
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def fill_column_with_fallbacks(df, target_col, fallback_cols):
    out = df.copy()

    if target_col not in out.columns:
        return out

    for fallback_col in fallback_cols:
        if fallback_col not in out.columns:
            continue
        missing = out[target_col].isna()
        out.loc[missing, target_col] = out.loc[missing, fallback_col]

    return out


def ensure_reported_profit_var(df):
    """Floored datasets: the excl_resource "IS" leg
    (PROFIT_VAR) is not stored in the floored file — reconstruct it from the
    floored pool + the royalty add-on (floored = excl_resource − add-on).
    No-op on every other dataset and when the column already exists."""
    if POOL_VAR is not None and PROFIT_VAR not in df.columns:
        _pool = pd.to_numeric(df[POOL_VAR], errors="coerce")
        _add = pd.to_numeric(df.get(ADDON_VAR, 0.0), errors="coerce")
        _add = _add.fillna(0.0) if hasattr(_add, "fillna") else 0.0
        df[PROFIT_VAR] = _pool + _add
        print(f"  [pool/reported split] {PROFIT_VAR} reconstructed as "
              f"{POOL_VAR} + {ADDON_VAR} (true-baseline comparison).")
    return df


def load_input_samples():
    numeric_cols = [
        "year",
        PROFIT_VAR,
        ETR_COL_AVERAGE,
        ETR_COL_MEDIAN,
        ETR_COL_P25,
        ETR_COL_MIN,
        ETR_COL_PAIR,
        "cit",
        "n_employees",
        "unrelated_party_revenues",
        "tangible_assets_except_cash",
        "payroll",
        "cfb_share",
        "ads_share",
        "wage_monthly",
        TAX_VAR,
    ]

    samples = {}

    for sample_name, file_path in INPUT_SAMPLES.items():
        df = pd.read_csv(file_path)
        df = keep_actual_country_rows(df)
        if REPORTED_ONLY:
            n_before = len(df)
            # Partial-reporter rule: measure each parent-year's aggregate share
            # of foreign unrelated-party revenues on the FULL frame (the
            # distributed rows carry the aggregate-origin activity), then drop
            # flagged parent-years entirely from the reported sample.
            _f = df[df["iso_partner"] != df["iso_parent"]]
            _upr = pd.to_numeric(_f["unrelated_party_revenues"], errors="coerce").fillna(0.0)
            _agg = _upr.where(_f["is_distributed"] == 1, 0.0)
            _tot = _upr.groupby([_f["iso_parent"], _f["year"]]).sum()
            _sh = _agg.groupby([_f["iso_parent"], _f["year"]]).sum() / _tot.where(_tot > 0)
            _flagged = set(_sh[_sh > PARTIAL_REPORTER_MAX_AGG_SHARE].index)
            if _flagged:
                _key = pd.MultiIndex.from_arrays([df["iso_parent"], df["year"]])
                df = df[~_key.isin(_flagged)].copy()
                _n_partial = len({p for p, _ in _flagged})
                print(f"  partial-reporter rule (> {PARTIAL_REPORTER_MAX_AGG_SHARE:.0%} of foreign "
                      f"unrelated-party revenues in aggregates): dropped "
                      f"{len(_flagged)} parent-years across {_n_partial} parents.")
            df = df[df["is_distributed"] == 0].copy()
            n_after_dist = len(df)
            # Drop "bad reporters": parents whose only remaining row is the
            # domestic row (iso_partner == iso_parent) — they have no
            # cross-border country-level data left after the keep_actual_country_rows
            # and is_distributed==0 filters. Mathematically they contribute 0 to
            # the misalignment signal (the formula factors collapse to 100% in
            # the parent's own country, so theoretical == reported); explicitly
            # dropping them shrinks the parent universe to the actual reporting
            # population.
            cross_border_parents = (
                df.loc[df["iso_partner"] != df["iso_parent"], "iso_parent"].unique()
            )
            n_parents_before = df["iso_parent"].nunique()
            df = df[df["iso_parent"].isin(cross_border_parents)].copy()
            n_parents_after = df["iso_parent"].nunique()
            print(f"  REPORTED_ONLY filter: kept {n_after_dist:,} of {n_before:,} rows "
                  f"after is_distributed==0; then dropped {n_parents_before - n_parents_after} "
                  f"bad-reporter parents (no cross-border country data after filter), "
                  f"leaving {len(df):,} rows for {n_parents_after} parents.")
        df = ensure_reported_profit_var(df)
        df = coerce_numeric_columns(df, numeric_cols)
        df = ensure_tax_rate_columns(df)
        df = ensure_current_tax_source_column(df)
        validate_input_data(df, sample_name)

        print(f"\nLoaded sample: {sample_name}{' (reported-only)' if REPORTED_ONLY else ''}")
        print(f"  Rows: {len(df):,}")
        print(f"  Years: {sorted(df['year'].dropna().astype(int).unique())}")

        for etr_spec in ETR_SPECS:
            n_missing = df[etr_spec["etr_col"]].isna().sum()
            print(f"  Missing {etr_spec['etr_col']}: {n_missing:,}")

        n_missing_cit = df["cit"].isna().sum()
        print(f"  Missing cit: {n_missing_cit:,}")

        if TAX_VAR in df.columns:
            n_missing_tax_paid = df[TAX_VAR].isna().sum()
            print(f"  Missing {TAX_VAR}: {n_missing_tax_paid:,}")

        df = _attach_destination_factors(df)

        samples[sample_name] = df

    return samples


# %% MARK: 8.3 Column ordering helpers
def order_columns(df, preferred_cols):
    if df.empty:
        return df.copy()

    preferred_existing = [c for c in preferred_cols if c in df.columns]
    remaining = sorted([c for c in df.columns if c not in preferred_existing])
    return df[preferred_existing + remaining].copy()


def order_country_columns(df):
    preferred = [
        "iso_partner",
        "partner_jurisdiction",
        "year",
        "sample_name",
        "formula_name",
        "etr_name",
        "etr_col",
        "etr_threshold",
        "threshold_rate_col",
        "rate_mode",
        "loss_rate_col",
        "gain_rate_col",
        "wb_income_group",
        "region_tjn",
        "ukt",
        "oecd",
        "oecd_oct",
        "eu27",
        "cit",
        ETR_COL_AVERAGE,
        ETR_COL_MEDIAN,
        ETR_COL_P25,
        ETR_COL_MIN,
        ETR_COL_PAIR,
        "current_tax_paid_cash_usd_raw",
        "current_tax_paid_cash_musd",
        "negative_misalignment",
        "positive_misalignment",
        "theoretical_profit",
        "reported_profit",
        "tax_revenue_loss",
        "tax_revenue_gain",
        "revenue_gain_from_ut",
        "tax_revenue_loss_caused_musd",
        "tax_revenue_loss_caused_pct_of_total",
        "tax_revenue_loss_suffered_pct_of_total",
        "revenue_gain_from_ut_pct_of_current_tax_paid",
        "tax_revenue_loss_pct_of_current_tax_paid",
        "tax_revenue_gain_pct_of_current_tax_paid",
        "wage_monthly",
    ]
    return order_columns(df, preferred)


def order_aggregate_columns(df):
    preferred = [
        "year",
        "sample_name",
        "formula_name",
        "etr_name",
        "etr_col",
        "etr_threshold",
        "threshold_rate_col",
        "rate_mode",
        "loss_rate_col",
        "gain_rate_col",
        "income_group_bucket",
        "n_countries",
        "total_shifted_musd",
        "total_tax_loss_musd",
        "total_tax_gain_musd",
        "total_revenue_gain_from_ut_musd",
        "mean_revenue_gain_from_ut_musd",
        "total_current_tax_paid_cash_musd",
        "revenue_gain_from_ut_pct_of_current_tax_paid",
        "tax_revenue_loss_pct_of_current_tax_paid",
        "tax_revenue_gain_pct_of_current_tax_paid",
    ]
    return order_columns(df, preferred)


def order_misalignment_columns(df):
    preferred = [
        "iso_parent",
        "iso_partner",
        "partner_jurisdiction",
        "year",
        "sample_name",
        "formula_name",
        "etr_name",
        "etr_col",
        "etr_threshold",
        "threshold_rate_col",
        "rate_mode",
        "loss_rate_col",
        "gain_rate_col",
        PROFIT_VAR,
        "theoretical_profit",
        "misaligned_profit",
        "positive_misalignment_musd_row",
        "negative_misalignment_musd_row",
        "tax_revenue_loss_suffered_musd_row",
        "tax_revenue_loss_caused_musd_row",
        "cit",
        ETR_COL_AVERAGE,
        ETR_COL_MEDIAN,
        ETR_COL_P25,
        ETR_COL_MIN,
        ETR_COL_PAIR,
        TAX_VAR,
        "n_employees",
        "unrelated_party_revenues",
        "tangible_assets_except_cash",
        "payroll",
        "economic_activity_partner_of_parent",
        "share_economy_partner_of_parent",
        "wb_income_group",
        "region_tjn",
        "ukt",
        "oecd",
        "oecd_oct",
        "eu27",
    ]
    return order_columns(df, preferred)


def order_run_summary_columns(df):
    preferred = [
        "sample_name",
        "formula_name",
        "etr_name",
        "etr_col",
        "etr_threshold",
        "threshold_rate_col",
        "rate_mode",
        "loss_rate_col",
        "gain_rate_col",
        "n_country_rows",
        "n_misalignment_rows",
        "n_years",
        "total_shifted_musd_all_years",
        "total_tax_loss_musd_all_years",
        "total_tax_gain_musd_all_years",
        "total_revenue_gain_from_ut_musd_all_years",
        "total_current_tax_paid_cash_musd_all_years",
        "revenue_gain_from_ut_pct_of_current_tax_paid_all_years",
        "total_revenue_gain_from_ut_low_income_musd_all_years",
        "total_revenue_gain_from_ut_middle_income_musd_all_years",
        "country_file",
        "misalignment_file",
        "aggregate_file",
        "n_bilateral_rows",
        "bilateral_file",
    ]
    return order_columns(df, preferred)


# %% MARK: 9. Core estimation functions
def _compute_share_economy(df, formula_vars, weights, share_prefix=""):
    """Compute share_economy_partner_of_parent for one formula spec.

    Returns the (share_col_name, df-with-new-column) pair. Mutates df.
    """
    active_specs = []
    for var, weight in zip(formula_vars, weights):
        if var is None or weight <= 0:
            continue
        if var not in df.columns:
            raise ValueError(f"Formula variable '{var}' not found in input data.")

        df[var] = pd.to_numeric(df[var], errors="coerce")
        df.loc[df[var] < 0, var] = 0

        total_by_parent = df.groupby("iso_parent")[var].transform("sum")
        share_col = f"share_{share_prefix}{var}"
        df[share_col] = np.where(total_by_parent > 0, df[var] / total_by_parent, 0)
        active_specs.append((share_col, weight))

    if not active_specs:
        raise ValueError("No active variables with positive weights found.")

    activity_col = f"economic_activity_{share_prefix}partner_of_parent"
    df[activity_col] = 0.0
    for share_col, weight in active_specs:
        df[activity_col] += df[share_col] * weight

    total_activity = df.groupby("iso_parent")[activity_col].transform("sum")
    out_col = f"share_economy_{share_prefix}partner_of_parent"
    df[out_col] = np.where(total_activity > 0, df[activity_col] / total_activity, 0)
    return out_col, df


# Reported-direction sign guard: the imputed (distributed) rows may amplify but
# must not REVERSE — or, where nothing is reported, manufacture — the profit-
# shifting direction implied by the directly-reported rows alone. A partner whose
# reported-only net misalignment is below REPORTED_SIGN_EPS_USD in magnitude (or
# who has no reported rows at all) counts as having "no reported anchor". Env-
# overridable; set REPORTED_SIGN_GUARD=0 to disable.
REPORTED_SIGN_GUARD = (
    os.environ.get("REPORTED_SIGN_GUARD", "1").strip().lower() not in ("0", "false", "")
)
REPORTED_SIGN_EPS_USD = float(os.environ.get("REPORTED_SIGN_EPS_USD", "5e6"))

# Sign-guard anchor mode (env SIGN_GUARD_MODE):
#   "per_year"  — each year's full-sample misalignment is clipped to THAT year's
#                 reported-only direction. The disaggregated estimate cannot reverse
#                 the reported direction within any given year. (Default; good for
#                 projects that want year-by-year fidelity.)
#   "aggregate" — every year is clipped to the partner's POOLED (all-years)
#                 reported-only direction, so the country's MULTI-YEAR net direction
#                 in the disaggregated sample matches the directly-reported cells.
#                 (Used for this project's pooled-period country results.)
# The anchor is always the directly-reported cells (is_distributed==0) of the SAME
# sample, not a separate reported-only run.
SIGN_GUARD_MODE = os.environ.get("SIGN_GUARD_MODE", "per_year").strip().lower()


def calculate_misalignment(
    cbcr_data,
    formula_vars,
    weights,
    profit_var=None,
    pool_var=None,
    loss_rate_col=None,
    reported_sign_guard=True,
    reported_sign_override=None,
):
    """Compute misalignment of reported profit vs formulary-apportioned profit.

    All of each parent's profit is allocated by `(formula_vars, weights)`.
    """
    # Defaults pulled from the active dataset config when callers omit them.
    # `pool_var`: the profit pool APPORTIONED by the
    # formula, when it differs from the reported "IS" leg (`profit_var`). Set
    # for the floored datasets — the royalty gap is deductible, so the
    # counterfactual pool is smaller than the profit countries book today. The
    # per-parent imbalance Σ misaligned = Σ add-on is INTENTIONAL there (the
    # royalty leaves the corporate base; it returns as the separate royalty
    # revenue stream). Only defaulted from the dataset config when profit_var
    # is also defaulted — a caller passing its own profit_var gets pool == it.
    if profit_var is None:
        profit_var = PROFIT_VAR
        if pool_var is None:
            pool_var = POOL_VAR
    df = cbcr_data.copy()

    # The minimum-rate haven test uses the average ETR that fits the active
    # sample — the dataset's own etr_col, taken as-passed. An undefined ETR (a
    # negligibly-small or non-positive profit base) is replaced upstream by the
    # partner-mean measured rate and then the statutory CIT, so it never arrives
    # here as NaN.

    if profit_var not in df.columns:
        raise ValueError(f"Profit variable '{profit_var}' not found in input data.")

    if loss_rate_col is not None and loss_rate_col not in df.columns:
        raise ValueError(f"Loss rate column '{loss_rate_col}' not found in input data.")

    # Reported-direction reference for the sign guard. Compute this spec's
    # misalignment on the directly-reported rows alone (is_distributed == 0) and
    # take each partner's net sign; below, any full-sample misalignment that
    # conflicts with it is removed. Only meaningful on a full (imputed) input
    # under a finite minimum-rate threshold; recursion is one level deep
    # (reported_sign_guard=False on the inner call).
    reported_sign = None
    if reported_sign_override is not None:
        # Aggregate mode: caller supplies the pooled (all-years) reported direction.
        reported_sign = reported_sign_override
    elif (
        reported_sign_guard
        and REPORTED_SIGN_GUARD
        and "is_distributed" in df.columns
        and (df["is_distributed"] == 1).any()
        and (df["is_distributed"] == 0).any()
    ):
        _rep = calculate_misalignment(
            df[df["is_distributed"] == 0],
            formula_vars,
            weights,
            profit_var=profit_var,
            pool_var=pool_var,
            loss_rate_col=loss_rate_col,
            reported_sign_guard=False,
        )
        _rep_net = _rep.groupby("iso_partner")["misaligned_profit"].sum()
        # |net| below the epsilon (or a partner absent from the reported rows)
        # counts as "no reported anchor" -> sign 0 -> the estimate is clipped to 0.
        reported_sign = np.sign(
            _rep_net.where(_rep_net.abs() >= REPORTED_SIGN_EPS_USD, 0.0)
        )

    primary_col, df = _compute_share_economy(df, formula_vars, weights, share_prefix="")
    df["share_economy_partner_of_parent"] = df[primary_col]

    _pool_col = pool_var if pool_var is not None else profit_var
    if _pool_col not in df.columns:
        raise ValueError(f"Pool variable '{_pool_col}' not found in input data.")
    total_profit_by_parent = df.groupby("iso_parent")[_pool_col].transform("sum")
    # Floor parent worldwide profit pool at 0 for UT apportionment. When a
    # parent's worldwide pool is non-positive, skip apportionment for that
    # parent — partners retain their reported values (theoretical = reported,
    # misalignment = 0). Prevents UT from redistributing a negative aggregate
    # pro-rata across all partners (which otherwise drags non-resource partners
    # more negative; see the Somalia case under excl_resource).
    parent_positive = total_profit_by_parent > 0
    df["theoretical_profit"] = np.where(
        parent_positive,
        df["share_economy_partner_of_parent"] * total_profit_by_parent,
        df[profit_var],
    )
    # Misalignment = reported "IS" leg minus the UT allocation of the pool.
    # With pool_var set this nets to +Σ add-on per parent instead of zero — by
    # design (see the pool_var note above).
    df["misaligned_profit"] = df[profit_var] - df["theoretical_profit"]

    # Reported-direction sign guard — applied in BOTH regimes. It
    # removes any full-sample misalignment whose sign would conflict with the
    # partner's reported-only direction:
    #   reported net < 0 -> drop positive misalignment (cannot become a winner)
    #   reported net > 0 -> drop negative misalignment (cannot become a loser)
    #   reported net ~ 0 -> drop both (no reported anchor; don't manufacture one)
    # The clip breaks the within-parent identity neg - pos == theoretical -
    # reported; conservation is restored in adjust_misalignment: the finite
    # regime rescales the negative side; the inf (pure-reapportionment) regime
    # rescales the IMPUTED rows' misalignment so the reported-row allocations
    # stay fixed.
    if reported_sign is not None:
        _rs = df["iso_partner"].map(reported_sign)
        _rs = _rs.where(_rs.notna(), 0.0)
        _conflict = (
            ((df["misaligned_profit"] > 0) & (_rs <= 0))
            | ((df["misaligned_profit"] < 0) & (_rs >= 0))
        )
        df.loc[_conflict, "misaligned_profit"] = 0

    def adjust_misalignment(group):
        total_neg = group.loc[group["misaligned_profit"] < 0, "misaligned_profit"].sum()
        total_pos = group.loc[group["misaligned_profit"] > 0, "misaligned_profit"].sum()

        # Restore within-parent conservation (Σ misaligned == 0) after the sign
        # guard may have zeroed some rows (full-reapportionment regime).
        if (reported_sign is not None and "is_distributed" in group.columns
                and pool_var is None):
            # (pool_var runs skip this restore: their per-parent imbalance is
            # the royalty gap leaving the corporate base — intentional, not a
            # clipping artifact to be absorbed by imputed rows.)
            # inf (pure-reapportionment) regime WITH the sign guard active: the clip
            # left Σ misaligned ≠ 0. Absorb the imbalance on the IMPUTED
            # (is_distributed==1) rows only — scale their net misalignment to
            # -reported_net so the parent nets to zero again while the reported-row
            # allocations stay exactly as computed. The single factor preserves
            # imputed-row signs (so the guard is respected) and reduces to 1.0 when
            # nothing was clipped. Falls back to a global negative rescale when there
            # is no usable imputed buffer (factor non-positive, exploding, or imp_net≈0).
            imp_mask = group["is_distributed"] == 1
            rep_net = group.loc[~imp_mask, "misaligned_profit"].sum()
            imp_net = group.loc[imp_mask, "misaligned_profit"].sum()
            f = (-rep_net / imp_net) if abs(imp_net) > 1.0 else np.nan
            if pd.notna(f) and 0.0 < f <= 10.0:
                group.loc[imp_mask, "misaligned_profit"] *= f
            elif total_neg != 0:
                group.loc[group["misaligned_profit"] < 0, "misaligned_profit"] *= (
                    -total_pos / total_neg
                )

        if loss_rate_col is not None:
            group["positive_misalignment_musd_row"] = np.where(
                group["misaligned_profit"] > 0,
                group["misaligned_profit"] / 1e6,
                0.0,
            )
            group["negative_misalignment_musd_row"] = np.where(
                group["misaligned_profit"] < 0,
                -group["misaligned_profit"] / 1e6,
                0.0,
            )
            group["tax_revenue_loss_suffered_musd_row"] = (
                group["negative_misalignment_musd_row"] * group[loss_rate_col]
            )

            total_positive_musd = group["positive_misalignment_musd_row"].sum()
            total_tax_loss_suffered_musd = group[
                "tax_revenue_loss_suffered_musd_row"
            ].sum()

            group["tax_revenue_loss_caused_musd_row"] = np.where(
                total_positive_musd > 0,
                (
                    group["positive_misalignment_musd_row"]
                    / total_positive_musd
                    * total_tax_loss_suffered_musd
                ),
                0.0,
            )

        return group

    adjusted_parts = []
    for _, group in df.groupby("iso_parent", sort=False):
        adjusted_parts.append(adjust_misalignment(group.copy()))

    df = pd.concat(adjusted_parts, ignore_index=True)
    return df


def aggregate_country_results(
    misalignment_df,
    year,
    loss_rate_col,
    gain_rate_col,
    formula_name,
    etr_name,
    etr_col,
    etr_threshold,
    threshold_rate_col,
    rate_mode_name,
    sample_name,
):
    metadata_cols = [
        "partner_jurisdiction",
        "cit",
        ETR_COL_AVERAGE,
        ETR_COL_MEDIAN,
        ETR_COL_P25,
        ETR_COL_MIN,
        ETR_COL_PAIR,
        "region_tjn",
        "wb_income_group",
        "ukt",
        "oecd",
        "oecd_oct",
        "eu27",
        "wage_monthly",
    ]

    unique_partners = misalignment_df.groupby("iso_partner", as_index=False)[
        metadata_cols
    ].first()

    # Revenue legs are valued at ROW level so that CELL-level rate columns
    # (etr_domfor_*: domestic rate on the domestic cell, foreign rate on
    # foreign-MNE cells) price each cell's misalignment at the rate that cell's
    # profit actually bears. For the partner-constant rate columns (average /
    # median / p25 / min / cit) this is numerically identical to computing at
    # partner level. The ETR-CIT max(CIT, gain-rate) loss-side
    # guard (see the note below) is applied row-level for the same reason.
    _loss_rate_row = pd.to_numeric(misalignment_df[loss_rate_col], errors="coerce")
    _gain_rate_row = pd.to_numeric(misalignment_df[gain_rate_col], errors="coerce")
    if loss_rate_col == "cit" and gain_rate_col != "cit":
        _loss_rate_row = np.maximum(_loss_rate_row, _gain_rate_row)
    _mis = misalignment_df["misaligned_profit"]
    misalignment_df = misalignment_df.assign(
        _tax_revenue_loss_row=np.where(_mis < 0, -_mis / 1e6, 0.0) * _loss_rate_row,
        _tax_revenue_gain_row=np.where(_mis > 0, _mis / 1e6, 0.0) * _gain_rate_row,
    )

    country_results = misalignment_df.groupby("iso_partner", as_index=False).agg(
        negative_misalignment=("misaligned_profit", lambda x: x[x < 0].sum()),
        positive_misalignment=("misaligned_profit", lambda x: x[x > 0].sum()),
        theoretical_profit=("theoretical_profit", "sum"),
        reported_profit=(PROFIT_VAR, "sum"),
        tax_revenue_loss_caused_musd=("tax_revenue_loss_caused_musd_row", "sum"),
        tax_revenue_loss=("_tax_revenue_loss_row", "sum"),
        tax_revenue_gain=("_tax_revenue_gain_row", "sum"),
    )

    current_tax_paid = misalignment_df.groupby("iso_partner", as_index=False).agg(
        current_tax_paid_cash_usd_raw=(
            TAX_VAR,
            lambda x: x.sum(min_count=1),
        )
    )

    country_results["negative_misalignment"] = (
        -country_results["negative_misalignment"] / 1e6
    )
    country_results["positive_misalignment"] = (
        country_results["positive_misalignment"] / 1e6
    )
    country_results["theoretical_profit"] = country_results["theoretical_profit"] / 1e6
    country_results["reported_profit"] = country_results["reported_profit"] / 1e6

    country_results = country_results.merge(
        unique_partners, on="iso_partner", how="left"
    )
    country_results = country_results.merge(
        current_tax_paid, on="iso_partner", how="left"
    )

    # ETR-CIT spec (loss=cit, gain=etr): when the gain-side ETR exceeds the
    # loss-side CIT, value the recovered ("won") base at the ETR too — i.e. fall
    # back to ETR-ETR there. The CIT-on-recovered / ETR-on-surrendered asymmetry
    # is only meant to favour sufferers when ETR < CIT (a haven's surrendered
    # profit was lightly taxed); when ETR > CIT it would perversely value
    # surrendered profit ABOVE recovered profit. max(CIT, ETR) on the loss side
    # guarantees a country that gains taxable profit also gains tax revenue.
    # Only the ETR-CIT mode is touched. (Applied ROW-level in the block above,
    # where tax_revenue_loss / tax_revenue_gain are computed.)
    total_loss = country_results["tax_revenue_loss"].sum()

    country_results["revenue_gain_from_ut"] = (
        country_results["tax_revenue_loss"] - country_results["tax_revenue_gain"]
    )

    country_results["tax_revenue_loss_caused_pct_of_total"] = np.where(
        total_loss > 0,
        country_results["tax_revenue_loss_caused_musd"] / total_loss,
        0,
    )
    country_results["tax_revenue_loss_suffered_pct_of_total"] = np.where(
        total_loss > 0,
        country_results["tax_revenue_loss"] / total_loss,
        0,
    )

    country_results["current_tax_paid_cash_musd"] = np.where(
        country_results["current_tax_paid_cash_usd_raw"].notna(),
        country_results["current_tax_paid_cash_usd_raw"].clip(lower=0) / 1e6,
        np.nan,
    )

    country_results["revenue_gain_from_ut_pct_of_current_tax_paid"] = np.where(
        country_results["current_tax_paid_cash_musd"] > 0,
        100
        * country_results["revenue_gain_from_ut"]
        / country_results["current_tax_paid_cash_musd"],
        np.nan,
    )

    country_results["tax_revenue_loss_pct_of_current_tax_paid"] = np.where(
        country_results["current_tax_paid_cash_musd"] > 0,
        100
        * country_results["tax_revenue_loss"]
        / country_results["current_tax_paid_cash_musd"],
        np.nan,
    )

    country_results["tax_revenue_gain_pct_of_current_tax_paid"] = np.where(
        country_results["current_tax_paid_cash_musd"] > 0,
        100
        * country_results["tax_revenue_gain"]
        / country_results["current_tax_paid_cash_musd"],
        np.nan,
    )

    country_results["year"] = year
    country_results["formula_name"] = formula_name
    country_results["etr_name"] = etr_name
    country_results["etr_col"] = etr_col
    country_results["etr_threshold"] = etr_threshold
    country_results["threshold_rate_col"] = threshold_rate_col
    country_results["rate_mode"] = rate_mode_name
    country_results["loss_rate_col"] = loss_rate_col
    country_results["gain_rate_col"] = gain_rate_col
    country_results["sample_name"] = sample_name

    return country_results


def run_estimation_year(
    year,
    cbcr_data,
    formula_spec,
    etr_spec,
    rate_mode,
    etr_threshold,
    sample_name,
    reported_sign_override=None,
):
    cbcr_year = cbcr_data.loc[cbcr_data["year"] == year].copy()

    if cbcr_year.empty:
        return None, None, None

    misalignment = calculate_misalignment(
        cbcr_data=cbcr_year,
        formula_vars=formula_spec["formula_vars"],
        weights=formula_spec["weights"],
        profit_var=PROFIT_VAR,
        pool_var=POOL_VAR,
                        loss_rate_col=rate_mode["loss_rate_col"],
        reported_sign_override=reported_sign_override,
    )
    misalignment["year"] = year
    misalignment["formula_name"] = formula_spec["name"]
    misalignment["etr_name"] = etr_spec["name"]
    misalignment["etr_col"] = etr_spec["etr_col"]
    misalignment["etr_threshold"] = etr_threshold
    misalignment["threshold_rate_col"] = etr_spec["etr_col"]
    misalignment["rate_mode"] = rate_mode["name"]
    misalignment["loss_rate_col"] = rate_mode["loss_rate_col"]
    misalignment["gain_rate_col"] = rate_mode["gain_rate_col"]
    misalignment["sample_name"] = sample_name

    country_results = aggregate_country_results(
        misalignment_df=misalignment,
        year=year,
        loss_rate_col=rate_mode["loss_rate_col"],
        gain_rate_col=rate_mode["gain_rate_col"],
        formula_name=formula_spec["name"],
        etr_name=etr_spec["name"],
        etr_col=etr_spec["etr_col"],
        etr_threshold=etr_threshold,
        threshold_rate_col=etr_spec["etr_col"],
        rate_mode_name=rate_mode["name"],
        sample_name=sample_name,
    )

    aggregate_rows = build_aggregate_rows(
        country_results=country_results,
        year=year,
        formula_name=formula_spec["name"],
        etr_name=etr_spec["name"],
        etr_col=etr_spec["etr_col"],
        etr_threshold=etr_threshold,
        threshold_rate_col=etr_spec["etr_col"],
        rate_mode_name=rate_mode["name"],
        loss_rate_col=rate_mode["loss_rate_col"],
        gain_rate_col=rate_mode["gain_rate_col"],
        sample_name=sample_name,
    )

    return misalignment, country_results, aggregate_rows


def compute_pooled_reported_sign(
    df, formula_spec, etr_spec, rate_mode, etr_threshold, years
):
    """Pooled (all-years) reported-direction anchor per partner, for the
    'aggregate' sign-guard mode. Runs the reported-only misalignment for each year
    (is_distributed==0, guard off), sums each partner's misaligned_profit across
    years, and returns its sign (0 where |sum| < REPORTED_SIGN_EPS_USD). Clipping
    every year to this pooled sign forces the country's multi-year direction in the
    disaggregated sample to match the directly-reported cells. Returns None if there
    are no reported rows."""
    rep = df[df["is_distributed"] == 0] if "is_distributed" in df.columns else df
    acc = None
    for year in years:
        ry = rep[rep["year"] == year]
        if ry.empty:
            continue
        m = calculate_misalignment(
            cbcr_data=ry,
            formula_vars=formula_spec["formula_vars"],
            weights=formula_spec["weights"],
            profit_var=PROFIT_VAR,
            pool_var=POOL_VAR,
                                    loss_rate_col=rate_mode["loss_rate_col"],
            reported_sign_guard=False,
        )
        s = m.groupby("iso_partner")["misaligned_profit"].sum()
        acc = s if acc is None else acc.add(s, fill_value=0.0)
    if acc is None:
        return None
    return np.sign(acc.where(acc.abs() >= REPORTED_SIGN_EPS_USD, 0.0))


# %% MARK: 10. Load and validate input samples
for formula_spec in FORMULAS:
    validate_formula_spec(formula_spec)

for etr_spec in ETR_SPECS:
    validate_etr_spec(etr_spec)

samples = load_input_samples()


# %% MARK: 10.1 Define years to run
years_requested = list(range(first_year, first_year + n_years))

sample_years = {}
for sample_name, df in samples.items():
    years_available = sorted(df["year"].dropna().astype(int).unique())
    years_to_run = [year for year in years_requested if year in years_available]

    sample_years[sample_name] = years_to_run

    print(f"\nSample: {sample_name}")
    print(f"  Years requested: {years_requested}")
    print(f"  Years run: {years_to_run}")


# %% MARK: 11. Run all specifications
run_summary_rows = []

for sample_name, df in samples.items():
    print("\n" + "=" * 100)
    print(f"RUNNING SAMPLE: {sample_name}")
    print("=" * 100)

    output_dir = ensure_output_dir(sample_name)

    # Skip formulas whose factor columns are absent from this sample (e.g.
    # destination-share variants on a dataset without the merged share columns).
    available_cols = set(df.columns)
    # Optional formula allow-list (comma-separated formula names) for cheap runs —
    # e.g. the bootstrap driver sets RUN_FORMULAS="employees_payroll,sales_employees"
    # so each seed only computes the needed formulas. Empty = all formulas.
    _run_formulas_env = os.environ.get("RUN_FORMULAS", "").strip()
    _formula_allow = {f.strip() for f in _run_formulas_env.split(",") if f.strip()}
    formulas_for_sample = [
        f for f in FORMULAS
        if all(v in available_cols for v in f["formula_vars"])
        and (not _formula_allow or f["name"] in _formula_allow)
    ]
    skipped = [f["name"] for f in FORMULAS if f not in formulas_for_sample]
    if skipped:
        print(f"  [skip {len(skipped)} formulas not applicable to this sample] "
              f"{', '.join(skipped)}")

    # Full spec grid, plus (a) the p10-CIT optimistic mode for EVERY formula on
    # the "average" ETR spec, and (b) the remaining headline-only sensitivity
    # rate modes for (headline formula × "average" ETR spec) only.
    _spec_combos = [
        (f, e, ETR_THRESHOLD, r)
        for f, e in product(formulas_for_sample, ETR_SPECS)
        for r in (
            list(RATE_MODE_TEMPLATES)
            + ([RATE_MODE_TEMPLATE_OPT_ALL] if e["name"] == "average" else [])
            + (RATE_MODE_TEMPLATES_HEADLINE_ONLY
               if (f["name"] == HEADLINE_SENSITIVITY_FORMULA
                   and e["name"] == "average") else [])
        )
    ]
    for formula_spec, etr_spec, etr_threshold, rate_mode_template in _spec_combos:
        rate_mode = resolve_rate_mode(rate_mode_template, etr_spec)

        file_stub = make_file_stub(
            formula_name=formula_spec["name"],
            etr_name=etr_spec["name"],
            rate_mode_name=rate_mode["name"],
        )

        print("\n" + "-" * 100)
        print(
            f"Formula: {formula_spec['name']} | "
            f"ETR definition: {etr_spec['name']} ({etr_spec['etr_col']}) | "
            f"ETR max: {etr_threshold} | "
            f"Rate mode: {rate_mode['name']}"
        )
        print("-" * 100)

        results_country = []
        results_misalignment = []
        results_aggregate = []

        # Aggregate sign-guard mode: precompute the pooled (all-years) reported
        # direction ONCE for this spec, then clip every year to it so the country's
        # multi-year direction in the disaggregated sample matches the reported
        # cells. per_year mode leaves this None and each year self-anchors inside
        # calculate_misalignment.
        reported_sign_override = None
        if (SIGN_GUARD_MODE == "aggregate" and REPORTED_SIGN_GUARD
                and "is_distributed" in df.columns
                and (df["is_distributed"] == 1).any()
                and (df["is_distributed"] == 0).any()):
            reported_sign_override = compute_pooled_reported_sign(
                df, formula_spec, etr_spec, rate_mode, etr_threshold,
                sample_years[sample_name],
            )

        for year in sample_years[sample_name]:
            misalignment, country_results, aggregate_rows = run_estimation_year(
                year=year,
                cbcr_data=df,
                formula_spec=formula_spec,
                etr_spec=etr_spec,
                rate_mode=rate_mode,
                etr_threshold=etr_threshold,
                sample_name=sample_name,
                reported_sign_override=reported_sign_override,
            )

            if country_results is not None:
                results_country.append(country_results)
                results_misalignment.append(misalignment)
                results_aggregate.append(aggregate_rows)

                global_row = aggregate_rows.loc[
                    aggregate_rows["income_group_bucket"] == "global"
                ].iloc[0]

                print(
                    f"  {year}: shifted {global_row['total_shifted_musd']:,.0f}M USD | "
                    f"tax loss {global_row['total_tax_loss_musd']:,.0f}M USD | "
                    f"tax gain {global_row['total_tax_gain_musd']:,.0f}M USD"
                )
            else:
                print(f"  {year}: no data")

        if results_country:
            country_all_years = pd.concat(results_country, ignore_index=True)
        else:
            country_all_years = pd.DataFrame()

        if results_misalignment:
            misalignment_all_years = pd.concat(results_misalignment, ignore_index=True)
        else:
            misalignment_all_years = pd.DataFrame()

        if results_aggregate:
            aggregate_df = pd.concat(results_aggregate, ignore_index=True)
        else:
            aggregate_df = pd.DataFrame()

        country_all_years = order_country_columns(country_all_years)
        misalignment_all_years = order_misalignment_columns(misalignment_all_years)
        aggregate_df = order_aggregate_columns(aggregate_df)

        country_file = output_dir / f"country_estimates__{file_stub}.csv"
        misalignment_file = output_dir / f"misalignment__{file_stub}.csv"
        aggregate_file = output_dir / f"aggregate_results__{file_stub}.csv"

        country_all_years.to_csv(_longpath(country_file), index=False)
        misalignment_all_years.to_csv(_longpath(misalignment_file), index=False)
        aggregate_df.to_csv(_longpath(aggregate_file), index=False)

        if not aggregate_df.empty:
            aggregate_global_df = aggregate_df.loc[
                aggregate_df["income_group_bucket"] == "global"
            ].copy()

            aggregate_low_df = aggregate_df.loc[
                aggregate_df["income_group_bucket"] == "low_income"
            ].copy()

            aggregate_middle_df = aggregate_df.loc[
                aggregate_df["income_group_bucket"] == "middle_income"
            ].copy()
        else:
            aggregate_global_df = pd.DataFrame()
            aggregate_low_df = pd.DataFrame()
            aggregate_middle_df = pd.DataFrame()

        total_current_tax_paid_cash_musd_all_years = (
            safe_series_sum(aggregate_global_df["total_current_tax_paid_cash_musd"])
            if not aggregate_global_df.empty
            and "total_current_tax_paid_cash_musd" in aggregate_global_df.columns
            else np.nan
        )

        if (
            pd.notna(total_current_tax_paid_cash_musd_all_years)
            and total_current_tax_paid_cash_musd_all_years > 0
        ):
            revenue_gain_from_ut_pct_of_current_tax_paid_all_years = (
                100
                * aggregate_global_df["total_revenue_gain_from_ut_musd"].sum()
                / total_current_tax_paid_cash_musd_all_years
            )
        else:
            revenue_gain_from_ut_pct_of_current_tax_paid_all_years = np.nan

        run_summary_rows.append(
            {
                "sample_name": sample_name,
                "formula_name": formula_spec["name"],
                "etr_name": etr_spec["name"],
                "etr_col": etr_spec["etr_col"],
                "etr_threshold": etr_threshold,
                "threshold_rate_col": etr_spec["etr_col"],
                "rate_mode": rate_mode["name"],
                "loss_rate_col": rate_mode["loss_rate_col"],
                "gain_rate_col": rate_mode["gain_rate_col"],
                "n_country_rows": len(country_all_years),
                "n_misalignment_rows": len(misalignment_all_years),
                "n_years": (
                    aggregate_global_df["year"].nunique()
                    if not aggregate_global_df.empty
                    else 0
                ),
                "total_shifted_musd_all_years": (
                    aggregate_global_df["total_shifted_musd"].sum()
                    if not aggregate_global_df.empty
                    else 0
                ),
                "total_tax_loss_musd_all_years": (
                    aggregate_global_df["total_tax_loss_musd"].sum()
                    if not aggregate_global_df.empty
                    else 0
                ),
                "total_tax_gain_musd_all_years": (
                    aggregate_global_df["total_tax_gain_musd"].sum()
                    if not aggregate_global_df.empty
                    else 0
                ),
                "total_revenue_gain_from_ut_musd_all_years": (
                    aggregate_global_df["total_revenue_gain_from_ut_musd"].sum()
                    if not aggregate_global_df.empty
                    else 0
                ),
                "total_current_tax_paid_cash_musd_all_years": total_current_tax_paid_cash_musd_all_years,
                "revenue_gain_from_ut_pct_of_current_tax_paid_all_years": revenue_gain_from_ut_pct_of_current_tax_paid_all_years,
                "total_revenue_gain_from_ut_low_income_musd_all_years": (
                    aggregate_low_df["total_revenue_gain_from_ut_musd"].sum()
                    if not aggregate_low_df.empty
                    else 0
                ),
                "total_revenue_gain_from_ut_middle_income_musd_all_years": (
                    aggregate_middle_df["total_revenue_gain_from_ut_musd"].sum()
                    if not aggregate_middle_df.empty
                    else 0
                ),
                "country_file": str(country_file),
                "misalignment_file": str(misalignment_file),
                "aggregate_file": str(aggregate_file),
            }
        )


# %% MARK: 12. Save and display run summary
run_summary = pd.DataFrame(run_summary_rows)
run_summary = order_run_summary_columns(run_summary)

# MERGE into the existing run_summary rather than overwrite: a supplementary
# pass (e.g. a DEST_SUBSET fast run) would otherwise REPLACE the
# file with just its subset, so it would never hold an authoritative list of the
# topic's current specs — script 6 gates its concatenation on this file,
# so it must ACCUMULATE. Specs re-run in this pass replace their previous
# row; all other previous rows are kept.
_rs_path = OUTPUT_ROOT / "run_summary.csv"
_spec_key = ["sample_name", "formula_name", "etr_name", "etr_threshold", "rate_mode"]
if _rs_path.exists() and not run_summary.empty:
    try:
        _prev = pd.read_csv(_rs_path)
        _new = run_summary.copy()
        for _f in (_prev, _new):
            _f["etr_threshold"] = _f["etr_threshold"].astype(str)
        run_summary = (
            pd.concat([_new, _prev], ignore_index=True)
            .drop_duplicates(subset=_spec_key, keep="first")
        )
        run_summary = order_run_summary_columns(run_summary)
    except Exception as _exc:
        print(f"[warn] could not merge existing run_summary ({_exc}) — overwriting")

run_summary.to_csv(_rs_path, index=False)

print("\n" + "=" * 100)
print("RUN SUMMARY")
print("=" * 100)

if not run_summary.empty:
    print(run_summary.to_string(index=False))
else:
    print("No results produced.")
