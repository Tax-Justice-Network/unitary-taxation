# %% [markdown]
# Resource contribution: append extractive variables to the disaggregated
# CbCR dataset and produce a self-contained analysis dataset suitable for
# unitary taxation (UT) and the resource carve-out.
#
# Reads:  data/final/cbcr_main_disaggregated.csv (from 2_disaggregate_*)
# Writes: data/final/cbcr_main_with_extractives.csv
#
# The dataset has three blocks of added columns:
#
#   - Per source country (iso_partner, year):
#       rent_total_usd, rent_oil_gas_usd, rent_coal_usd,
#       rent_minerals_usd, rent_source,
#       captured_total_usd, captured_deductible_usd, captured_cit_usd,
#       captured_equity_usd, captured_*_source, *_carry_forwarded
#
#   The `rent_*` columns hold the layered best-estimate value
#   (EITI > BGS > EIA > WB per category). The provenance per partner-year is
#   recorded in `rent_source` (see docs/extractive/cbcr_main_with_extractives_columns.md
#   for the full value vocabulary).
#
#   - Per parent country × commodity (iso_parent, year):
#       hq_share_oil_gas, hq_share_coal, hq_share_minerals
#
#   - Per row (iso_parent, iso_partner, year):
#       state_share, alloc_weight_ioc_usd, alloc_weight_state_self_usd,
#       alloc_weight_usd, equity_add_back_active,
#       captured_deductible_allocated_usd, captured_equity_for_add_back_usd,
#       captured_equity_allocated_usd, profit_extractive_corrected
#
# ───────────────────────────── Conceptual flow ─────────────────────────────
#
# 1. PARTNER-LEVEL RENTS. Load a layered rent panel built upstream by
#    `3_extractive_prep/2_9_combined_rents.py`. Per (iso3, year, category):
#        EITI volumes  >  BGS volumes  >  EIA volumes  >  WB rent
#    where EITI/BGS/EIA volumes are converted to rent using country-specific
#    rent fractions reverse-engineered from the WB Resource Rents indicator
#    (calibration in `3_extractive_prep/2_8a_calibrate_rent_fractions.py`).
#    Carry-forward / backward within country fills annual gaps. The
#    `rent_source` column records provenance per cell. Despite the upstream
#    extractive panel still using `wb_*_rents_usd` as raw column names, the
#    output of this script exposes the layered values as `rent_total_usd`,
#    `rent_oil_gas_usd`, `rent_coal_usd`, `rent_minerals_usd` -- WB is only
#    the lowest-priority fallback in the cascade.
#
#    Captured government revenue (royalties + CIT + state PSA equity) comes
#    from the GRD > EITI > manual-fill cascade in
#    `data/raw/extractive_royalty_dataset_yearly.csv`.
#
#    Two consistency adjustments at partner-year level:
#      (a) Optional override layer at `data/raw/wb_resource_rents_overrides.csv`
#          can replace specific (iso, year, commodity) cells.
#      (b) Captured-revenue floor (toggle APPLY_CAPTURED_FLOOR=True): if
#          (captured_total_usd - captured_cit_usd) > rent_total_usd, scale up
#          per-commodity rents proportionally so rent_total matches that target.
#          Royalties/excise/levies/bonuses/SOE-dividends are lower-bound
#          evidence of rent; resource CIT is NOT (it can be ordinary CIT on
#          non-rent profit), so it is excluded from the floor target — the rent
#          cap downstream then keeps such ordinary CIT inside the UT pool.
#
# 2. HQ SHARES. Load Orbis-based shares per (iso_parent, commodity, year).
#    hq_share[parent, c, y] is the parent country's share of global
#    extractive-sector revenue for commodity c in year y.
#
# 3. PER-ROW EXTRACTION VALUE. Split rent into two pools, one routed via HQ
#    share to global IOC parents and one routed to the source country itself.
#
#        state_share[q, y]   = captured_total[q, y] / rent_total[q, y]
#                              clipped to [0, 1]
#        ioc_pool[p, q, y]   = (1 - state_share) × sum_c rent[q, c]
#                                                     × hq_share[p, c]
#        state_self_pool[p, q, y]
#                            = state_share × rent_total[q, y]      if p == q
#                            = 0                                   otherwise
#        alloc_weight_usd    = ioc_pool + state_self_pool
#
#    Each (year, iso_parent, iso_partner) cell has exactly one row in
#    cbcr_main_disaggregated.csv (enforced by sanity test A2), so the formula
#    runs once per cell — no row-count divisor needed.
#
#    The state-self pool represents the source country's own claim on rent
#    captured directly through royalties + CIT + state PSA equity. Routing
#    it to the (parent==partner) row prevents the IOC-pool allocation from
#    fictively reassigning state-captured rent to global IOC parents
#    proportional to their global oil/gas share.
#
#    Where script 2 produced multiple rows for a single (year, parent,
#    partner) cell (multi-source partner aggregation), the alloc_weight is
#    split evenly across duplicates so the cell sum equals one attribution.
#
# 4. CAPTURED-REVENUE ALLOCATION. Distribute partner-level
#    captured_deductible_usd across rows in proportion to alloc_weight_usd.
#    Captured equity flows through equity_add_back_active gating but with
#    ADD_BACK_EQUITY=False (default), the gated value stays zero -- the
#    state pool is already in the source country's own row from step 3, so
#    adding equity back to CbCR profit would double-count.
#
#    Captured CIT (`captured_cit_usd`) is NEVER added back -- it was paid
#    out of profit, not before it.
#
# 5. PROFIT CORRECTION (final output column).
#        profit_extractive_corrected
#          = profit_loss_before_income_tax_corrected
#            + captured_deductible_allocated_usd
#            + captured_equity_allocated_usd       (zero when ADD_BACK_EQUITY=False)
#    This recovers the pre-royalty extractive surplus and is the profit base
#    that downstream UT (script 5) and the carve-out (script 4) operate on.
#
# Run order:
#   src/3_resource_contribution.py           <- this script
#   src/4_carveout.py                        <- expected royalty rate + USD
#   src/4_carveout_summary.py                <- partner-year summary tables
#   src/5_estimate_profit_shifting.py        <- UT (uses profit_extractive_corrected)
#   src/3_validate_resource_contribution.py  <- validation tests

