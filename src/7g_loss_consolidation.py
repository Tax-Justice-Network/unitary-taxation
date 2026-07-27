"""
9i — Loss-consolidation sensitivity (CbCR static approximation).

EX-POST add-on. Reads the per-row `misalignment__*.csv` outputs already written by
`5_estimate_profit_shifting.py` and applies a single correction to the REVENUE only:

    a country pays ZERO tax on a reported loss (no refund).

The current revenue gain credits a loss-reporting gainer with
`(theoretical - reported) x loss_rate = (theoretical + |loss|) x loss_rate`, i.e. it
treats the reported loss `-X` as a refund position. The corrected gain is
`theoretical x loss_rate` — the `-X -> 0` loss-recovery generates no tax. We compute the
overstatement per row and subtract it from `revenue_gain_from_ut` per country.

This is the SAME phenomenon as "international loss consolidation", but a PARTIAL, STATIC,
CbCR-aggregate, zero-carry-forward view of it (see the caveat printed/written below and in
docs/scenarios_methodology.md). It is an ADDITIONAL estimate — the main specification is
unchanged. Nothing here modifies the estimation pipeline or the headline outputs.

  * Taxable-profit / taxing-rights change is LEFT UNCHANGED (the fix is on the rate, not
    the profit base).
  * Exact for inf-threshold specs (no adjust_misalignment rescaling); approximate for
    finite (15%-haven-gated) specs — flagged in the `exact` column.

Output: output/unitary_taxation/across_samples/loss_consolidation_sensitivity/
Usage:  python 9i_loss_floored_sensitivity.py
"""
import os
import sys
import glob
import re
import numpy as np
import pandas as pd

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SRC_DIR)            # repo root (parent of src/)
sys.path.insert(0, _SRC_DIR)
import config  # noqa: E402

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SAMPLES = ["reported_only", "gravity"]   # reported is the headline; gravity for the appendix
# "baseline" added 2026-07-22 for the consolidation-bounds bracket (9i2): the
# lower bound must exist on the same scenario as the positive-panel upper bound.
SCENARIOS = ["baseline", "excl_resource", "excl_resource_floored"]
# scenario -> (folder name under the sample dir, inner tables subdir, PROFIT_COL key).
# The baseline run's folder is "baseline" but script 5 writes its per-spec files
# into a subdir named after its RUN_DATASET ("disaggregated").
SCENARIO_DIRS = {
    "baseline": ("baseline", "disaggregated", "disaggregated"),
    "excl_resource": ("excl_resource", "excl_resource", "excl_resource"),
    "excl_resource_floored": ("excl_resource_floored", "excl_resource_floored",
                              "excl_resource_floored"),
}

_DEFL = config.deflator_to_base()        # year → factor to constant BASE_YEAR USD
# Paper deliverables report the PER-YEAR AVERAGE over these years (2020 excluded).
# 9i has no mean-denominators, so scaling the deflator by 1/N converts every summed
# monetary output to a per-year average directly (Σ value·deflator/N = the mean).
AVG_YEARS = [2016, 2017, 2018, 2019, 2021, 2022]
N_AVG_YEARS = len(AVG_YEARS)

# Per-scenario reported-profit column used as the UT profit_var in script 5.
PROFIT_COL = {
    "disaggregated": "profit_loss_before_income_tax_corrected",
    "excl_resource": "profit_loss_excl_resource",
    "excl_resource_floored": "profit_loss_excl_resource_floored",
    "incl_resource": "profit_loss_incl_resource",
}

# Headline spec for the focused summary / verification.
HEADLINE_FORMULA = "sales_employees_destmnedds"   # paper headline (2026-07-12)
HEADLINE_RATE = "loss_cit_gain_etr"
HEADLINE_THRESHOLD = "inf"          # etrmax token in the file name
HEADLINE_ETR = "domfor"             # cell-matched dom/for ETR (2026-07-13 fix: without
                                    # this filter the summary SUMMED the domfor and
                                    # average-ETR runs, doubling the by-income values)

CAVEAT = (
    "Loss-consolidation sensitivity (CbCR static approximation): credits ZERO tax on "
    "reported losses in the apportionment (a loss pays no tax, not a refund). This is a "
    "PARTIAL, STATIC, CbCR-aggregate view of the loss-consolidation effect; it differs "
    "from the proper firm-level estimate (WIFO 2026), which is dynamic (models loss "
    "carry-forward across years) and group-level (captures losses netted inside "
    "net-positive cells). This measure (a) misses losses hidden inside net-positive "
    "aggregate cells and (b) ignores carry-forward value, so it is an UPPER BOUND on the "
    "permanent effect; the gap to the headline is largely transitory. ADDITIONAL estimate "
    "— NOT the main specification. Exact for inf-threshold specs; approximate for "
    "15%-haven-gated specs (negative side is rescaled in adjust_misalignment)."
)