# %%
import sys
import pandas as pd
import numpy as np
from config import *

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

pd.set_option("display.max_columns", None)
pd.options.display.float_format = "{:,.2f}".format


# %% [1] Run settings.
#
# Toggle whether captured_equity_usd contributes to the per-row equity
# add-back to CbCR profit. The state PSA / SOE-equity portion of rent is
# already routed to the source country's own iso_parent row via
# state_self_pool in step 6, so adding equity back to CbCR profit on top
# would double-count. Keep False; the True branch is for sensitivity tests.
ADD_BACK_EQUITY = False

PROFIT_VAR = "profit_loss_before_income_tax_corrected"

# Which rent source feeds the partner-level rent column.
#   "wb"   - World Bank rents only.
#   "best" - Layered best-estimate panel (EITI > BGS > EIA > WB per category)
#            read from data/final/rents_combined_yearly.csv. Recommended for
#            full African-producer coverage and for analysis years where WB
#            hasn't published yet (currently 2022).
# In "best" mode, WB rents are still loaded first with carry-fwd/bwd, then
# the overlay replaces cells where EITI / BGS / EIA delivered a value.
RENT_SOURCE = "best"

# Enforce rent >= captured per (iso3, year). When captured government
# revenue (GRD / EITI / manual cascade) exceeds the rent estimate, scale up
# per-commodity rents proportionally so rent_total_usd >=
# captured_total_usd, and tag the source with ":floor_applied". A country
# can't fiscally capture more than 100% of its economic rent, so a capture
# ratio > 1 indicates the rent estimate under-states reality (typically
# because a global cost-curve mis-prices low-cost producers like LBY, SAU,
# IRQ). Setting rent = captured at minimum is a conservative correction
# that respects the ground-truth fiscal data.
APPLY_CAPTURED_FLOOR = True

# Commodities present on the HQ-share side (Orbis pipeline)
HQ_COMMODITIES = ["oil_gas", "coal", "minerals"]

# Mapping from HQ commodity to upstream WB rent columns (oil_gas = oil + gas).
# These are the column names in the upstream extractive panel; downstream
# they're combined into the layered `rent_<cat>_usd` columns.
COMMODITY_TO_WB_COLS = {
    "oil_gas": ["wb_oil_rents_usd", "wb_gas_rents_usd"],
    "coal": ["wb_coal_rents_usd"],
    "minerals": ["wb_mineral_rents_usd"],
}


# %% [2] Load inputs
print("Loading disaggregated CbCR...")
cbcr = pd.read_csv(f"{data_final}/cbcr_main_disaggregated.csv")
print(f"  {len(cbcr):,} rows; years {sorted(cbcr['year'].unique())}")

print("Loading extractive yearly panel (WB rents + GRD/EITI/manual capture)...")
extractive = pd.read_csv(extractive_royalty_yearly_data)
print(f"  {len(extractive):,} (iso3, year) rows")

print("Loading HQ shares by commodity...")
hq_shares = pd.read_csv(hq_shares_yearly_data)
print(f"  {len(hq_shares):,} (year, hq_iso3, commodity) rows")

print("Loading equity add-back overrides...")
overrides = pd.read_csv(equity_add_back_overrides_data, comment="#")
overrides["add_back_equity"] = (
    overrides["add_back_equity"].astype(str).str.strip().str.upper().eq("TRUE")
)
override_map = dict(zip(overrides["iso3"], overrides["add_back_equity"]))
print(
    f"  {len(override_map)} country overrides; "
    f"{sum(not v for v in override_map.values())} flagged FALSE (no equity add-back)"
)


# %% [3] Build per-source (partner) extractive table
# Keep WB commodity rents, captured_deductible, captured_cit, captured_equity.
EXT_NUM_COLS = [
    "wb_total_rents_usd",
    "wb_oil_rents_usd",
    "wb_gas_rents_usd",
    "wb_coal_rents_usd",
    "wb_mineral_rents_usd",
    "captured_total_usd",
    "captured_deductible_usd",
    "captured_cit_usd",
    "captured_equity_usd",
]
EXT_SRC_COLS = [
    "captured_total_source",
    "captured_deductible_source",
    "captured_cit_source",
    "captured_equity_source",
]
EXT_KEEP = ["iso3", "year"] + EXT_NUM_COLS + EXT_SRC_COLS
ext = extractive[EXT_KEEP].copy()
# IMPORTANT: keep NaN for WB cols here so we can distinguish genuinely missing
# years from real zeros. Captured cols still get fillna(0) because their
# downstream carry-fwd/bwd uses zero-as-missing semantics.
for c in EXT_NUM_COLS:
    ext[c] = pd.to_numeric(ext[c], errors="coerce")
for c in (
    "captured_total_usd",
    "captured_deductible_usd",
    "captured_cit_usd",
    "captured_equity_usd",
):
    ext[c] = ext[c].fillna(0.0)
for c in EXT_SRC_COLS:
    ext[c] = ext[c].fillna("").astype(str)

# Build the layered rent columns. At this point only WB has been loaded;
# the EITI/EIA/BGS overlay arrives in section [3c]. Despite the layered
# semantics, we name the columns `rent_<cat>_usd` from the start so the
# rest of the script and downstream consumers see consistent names.
# Use NaN-aware sum so a row missing both oil and gas stays NaN rather than 0.
ext["rent_oil_gas_usd"] = ext[["wb_oil_rents_usd", "wb_gas_rents_usd"]].sum(
    axis=1, min_count=1
)
ext = ext.rename(
    columns={
        "wb_total_rents_usd": "rent_total_usd",
        "wb_coal_rents_usd": "rent_coal_usd",
        "wb_mineral_rents_usd": "rent_minerals_usd",
    }
)
# Drop the per-fuel WB raw splits — they only ever held WB-only values and
# would be misleading alongside the layered combined columns.
ext = ext.drop(columns=["wb_oil_rents_usd", "wb_gas_rents_usd"])

# Per-category rent source tracking. Each category (oil_gas, coal, minerals)
# carries its own source string in `_rent_src_<cat>`. At the end of section
# [3] these get assembled into the human-readable `rent_source` column.
# Possible per-category source values:
#   "WB"                         WB published the value (incl. real zeros)
#   "WB:carry_fwd"               WB filled by forward-fill from earlier year
#   "WB:carry_bwd"               WB filled by backward-fill from later year
#   "EITI" / "EITI:carry_fwd" / "EITI:carry_bwd"
#   "BGS"  / "BGS:carry_fwd"  / "BGS:carry_bwd"
#   "EIA"  / "EIA:carry_fwd"  / "EIA:carry_bwd"
#   "WB_OVERRIDE:<note>"         set by section [3b] override file
#   "MISSING"                    no data of any kind for this category
# A separate boolean `rent_scaled_to_capture` flags rows where section [3d]
# scaled rents up to match captured government revenue.
CATEGORY_RENT_COLS = {
    "oil_gas": "rent_oil_gas_usd",
    "coal": "rent_coal_usd",
    "minerals": "rent_minerals_usd",
}
RENT_COLS = ["rent_total_usd"] + list(CATEGORY_RENT_COLS.values())
PER_CAT_SRC_COLS = {cat: f"_rent_src_{cat}" for cat in CATEGORY_RENT_COLS}
ext = ext.sort_values(["iso3", "year"]).reset_index(drop=True)

# Initial per-category source: "WB" wherever total_rents was published.
# (WB load is all-or-nothing across categories — any published row gives
# numeric values, possibly zero, for all three categories.)
wb_published = ext["rent_total_usd"].notna()
for cat, src_col in PER_CAT_SRC_COLS.items():
    ext[src_col] = np.where(wb_published, "WB", "")

# Carry forward then backward within each iso3 across the rent columns.
# Triggers only when the WHOLE row is missing (total NaN) -- a published-zero
# row is a real zero (e.g. countries with no extractive sector) and stays.
missing_row = ext["rent_total_usd"].isna()
for c in RENT_COLS:
    ext[c] = ext.groupby("iso3")[c].ffill()
fwd_filled = missing_row & ext["rent_total_usd"].notna()
for src_col in PER_CAT_SRC_COLS.values():
    ext.loc[fwd_filled, src_col] = "WB:carry_fwd"

still_missing = ext["rent_total_usd"].isna()
for c in RENT_COLS:
    ext[c] = ext.groupby("iso3")[c].bfill()
bwd_filled = still_missing & ext["rent_total_usd"].notna()
for src_col in PER_CAT_SRC_COLS.values():
    ext.loc[bwd_filled, src_col] = "WB:carry_bwd"

# Anything still NaN after both passes is genuinely absent in the panel
# (e.g. SSD, ERI, GNQ partially). Mark MISSING. Numeric stays NaN until the
# override layer below; see Phase 2 of the WB-coverage fix.
truly_missing = ext["rent_total_usd"].isna()
for src_col in PER_CAT_SRC_COLS.values():
    ext.loc[truly_missing, src_col] = "MISSING"

# Pre-overlay source counts (all three category sources move together at this
# stage, so just inspect oil_gas).
_first_src = ext[PER_CAT_SRC_COLS["oil_gas"]]
print(
    f"  WB rents: {(_first_src=='WB').sum()} published, "
    f"{(_first_src=='WB:carry_fwd').sum()} carry-fwd, "
    f"{(_first_src=='WB:carry_bwd').sum()} carry-bwd, "
    f"{(_first_src=='MISSING').sum()} still missing pre-override"
)

# %% [3b] WB rents override layer
# Read data/raw/wb_resource_rents_overrides.csv if it exists. Each row supplies
# a value for one (iso3, year, commodity) cell. Commodity codes:
#   total | oil_gas | coal | minerals
# An override on `total` resets the total column (use sparingly; per-commodity
# is preferred so the carve-out base aligns with HQ-share commodities). The
# override is applied AFTER carry-fwd/bwd so that a country's own published
# values are preferred where available.
import os as _os