def _spec_meta(df):
    """Pull spec identifiers (constant within a misalignment file)."""
    g = lambda c: (df[c].iloc[0] if c in df.columns and len(df) else None)
    return dict(
        formula=g("formula_name"), etr=g("etr_name"),
        threshold=g("etr_threshold"), rate=g("rate_mode"),
        loss_rate_col=g("loss_rate_col"), gain_rate_col=g("gain_rate_col"),
    )


def _lp(p):
    """Extended-length path so >260-char Windows paths open (mirrors script 5)."""
    if sys.platform == "win32":
        ap = os.path.abspath(p)
        if not ap.startswith("\\\\?\\"):
            return "\\\\?\\" + ap
    return p


def process_scenario(scenario, sample):
    scen_dir, inner_dir, prof_key = SCENARIO_DIRS.get(scenario, (scenario, scenario, scenario))
    mis_dir = os.path.join(
        _ROOT, "output", "unitary_taxation", sample, scen_dir, "tables", inner_dir)
    files = sorted(glob.glob(os.path.join(mis_dir, "misalignment__*.csv")))
    if not files:
        print(f"  [skip] no misalignment files under {mis_dir}")
        return pd.DataFrame()

    prof_col = PROFIT_COL.get(prof_key)
    rows = []
    for f in files:
        stub = os.path.basename(f)[len("misalignment__"):-len(".csv")]
        d = pd.read_csv(_lp(f), low_memory=False)
        if "year" in d.columns:
            d = d[d["year"].isin(AVG_YEARS)]
        meta = _spec_meta(d)
        lrc = meta["loss_rate_col"]
        if lrc is None or lrc not in d.columns:
            continue
        # reported profit for this scenario (fallback: reconstruct, inf-threshold only)
        if prof_col in d.columns:
            reported = pd.to_numeric(d[prof_col], errors="coerce").fillna(0.0)
        else:
            reported = (pd.to_numeric(d["theoretical_profit"], errors="coerce").fillna(0.0)
                        + pd.to_numeric(d["misaligned_profit"], errors="coerce").fillna(0.0))
        theo = pd.to_numeric(d["theoretical_profit"], errors="coerce").fillna(0.0)
        loss_rate = pd.to_numeric(d[lrc], errors="coerce").fillna(0.0)

        # loss-reporting gainer cells: reported < 0 AND allocated more (theoretical > reported)
        gainer_loss = (reported < 0) & (theo > reported)
        loss_recovery = np.where(gainer_loss, -reported, 0.0)          # the -X -> 0 part (USD)
        dfac = d["year"].map(_DEFL).fillna(1.0).to_numpy() / N_AVG_YEARS  # → per-year avg, constant BASE_YEAR USD
        overstated = loss_recovery * loss_rate * dfac                   # USD, BASE_YEAR prices

        gd = pd.DataFrame({
            "iso_partner": d["iso_partner"],
            "wb_income_group": d.get("wb_income_group"),
            "region_tjn": d.get("region_tjn"),
            "overstated_revenue_musd": overstated / 1e6,
            "loss_recovery_profit_musd": loss_recovery * dfac / 1e6,
        }).groupby(["iso_partner", "wb_income_group", "region_tjn"],
                   dropna=False, as_index=False).sum()

        # headline revenue_gain_from_ut + taxable-profit change from country_estimates
        ce_path = os.path.join(mis_dir, f"country_estimates__{stub}.csv")
        if not os.path.exists(_lp(ce_path)):
            continue
        ce = pd.read_csv(_lp(ce_path), low_memory=False)
        if "year" in ce.columns:
            ce = ce[ce["year"].isin(AVG_YEARS)]
        _cf = ce["year"].map(_DEFL).fillna(1.0) / N_AVG_YEARS   # per-year average
        for _c in ("revenue_gain_from_ut", "theoretical_profit", "reported_profit"):
            if _c in ce.columns:
                ce[_c] = pd.to_numeric(ce[_c], errors="coerce") * _cf
        ce_agg = ce.groupby("iso_partner", as_index=False).agg(
            revenue_gain_from_ut=("revenue_gain_from_ut", "sum"),
            theoretical_profit=("theoretical_profit", "sum"),
            reported_profit=("reported_profit", "sum"),
        )
        ce_agg["taxable_profit_change_musd"] = (
            ce_agg["theoretical_profit"] - ce_agg["reported_profit"])

        m = ce_agg.merge(gd, on="iso_partner", how="left")
        for c in ("overstated_revenue_musd", "loss_recovery_profit_musd"):
            m[c] = m[c].fillna(0.0)
        m["revenue_gain_loss_consolidated_musd"] = (
            m["revenue_gain_from_ut"] - m["overstated_revenue_musd"])
        m["pct_overstated"] = np.where(
            m["revenue_gain_from_ut"] > 0,
            100 * m["overstated_revenue_musd"] / m["revenue_gain_from_ut"], np.nan)
        m["sample"] = sample
        m["scenario"] = scenario
        m["formula"] = meta["formula"]
        m["etr"] = meta["etr"]
        m["etr_threshold"] = meta["threshold"]
        m["rate_mode"] = meta["rate"]
        m["loss_rate_col"] = lrc
        m["exact"] = str(meta["threshold"]) == "inf"   # rescaling only for finite threshold
        rows.append(m)

    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main():
    tables_dir, figures_dir = config.output_dirs(
        "deliverables/loss_consolidation_sensitivity")

    allres = []
    for sample in SAMPLES:
        for s in SCENARIOS:
            print(f"== processing {sample}/{s} ==")
            allres.append(process_scenario(s, sample))
    long = pd.concat([r for r in allres if not r.empty], ignore_index=True)

    cols = ["sample", "scenario", "formula", "etr", "etr_threshold", "rate_mode", "exact",
            "iso_partner", "wb_income_group", "region_tjn",
            "revenue_gain_from_ut", "overstated_revenue_musd",
            "revenue_gain_loss_consolidated_musd", "pct_overstated",
            "taxable_profit_change_musd", "loss_recovery_profit_musd", "loss_rate_col"]
    long = long[cols].sort_values(
        ["sample", "scenario", "formula", "rate_mode", "revenue_gain_from_ut"],
        ascending=[True, True, True, True, False])
    out_long = os.path.join(tables_dir, "loss_consolidation_country_long.csv")
    long.to_csv(out_long, index=False)
    print(f"\nwrote {out_long}  ({len(long):,} rows)")

    # caveat note alongside the data
    with open(os.path.join(tables_dir, "README_CAVEAT.txt"), "w", encoding="utf-8") as fh:
        fh.write(CAVEAT + "\n")

    # ---- headline-spec summary + verification ----
    h = long[(long.formula == HEADLINE_FORMULA) & (long.rate_mode == HEADLINE_RATE)
             & (long.etr_threshold.astype(str) == HEADLINE_THRESHOLD)
             & (long.etr.astype(str).str.contains(HEADLINE_ETR))]
    if h.empty:
        print(f"\n[warn] headline spec not found "
              f"({HEADLINE_FORMULA}/{HEADLINE_RATE}/etrmax_{HEADLINE_THRESHOLD}); "
              "skipping focused summary.")
        return

    order = ["low_income", "lower_middle_income", "upper_middle_income",
             "high_income", "investment_hub"]
    region_order = ["Africa", "Asia", "Latin America", "Caribbean/American isl.",
                    "Northern America", "Europe", "Oceania"]
    _val_cols = ["revenue_gain_from_ut", "overstated_revenue_musd",
                 "revenue_gain_loss_consolidated_musd"]
    for sample in SAMPLES:
      for scen in SCENARIOS:
        hs = h[(h["sample"] == sample) & (h.scenario == scen)]
        if hs.empty:
            continue
        print(f"\n[sample={sample}]", end="")
        byg = hs.groupby("wb_income_group")[_val_cols].sum().reindex(order) / 1e3  # $B
        # region-breakdown counterpart
        byr = hs.groupby("region_tjn")[_val_cols].sum().reindex(region_order) / 1e3
        byr.to_csv(os.path.join(
            tables_dir, f"loss_consolidation_by_region__{sample}__{scen}.csv"))
        tot_over = hs["overstated_revenue_musd"].sum() / 1e3
        win = hs[hs.revenue_gain_from_ut > 0]["revenue_gain_from_ut"].sum() / 1e3
        print(f"\n=== HEADLINE {sample}/{scen}: {HEADLINE_FORMULA}, {HEADLINE_RATE}, etrmax_{HEADLINE_THRESHOLD} ($B) ===")
        print(f"  Σ overstated revenue (loss consolidation): {tot_over:,.1f}")
        print(f"  winners' gains: {win:,.0f}  ->  overstatement {100*tot_over/win:.1f}% of winners' gains")
        print(byg.round(2).to_string())
        byg.to_csv(os.path.join(
            tables_dir, f"loss_consolidation_by_income_group__{sample}__{scen}.csv"))
        # verification asserts (do not crash; warn)
        bad = hs[hs.revenue_gain_loss_consolidated_musd > hs.revenue_gain_from_ut + 1e-6]
        if len(bad):
            print(f"  [WARN] {len(bad)} countries have floored > headline (should not happen)")
        # spot-check Luxembourg
        lux = hs[hs.iso_partner == "LUX"]
        if len(lux):
            r = lux.iloc[0]
            print(f"  LUX: headline {r.revenue_gain_from_ut/1e3:,.1f}B -> "
                  f"loss-consolidated {r.revenue_gain_loss_consolidated_musd/1e3:,.1f}B "
                  f"(overstated {r.overstated_revenue_musd/1e3:,.1f}B)")

    print("\n" + CAVEAT)


if __name__ == "__main__":
    main()