override_path = _os.path.join(
    _os.path.dirname(_os.path.abspath(extractive_royalty_yearly_data)),
    "wb_resource_rents_overrides.csv",
)
COMMODITY_TO_COL = {
    "total": "rent_total_usd",
    "oil_gas": "rent_oil_gas_usd",
    "coal": "rent_coal_usd",
    "minerals": "rent_minerals_usd",
}
if _os.path.exists(override_path):
    ovr = pd.read_csv(override_path, comment="#")
    ovr.columns = [c.strip() for c in ovr.columns]
    ovr["iso3"] = ovr["iso3"].astype(str).str.strip().str.upper()
    ovr["year"] = pd.to_numeric(ovr["year"], errors="coerce").astype("Int64")
    ovr["commodity"] = ovr["commodity"].astype(str).str.strip().str.lower()
    ovr["rents_usd"] = pd.to_numeric(ovr["rents_usd"], errors="coerce")
    ovr = ovr.dropna(subset=["iso3", "year", "commodity", "rents_usd"])
    n_applied = 0
    n_skipped = 0
    any_per_commodity = False
    for _, r in ovr.iterrows():
        commodity = r["commodity"]
        col = COMMODITY_TO_COL.get(commodity)
        if col is None:
            n_skipped += 1
            continue
        mask = (ext["iso3"] == r["iso3"]) & (ext["year"] == int(r["year"]))
        if not mask.any():
            n_skipped += 1
            continue
        ext.loc[mask, col] = float(r["rents_usd"])
        src_label = f"WB_OVERRIDE:{str(r.get('source',''))[:50]}"
        if commodity == "total":
            # Mark all three per-category sources (no per-commodity values
            # were supplied; a "total" override is a blanket reset).
            for sc in PER_CAT_SRC_COLS.values():
                ext.loc[mask, sc] = src_label
        else:
            ext.loc[mask, PER_CAT_SRC_COLS[commodity]] = src_label
            any_per_commodity = True
        n_applied += 1
    # If a per-commodity override was applied, recompute total as the sum
    # of commodity components for that row (oil_gas+coal+minerals only --
    # forest is not part of the carve-out base).
    if any_per_commodity:
        any_overridden = pd.concat(
            [
                ext[sc].astype(str).str.startswith("WB_OVERRIDE")
                for sc in PER_CAT_SRC_COLS.values()
            ],
            axis=1,
        ).any(axis=1)
        if any_overridden.any():
            ext.loc[any_overridden, "rent_total_usd"] = ext.loc[
                any_overridden,
                ["rent_oil_gas_usd", "rent_coal_usd", "rent_minerals_usd"],
            ].sum(axis=1, min_count=1)
    print(f"  WB rent overrides: {n_applied} applied, {n_skipped} skipped (bad keys)")
else:
    print(f"  WB rent overrides: file not present at {override_path}")

# %% [3c] Best-of-three overlay (EITI > EIA > WB per category)
# Reads data/final/rents_combined_yearly.csv produced by 2_9_combined_rents.py
# and replaces wb_<category>_rents_usd cells with the best-estimate value when
# the source is EIA or EITI (i.e. country-self-reported or asset-level energy
# stats outperform the WB cost-curve model). Skipped when RENT_SOURCE != "best".
if RENT_SOURCE == "best":
    # rents_combined_yearly.csv lives in the same data/intermediate/extractive/
    # folder as extractive_royalty_dataset_yearly.csv.
    combined_path = _os.path.normpath(
        _os.path.join(
            _os.path.dirname(_os.path.abspath(extractive_royalty_yearly_data)),
            "rents_combined_yearly.csv",
        )
    )
    if not _os.path.exists(combined_path):
        print(
            "  [warn] RENT_SOURCE='best' but rents_combined_yearly.csv not "
            "found - falling back to WB-only. Run 2_9_combined_rents.py first."
        )
    else:
        print("Applying best-of-three rent overlay (EITI > EIA > WB)...")
        combined = pd.read_csv(combined_path)
        # Pivot to wide: one row per (iso3, year) with one rent_best_<cat>
        # column per category and a per-category source label.
        bp = combined.pivot_table(
            index=["iso3", "year"],
            columns="category",
            values=["rent_best_usd", "rent_best_source"],
            aggfunc="first",
        )
        bp.columns = [f"{a}__{b}" for a, b in bp.columns]
        bp = bp.reset_index()

        # Outer-merge so (iso, year) cells that exist in the combined panel
        # but NOT in the upstream WB-yearly panel get added as new rows. This
        # is the case for partners like BFA/MOZ/MDG/ETH 2022 where WB hasn't
        # published yet but BGS/EIA/EITI provided a rent estimate.
        ext = ext.merge(bp, on=["iso3", "year"], how="outer")
        # New rows from the right side need the standard structural columns.
        # All numeric rent / captured columns default to 0 (will be overwritten
        # by the overlay below if the source is non-WB; otherwise stay 0).
        for c in RENT_COLS + [
            "captured_total_usd",
            "captured_deductible_usd",
            "captured_cit_usd",
            "captured_equity_usd",
        ]:
            if c in ext.columns:
                ext[c] = ext[c].fillna(0.0)
        for c in EXT_SRC_COLS:
            if c in ext.columns:
                ext[c] = ext[c].fillna("MISSING")
        for sc in PER_CAT_SRC_COLS.values():
            if sc in ext.columns:
                ext[sc] = ext[sc].fillna("MISSING")
        for c in ("rent_carry_forwarded", "captured_carry_forwarded"):
            if c in ext.columns:
                ext[c] = ext[c].fillna(False)

        # Per category: where the best-source is EIA / EITI / BGS (i.e. better
        # than the WB cell we already have), replace the rent column AND
        # overwrite the per-category source. Cells with best-source = WB are
        # left alone (the value is identical anyway).
        n_replaced = {"EIA": 0, "EITI": 0, "BGS": 0}
        for cat, col in CATEGORY_RENT_COLS.items():
            best_col = f"rent_best_usd__{cat}"
            src_col = f"rent_best_source__{cat}"
            sc = PER_CAT_SRC_COLS[cat]
            if best_col not in ext.columns:
                continue
            for src in ("EIA", "EITI", "BGS"):
                # Match the source exactly OR with a carry-fwd/bwd suffix
                # (e.g. "EITI:carry_fwd") — those rows still came originally
                # from EIA/EITI and should overwrite the WB cell.
                src_str = ext[src_col].astype(str)
                mask = (
                    (src_str.eq(src) | src_str.str.startswith(src + ":"))
                    & ext[best_col].notna()
                    & (ext[best_col] > 0)
                )
                if mask.any():
                    ext.loc[mask, col] = ext.loc[mask, best_col].astype(float)
                    ext.loc[mask, sc] = src_str[mask].values
                    n_replaced[src] += int(mask.sum())
        print(
            f"  best overlay: replaced {n_replaced['EIA']} cells with EIA, "
            f"{n_replaced['EITI']} cells with EITI, "
            f"{n_replaced['BGS']} cells with BGS"
        )

        # Recompute rent_total_usd from the (possibly updated) per-category
        # components so the partner-level total reflects the overlay.
        ext["rent_total_usd"] = ext[
            ["rent_oil_gas_usd", "rent_coal_usd", "rent_minerals_usd"]
        ].sum(axis=1, min_count=1)

        # Drop the merge helper columns
        drop_cols = [c for c in ext.columns if c.startswith("rent_best_")]
        ext = ext.drop(columns=drop_cols)

# Final fillna(0) for downstream math. Genuinely-missing rows (per-category
# source = "MISSING") remain numerically zero.
for c in RENT_COLS:
    ext[c] = ext[c].fillna(0.0)
for sc in PER_CAT_SRC_COLS.values():
    ext[sc] = ext[sc].fillna("MISSING")

# Carry-forwarded flag: True iff the WB BASE for any category was filled by
# ffill/bfill. (Per-category EITI/EIA/BGS carry tags are also visible in the
# composite rent_source string assembled at the end of section [3].)
ext["rent_carry_forwarded"] = pd.concat(
    [
        ext[sc].astype(str).isin({"WB:carry_fwd", "WB:carry_bwd"})
        for sc in PER_CAT_SRC_COLS.values()
    ],
    axis=1,
).any(axis=1)

# Carry-forward AND backward of captured government revenue.
# Many large producers (USA, CHN, RUS, AUS, BRA, IRN, CAN, IND etc.) have
# captured revenue reported only in some years - manual fills are typically
# stamped to a single year, GRD coverage may be discontinuous, EITI may have
# gaps. Without filling, the carve-out comparison shows captured = 0 for
# those years and over-states the additional royalty owed. Treat zero as
# missing and ffill+bfill within each iso3 across the panel; mark the flag.
CAPTURED_COLS = [
    "captured_total_usd",
    "captured_deductible_usd",
    "captured_cit_usd",
    "captured_equity_usd",
]
CAPTURED_SRC_PAIRS = list(zip(CAPTURED_COLS, EXT_SRC_COLS))
zero_captured_mask = ext.groupby("iso3")["captured_total_usd"].transform(
    lambda s: s.eq(0)
)
for c, src_c in CAPTURED_SRC_PAIRS:
    ext.loc[zero_captured_mask, c] = np.nan
    ext.loc[zero_captured_mask, src_c] = np.nan
    ext[c] = ext.groupby("iso3")[c].ffill()
    ext[c] = ext.groupby("iso3")[c].bfill()
    ext[c] = ext[c].fillna(0.0)
    ext[src_c] = ext.groupby("iso3")[src_c].ffill()
    ext[src_c] = ext.groupby("iso3")[src_c].bfill()
    ext[src_c] = ext[src_c].fillna("")
ext["captured_carry_forwarded"] = zero_captured_mask & (ext["captured_total_usd"] > 0)
# Annotate the source for rows that were filled in by carry-fwd/bwd.
carry_idx = ext["captured_carry_forwarded"]
for _, src_c in CAPTURED_SRC_PAIRS:
    has_src = ext[src_c].astype(str).str.len() > 0
    tag_idx = carry_idx & has_src & ~ext[src_c].astype(str).str.endswith(":carry")
    ext.loc[tag_idx, src_c] = ext.loc[tag_idx, src_c].astype(str) + ":carry"
n_filled_cap = int(ext["captured_carry_forwarded"].sum())
print(
    f"  Captured revenue carry-filled (ffill+bfill) for {n_filled_cap} "
    f"(iso3, year) rows"
)


# %% [3d] Captured-revenue floor on rent
# Where the captured government revenue exceeds rent_total_usd, scale up the
# per-commodity rents proportionally so rent_total = that capture. This handles
# countries whose true rent is under-modelled (LBY, SAU, IRQ, etc.). The floor
# target is captured_total MINUS resource CIT: royalties, excise, levies,
# bonuses/fees and SOE dividends are lower-bound *evidence of rent* (the state
# demonstrably extracted at least that much value), but corporate income tax is
# not — a high EITI "CIT" line can just be ordinary CIT on non-rent profit, and
# scaling the rent estimate up to absorb it would defeat the rent cap that keeps
# such ordinary CIT inside the UT pool. When the rent is zero or very small but
# capture is non-zero, we can't scale (no commodity allocation to make) — those
# rows are left with rent=0 and flagged.
ext["rent_scaled_to_capture"] = False
if APPLY_CAPTURED_FLOOR:
    print(
        "Applying captured floor (rent >= captured_total - captured_cit per iso3,year)..."
    )
    _floor_target = ext["captured_total_usd"] - ext["captured_cit_usd"].fillna(0.0)
    floor_mask = (_floor_target > ext["rent_total_usd"]) & (ext["rent_total_usd"] > 0)
    n_scaled = int(floor_mask.sum())
    if n_scaled > 0:
        scale = _floor_target[floor_mask] / ext.loc[floor_mask, "rent_total_usd"]
        for c in ("rent_oil_gas_usd", "rent_coal_usd", "rent_minerals_usd"):
            ext.loc[floor_mask, c] = ext.loc[floor_mask, c] * scale
        ext.loc[floor_mask, "rent_total_usd"] = _floor_target[floor_mask]
        ext.loc[floor_mask, "rent_scaled_to_capture"] = True
    # Cells where rent is zero but capture is non-zero — flag without changing
    # the value (no commodity allocation to make).
    impossible_mask = (_floor_target > 0) & (ext["rent_total_usd"] <= 0)
    n_impossible = int(impossible_mask.sum())
    print(
        f"  scaled up {n_scaled} cells; "
        f"{n_impossible} cells have (capture - CIT) > 0 but rent = 0 (flagged, not scaled)"
    )


# Assemble the human-readable composite rent_source string from the per-
# category sources. Format: "oil_gas:<src> | coal:<src> | minerals:<src>".
# When all three categories are MISSING, collapse to just "MISSING".
def _assemble_rent_source(row):
    parts = [f"{cat}:{row[sc]}" for cat, sc in PER_CAT_SRC_COLS.items()]
    if all(row[sc] == "MISSING" for sc in PER_CAT_SRC_COLS.values()):
        return "MISSING"
    return " | ".join(parts)


ext["rent_source"] = ext.apply(_assemble_rent_source, axis=1)
# Drop the private per-category source columns. Comment these `drop` lines
# out (and add the columns to COLUMNS_STAGE_3) to expose them downstream.
ext = ext.drop(columns=list(PER_CAT_SRC_COLS.values()))


# %% [3e] Per-(iso, year, category) price, gross revenue, volume
#
# Derive three auditable extractive-volume columns per commodity category,
# at the (iso3, year) level, parallel to rent_<cat>_usd. These are the
# inputs the variable-royalty carve-out (script 4) needs:
#
#   price_<cat>             reference commodity price for the year
#   gross_revenue_<cat>_usd rent_<cat>_usd / rent_fraction_<cat>
#                           (back-computed; uses calibrated per-(iso, cat)
#                           rent fractions when available, else flat default)
#   volume_<cat>            gross_revenue / price (implied physical units)
#
# For EITI/EIA/BGS-sourced rent cells, gross_revenue exactly recovers the
# upstream <src>_revenue_usd (since rent = revenue × calibrated_fraction).
# For WB-only cells the back-compute is approximate.

# Reference prices come from the shared module (src/3_extractive_prep/
# _reference_prices.py — single source of truth; importable here via the
# sys.path entry added in config.py).
from _reference_prices import (
    BRENT_USD_BBL as _BRENT_USD_BBL,
    COAL_AUS_USD_T as _COAL_AUS_USD_T,
    MINERAL_PRICES as _MINERAL_PRICES,
    RENT_FRAC_DEFAULT as _RENT_FRACTIONS_DEFAULT,
)

_CATEGORY_REF_PRICES = {
    "oil_gas": _BRENT_USD_BBL,  # Brent
    "coal": _COAL_AUS_USD_T,  # Australian thermal coal
    "minerals": _MINERAL_PRICES["2601"],  # iron ore CFR China — single anchor
}


def _yearly_lookup_local(table, year):
    year = int(year)
    if year in table:
        return table[year]
    avail = sorted(table.keys())
    if year < avail[0]:
        return table[avail[0]]
    return table[avail[-1]]


# Load calibrated rent fractions (built by 2_8a). Same lookup used by 2_9
# to convert volumes to rent — applying it here guarantees that
# back-computed gross_revenue = upstream <src>_revenue_usd for non-WB cells.
# Lives alongside extractive_royalty_dataset_yearly.csv in data/intermediate/extractive/.
_calib_rf_path = _os.path.normpath(
    _os.path.join(
        _os.path.dirname(_os.path.abspath(extractive_royalty_yearly_data)),
        "rent_fractions_calibrated.csv",
    )
)
_calib_lookup = {}
if _os.path.exists(_calib_rf_path):
    _calib_df = pd.read_csv(_calib_rf_path)
    _calib_lookup = {
        (r["iso3"], r["category"]): float(r["rent_fraction"])
        for _, r in _calib_df.iterrows()
        if pd.notna(r["rent_fraction"]) and float(r["rent_fraction"]) > 0
    }
    print(f"Loaded {len(_calib_lookup)} calibrated (iso, category) rent fractions")
else:
    print("  [warn] rent_fractions_calibrated.csv not present; using flat defaults")


def _rf_for(iso3: str, category: str) -> float:
    rec = _calib_lookup.get((iso3, category))
    if rec is not None:
        return rec
    return _RENT_FRACTIONS_DEFAULT[category]


print("Building per-(iso, year, category) price / gross_revenue / volume...")
for cat in ("oil_gas", "coal", "minerals"):
    rent_col = f"rent_{cat}_usd"
    price_table = _CATEGORY_REF_PRICES[cat]

    ext[f"price_{cat}"] = ext["year"].map(
        lambda y: _yearly_lookup_local(price_table, y)
    )
    rf_series = ext["iso3"].map(lambda iso: _rf_for(iso, cat))
    ext[f"gross_revenue_{cat}_usd"] = ext[rent_col] / rf_series
    ext[f"volume_{cat}"] = (
        (ext[f"gross_revenue_{cat}_usd"] / ext[f"price_{cat}"])
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )


# %% [4] HQ shares wide: one column per commodity
hq_wide = (
    hq_shares.pivot_table(
        index=["year", "hq_iso3"],
        columns="commodity",
        values="share",
        aggfunc="sum",
        fill_value=0.0,
    )
    .reset_index()
    .rename_axis(columns=None)
)
for c in HQ_COMMODITIES:
    if c not in hq_wide.columns:
        hq_wide[c] = 0.0
    hq_wide[c] = hq_wide[c].fillna(0.0)
hq_wide = hq_wide.rename(columns={c: f"hq_share_{c}" for c in HQ_COMMODITIES})


# %% [5] Merge onto CbCR rows
# Source-country (partner) extractive features
df = cbcr.merge(
    ext.rename(columns={"iso3": "iso_partner"}),
    on=["iso_partner", "year"],
    how="left",
)
ext_cols = [
    "rent_total_usd",
    "rent_oil_gas_usd",
    "rent_coal_usd",
    "rent_minerals_usd",
    "gross_revenue_oil_gas_usd",
    "gross_revenue_coal_usd",
    "gross_revenue_minerals_usd",
    "volume_oil_gas",
    "volume_coal",
    "volume_minerals",
    "price_oil_gas",
    "price_coal",
    "price_minerals",
    "captured_total_usd",
    "captured_deductible_usd",
    "captured_cit_usd",
    "captured_equity_usd",
]
for c in ext_cols:
    df[c] = df[c].fillna(0.0)
for c in EXT_SRC_COLS:
    df[c] = df[c].fillna("").astype(str)
# Rent source: rows from CbCR partners that have no row in the extractive
# panel at all (e.g. small jurisdictions outside the rent panel) get MISSING.
df["rent_source"] = df["rent_source"].fillna("MISSING").astype(str)
df["rent_carry_forwarded"] = df["rent_carry_forwarded"].fillna(False).astype(bool)
df["rent_scaled_to_capture"] = df["rent_scaled_to_capture"].fillna(False).astype(bool)
df["captured_carry_forwarded"] = (
    df["captured_carry_forwarded"].fillna(False).astype(bool)
)

# Parent-country HQ shares
df = df.merge(
    hq_wide.rename(columns={"hq_iso3": "iso_parent"}),
    on=["iso_parent", "year"],
    how="left",
)
for c in HQ_COMMODITIES:
    df[f"hq_share_{c}"] = df[f"hq_share_{c}"].fillna(0.0)


# %% [6] Per-row allocation weight (extraction value).
#
# Split partner-level rent into two pools:
#   ioc_pool        = (1 - state_share) × hq_share × rent_<cat>
#   state_self_pool =  state_share × rent_total  (only on parent==partner row)
# where state_share = captured_total / rent_total, clipped to [0, 1].
#
# state_share = the share of country rent the producing state already captures
# through ANY fiscal channel — royalties, excise, levies, bonuses/fees, SOE
# dividends / state PSA equity, AND corporate income tax on resource profit. We
# are deliberately instrument-agnostic here: a state that captures its rent via
# CIT (common — many regimes barely use royalties) should be protected just like
# one that uses royalties, otherwise the carve-out would re-expose CIT-reliant
# producers to having their rent formulary-apportioned away by the employee /
# payroll factors. Capped at 1: a state can't have a prior claim on more than the
# whole rent.
#
# The over-counting risk — that the EITI "CIT" line is sometimes just ordinary
# CIT on *non-rent* corporate profit, which UT should redistribute — is handled
# by the rent cap rather than by excluding CIT here: ordinary CIT on non-rent
# profit pushes captured_total above the rent estimate, so it gets clipped (and
# the rent-scaling floor in §3d deliberately does NOT scale the rent up to absorb
# CIT, so the clip actually bites). What survives the clip is rent-sized capture,
# which the producing country legitimately retains as a prior claim; the residual
# profit (including ordinary CIT base) flows through the IOC → UT machinery.
#
# Why captured_total rather than equity-only: GRD reports a single
# total_resource_revenue without disaggregating into equity / royalty / CIT
# for most PSA-regime countries (NGA, AGO, IRQ, DZA, LBY, GAB, COG, ...).
# Using captured_equity alone would degenerate to zero for these and leave
# state-captured rent fictively assigned to global IOC parents.
#
# The IOC pool is allocated across parent rows by hq_share. The state-self
# pool is routed only to (iso_parent == iso_partner) rows, treating
# state-captured rent as the source country's own claim that does not need
# UT redistribution.
#
# Script 2 (cbcr disaggregation) guarantees one row per (year, iso_parent,
# iso_partner) cell — sanity test A2 in
# 3_extractive_prep/sanity_test_resource_extraction.py asserts this. So the
# alloc_weight formulas just multiply rent × hq_share once per row.
df["state_share"] = np.where(
    df["rent_total_usd"] > 0,
    (df["captured_total_usd"] / df["rent_total_usd"]).clip(0.0, 1.0),
    0.0,
)

ioc_pool = (
    df["rent_oil_gas_usd"] * df["hq_share_oil_gas"]
    + df["rent_coal_usd"] * df["hq_share_coal"]
    + df["rent_minerals_usd"] * df["hq_share_minerals"]
) * (1.0 - df["state_share"])

is_self_row = df["iso_parent"] == df["iso_partner"]
state_self_pool = np.where(
    is_self_row,
    df["rent_total_usd"] * df["state_share"],
    0.0,
)

df["alloc_weight_ioc_usd"] = ioc_pool
df["alloc_weight_state_self_usd"] = state_self_pool
df["alloc_weight_usd"] = df["alloc_weight_ioc_usd"] + df["alloc_weight_state_self_usd"]


# %% [7] Equity gating per partner country.
# equity_add_back_active drives whether captured_equity_usd contributes to
# the per-row equity add-back column in step 8. The override file flags
# countries whose dominant SOE files CbCR (so its dividend would already
# implicitly sit inside profit_loss_before_income_tax). With
# ADD_BACK_EQUITY=False the gated value stays zero throughout because the
# state pool is already routed via state_self_pool in step 6; flipping the
# toggle to True would double-count.
df["equity_add_back_active"] = df["iso_partner"].map(
    lambda iso: override_map.get(iso, True)
)
if not ADD_BACK_EQUITY:
    df["equity_add_back_active"] = False


# %% [8] Allocate captured_deductible (and equity where gated) across rows
# in proportion to alloc_weight_usd within each (partner, year) cell.
def _allocate(df_in, captured_col, out_col):
    """Distribute partner-year captured total across rows by alloc_weight_usd."""
    weight_sum = df_in.groupby(["iso_partner", "year"])["alloc_weight_usd"].transform(
        "sum"
    )
    captured = df_in[captured_col]
    out = np.where(
        weight_sum > 0,
        captured * df_in["alloc_weight_usd"] / weight_sum.replace(0, np.nan),
        0.0,
    )
    return pd.Series(out, index=df_in.index, name=out_col).fillna(0.0)


print("\nAllocating captured_deductible across rows by HQ-share weight...")
df["captured_deductible_allocated_usd"] = _allocate(
    df, "captured_deductible_usd", "captured_deductible_allocated_usd"
)

print("Allocating captured_equity across rows (gated by override)...")
df["captured_equity_for_add_back_usd"] = np.where(
    df["equity_add_back_active"], df["captured_equity_usd"], 0.0
)
df["captured_equity_allocated_usd"] = _allocate(
    df, "captured_equity_for_add_back_usd", "captured_equity_allocated_usd"
)


# %% [9] Diagnostics: residual where captured revenue could not be allocated
# (no row in that partner-year had positive HQ-share weight)
def _residual_diag(df_in, captured_col, allocated_col, label):
    per_cell = (
        df_in.groupby(["iso_partner", "year"])
        .agg(captured=(captured_col, "first"), allocated=(allocated_col, "sum"))
        .reset_index()
    )
    per_cell["residual"] = per_cell["captured"] - per_cell["allocated"]
    unallocated = per_cell[(per_cell["captured"] > 0) & (per_cell["allocated"] == 0)]
    print(
        f"  {label}: total captured ${per_cell['captured'].sum() / 1e9:,.1f}B; "
        f"allocated ${per_cell['allocated'].sum() / 1e9:,.1f}B; "
        f"unallocated cells: {len(unallocated)} "
        f"(${unallocated['captured'].sum() / 1e9:,.1f}B)"
    )
    return per_cell


print("\nAllocation diagnostics:")
ded_diag = _residual_diag(
    df, "captured_deductible_usd", "captured_deductible_allocated_usd", "deductible"
)
eq_diag = _residual_diag(
    df,
    "captured_equity_for_add_back_usd",
    "captured_equity_allocated_usd",
    "equity (gated)",
)


# %% [10] Profit correction (the FINAL output column)
df["profit_extractive_corrected"] = (
    df[PROFIT_VAR].fillna(0.0)
    + df["captured_deductible_allocated_usd"]
    + df["captured_equity_allocated_usd"]
)


# %% [11] Output
from _column_order import COLUMNS_STAGE_3, apply_canonical_order

df = apply_canonical_order(df, COLUMNS_STAGE_3)

OUT = f"{data_final}/cbcr_main_with_extractives.csv"
df.to_csv(OUT, index=False)
print(f"\nWrote {len(df):,} rows -> {OUT}")

print("\nKey added columns (per source country, year):")
for c in [
    "rent_total_usd",
    "rent_oil_gas_usd",
    "rent_coal_usd",
    "rent_minerals_usd",
    "rent_source",
    "captured_total_usd",
    "captured_deductible_usd",
    "captured_cit_usd",
    "captured_equity_usd",
]:
    if c in df.columns:
        print(f"  {c}")
print("Per parent country (year, commodity):")
for c in ["hq_share_oil_gas", "hq_share_coal", "hq_share_minerals"]:
    if c in df.columns:
        print(f"  {c}")
print("Per row (parent x partner x year):")
for c in [
    "alloc_weight_usd",
    "equity_add_back_active",
    "captured_deductible_allocated_usd",
    "captured_equity_allocated_usd",
    "profit_extractive_corrected",
]:
    if c in df.columns:
        print(f"  {c}")

# Aggregate sanity checks
total_extraction = df["alloc_weight_usd"].sum() / 1e9
n_with_weight = (df["alloc_weight_usd"] > 0).sum()
total_profit_orig = df[PROFIT_VAR].sum() / 1e9
total_profit_new = df["profit_extractive_corrected"].sum() / 1e9
total_added = (
    df["captured_deductible_allocated_usd"].sum()
    + df["captured_equity_allocated_usd"].sum()
) / 1e9
print(
    f"\nTotal extraction value across rows: ${total_extraction:,.1f}B"
    f"\nRows with positive alloc_weight:    {n_with_weight:,} of {len(df):,}"
    f"\n\nGlobal profit before correction:  ${total_profit_orig:,.1f}B"
    f"\nProfit added back (deductible + gated equity): ${total_added:,.1f}B"
    f"\nGlobal profit after correction:   ${total_profit_new:,.1f}B"
)
