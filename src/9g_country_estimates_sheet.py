# %%
"""
Country overview — ONE metric-rich spreadsheet per sample.

For each sample (reported-only, gravity full) writes a wide overview to that
sample's folder (output/unitary_taxation/{sample}/country_overview/):

  country_overview_<sample>.xlsx   (Overview + Legend tabs)

Columns (all cumulative 2016–2022, average ETR):
  IDs: Country name | Country ISO |
       Income group (incl. tax haven category) [wb_income_group, has investment_hub] |
       Income group (excl. tax haven category) [raw WB income level]
  Then, per scenario (ignoring resources → excluding resources → excluding
  resources plus floor) × formula (5 families), each fully self-describing:
       tax base change (mUSD)                       = Σ(theoretical − reported profit)
       tax base change (% of tax base)              = ÷ Σ reported profit
       revenue change (ETR-ETR) (mUSD)              [loss_etr_gain_etr]
       revenue change (ETR-ETR) (% of tax revenue)  [÷ total govt tax revenue]
       revenue change (ETR-CIT) (mUSD)              [loss_cit_gain_etr: gain ETR, loss CIT]
       revenue change (ETR-CIT) (% of tax revenue)
  Floored scenario only — the 4 revenue columns INCLUDE the minimum royalty, plus:
       revenue change from minimum royalty (mUSD)        [Σ floor_add_on_cat1]
       revenue change from UT alone (ETR-ETR) (mUSD)
       revenue change from UT alone (ETR-CIT) (mUSD)

Also writes a tidy long table (country_estimates_long.csv, both samples, origin +
destination sales) to output/unitary_taxation/across_samples/country_overview/ —
consumed by 9h_negative_estimates_detail.py.

Usage: python 9g_country_estimates_sheet.py   (run after scripts 5/6 for both samples)
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

from config import output_dirs, data_final

YEARS = list(range(2016, 2023))
ETR = "domfor"                       # cell-matched domestic/foreign ETR (headline 2026-07-12)
RATE_ETR_ETR = "loss_etr_gain_etr"   # (ETR-ETR): gain & loss both at the (cell-matched) ETR
RATE_ETR_CIT = "loss_cit_gain_etr"   # (ETR-CIT): gain at ETR, loss at statutory CIT

# Formula families shown in the overview, in display order. The headline is
# employees + DESTINATION-based sales; the rest are the origin-based families.
FORMULAS = [
    ("sales_employees_destmnedds", "employees + destination-based sales"),
    ("ccctb", "CCCTB"),
    ("three_factors", "three-factor"),
    ("employees_payroll", "employees + payroll"),
]

SCEN_ORDER = ["ignoring resources", "excluding resources", "excluding resources plus floor"]

# sample -> {scenario -> UT topic}
SAMPLE_SCENARIO_TOPIC = {
    "reported only": {
        "ignoring resources": "unitary_taxation_disaggregated_reported",
        "excluding resources": "unitary_taxation_excl_resource_reported",
        "excluding resources plus floor": "unitary_taxation_excl_resource_floored_reported",
    },
    "gravity (full sample)": {
        "ignoring resources": "unitary_taxation_disaggregated",
        "excluding resources": "unitary_taxation_excl_resource",
        "excluding resources plus floor": "unitary_taxation_excl_resource_floored",
    },
}
SAMPLE_OUT_TOPIC = {
    "reported only": "country_overview_reported",
    "gravity (full sample)": "country_overview_gravity",
}
# floored dataset for the minimum-royalty add-on: (file, restrict to is_distributed==0)
SAMPLE_FLOORED_DATA = {
    "reported only": ("cbcr_main_excl_resource_floored.csv", True),
    "gravity (full sample)": ("cbcr_main_excl_resource_floored.csv", False),
}


def rd(path, **kw):
    try:
        return pd.read_csv(path, **kw)
    except (FileNotFoundError, OSError):
        dst = os.path.join(tempfile.gettempdir(), "co_" + os.path.basename(path))
        for cp in (r"C:\Program Files\Git\usr\bin\cp.exe", "cp"):
            try:
                subprocess.run([cp, os.fspath(path), dst], check=True)
                return pd.read_csv(dst, **kw)
            except Exception:
                continue
        raise


def load_summary(topic):
    p = output_dirs(topic)[0] / "summary_country_year_long.csv"
    if not p.exists():
        print(f"  [warn] missing summary for {topic}")
        return None
    return rd(p, low_memory=False)


def _sum_by_partner(df, formula, rate, cols):
    """Σ over YEARS, per iso_partner, of `cols`, for one (formula, ETR, rate)."""
    d = df[(df["formula_name"] == formula) & (df["etr_name"] == ETR)
           & (df["rate_mode"] == rate) & (df["year"].isin(YEARS))]
    if d.empty:
        return pd.DataFrame(columns=cols)
    return d.groupby("iso_partner")[cols].sum()


def royalty_by_partner(sample):
    """Minimum-royalty add-on (mUSD) per partner from the floored dataset.

    The resource floor add-on is a royalty on the country's *physical* resource
    production (from EITI/GRD), merged onto the CbCR rows — it is not a CbCR
    apportionment quantity. A producing country collects it on all its output
    regardless of whether the matching CbCR cell was reported directly or only
    via an imputed aggregate, so we sum the FULL add-on even in the
    reported-only sample. Restricting to is_distributed==0 would arbitrarily
    drop the part attached to imputed rows — e.g. it cut Burkina Faso's royalty
    from $257m to $13m and wrongly left it a net loser. Using the full add-on
    matches the royalty stream in the script-8 three-scenario summary.
    """
    fname, _ = SAMPLE_FLOORED_DATA[sample]
    df = rd(f"{data_final}{fname}", low_memory=False,
            usecols=lambda c: c in ("iso_partner", "year", "floor_add_on_cat1_usd"))
    df = df[df["year"].isin(YEARS)]
    s = df.groupby("iso_partner")["floor_add_on_cat1_usd"].sum() / 1e6
    return s  # mUSD


def build_overview(sample):
    scen_topic = SAMPLE_SCENARIO_TOPIC[sample]
    summaries = {sc: load_summary(t) for sc, t in scen_topic.items()}
    base = next((s for s in summaries.values() if s is not None), None)
    if base is None:
        print(f"  [error] no summaries for {sample}")
        return None

    # ---- ID columns ----
    meta = base[["iso_partner", "partner_jurisdiction", "wb_income_group"]].drop_duplicates(
        "iso_partner").set_index("iso_partner")
    out = pd.DataFrame(index=meta.index)
    out["Country name"] = meta["partner_jurisdiction"]
    out["Country ISO"] = out.index
    out["Income group"] = meta["wb_income_group"]

    royalty = royalty_by_partner(sample)

    def col(idx, name):
        """Reindex a per-partner Series to the output index, rounded."""
        return pd.to_numeric(idx.reindex(out.index), errors="coerce").round(1)

    for scen in SCEN_ORDER:
        df = summaries.get(scen)
        floored = scen == "excluding resources plus floor"
        for fkey, flabel in FORMULAS:
            pfx = f"{scen} | {flabel} | "
            if df is None:
                continue
            # tax base (rate-invariant; use ETR-ETR rows)
            tb = _sum_by_partner(df, fkey, RATE_ETR_ETR,
                                 ["theoretical_profit", "reported_profit",
                                  "revenue_gain_from_ut", "tax_revenue_current_usd"])
            cit = _sum_by_partner(df, fkey, RATE_ETR_CIT, ["revenue_gain_from_ut"])
            if tb.empty:
                continue
            base_profit = tb["reported_profit"]
            tax_base_change = tb["theoretical_profit"] - tb["reported_profit"]
            tax_rev_musd = tb["tax_revenue_current_usd"] / 1e6
            ut_etr_etr = tb["revenue_gain_from_ut"]
            ut_etr_cit = cit["revenue_gain_from_ut"] if not cit.empty else ut_etr_etr * np.nan

            if floored:
                roy = royalty.reindex(tb.index).fillna(0.0)
                rev_etr_etr = ut_etr_etr + roy
                rev_etr_cit = ut_etr_cit + roy
            else:
                rev_etr_etr, rev_etr_cit = ut_etr_etr, ut_etr_cit

            # A percentage change is only meaningful against a POSITIVE base —
            # for a negative (or zero) base the ratio sign-flips and misleads, so
            # we blank the % columns there (keep the absolute mUSD columns).
            base_den = base_profit.where(base_profit > 0)
            rev_den = tax_rev_musd.where(tax_rev_musd > 0)
            out[pfx + "tax base change (mUSD)"] = col(tax_base_change, None)
            out[pfx + "tax base change (% of tax base)"] = col(
                100 * tax_base_change / base_den, None)
            # For the floored scenario the headline revenue columns are the
            # OVERALL effect = UT revenue + minimum royalty; the two components
            # are then broken out below. For the other scenarios there is no
            # royalty, so the overall effect is just the UT revenue.
            tot = "total revenue change, UT + royalty" if floored else "revenue change"
            out[pfx + f"{tot} (ETR-ETR) (mUSD)"] = col(rev_etr_etr, None)
            out[pfx + f"{tot} (ETR-ETR) (% of tax revenue)"] = col(
                100 * rev_etr_etr / rev_den, None)
            out[pfx + f"{tot} (ETR-CIT) (mUSD)"] = col(rev_etr_cit, None)
            out[pfx + f"{tot} (ETR-CIT) (% of tax revenue)"] = col(
                100 * rev_etr_cit / rev_den, None)
            if floored:
                out[pfx + "of which: minimum royalty (mUSD)"] = col(roy, None)
                out[pfx + "of which: UT alone (ETR-ETR) (mUSD)"] = col(ut_etr_etr, None)
                out[pfx + "of which: UT alone (ETR-CIT) (mUSD)"] = col(ut_etr_cit, None)

    return out.reset_index(drop=True)


_LEGEND = pd.DataFrame([
    ["Scope", "Cumulative 2016–2022, average ETR. One spreadsheet per sample."],
    ["Income group", "World Bank income level, but recognised "
        "investment hubs/tax havens are shown as their own 'investment_hub' category."],
    ["tax base change (mUSD)", "Change in the country's taxable profit under unitary taxation "
        "= Σ(theoretical apportioned profit − reported profit). Negative = profit reallocated away."],
    ["tax base change (% of tax base)", "The above as a percentage of the country's reported "
        "taxable profit."],
    ["revenue change (ETR-ETR)", "Change in corporate tax revenue with BOTH recovered and "
        "foregone profit valued at the average effective tax rate (loss_etr_gain_etr)."],
    ["revenue change (ETR-CIT)", "Change in corporate tax revenue with recovered profit valued "
        "at the average ETR and foregone profit at the statutory CIT rate (loss_cit_gain_etr)."],
    ["% of tax revenue", "Revenue change as a percentage of the country's TOTAL government tax "
        "revenue (World Bank)."],
    ["total revenue change, UT + royalty", "Floored scenario only. The OVERALL government "
        "revenue effect = unitary-taxation revenue + the IGF-ATAF minimum royalty. The "
        "'of which: minimum royalty' / 'of which: UT alone' columns split this total into its "
        "two sources (royalty is rate-invariant; UT-alone is shown for each rate convention). "
        "The minimum royalty is levied on the country's full physical resource production "
        "(all owning MNEs), so it is not restricted to directly-reported CbCR rows."],
], columns=["Field", "Meaning"])


def main():
    for sample, out_topic in SAMPLE_OUT_TOPIC.items():
        ov = build_overview(sample)
        if ov is None:
            continue
        tables_dir, _ = output_dirs(out_topic)
        tag = "reported_only" if "reported" in sample else "gravity"
        xlsx = tables_dir / f"country_overview_{tag}.xlsx"
        try:
            with pd.ExcelWriter(xlsx) as xw:
                ov.to_excel(xw, sheet_name="Overview", index=False)
                _LEGEND.to_excel(xw, sheet_name="Legend", index=False)
            print(f"wrote {xlsx} ({ov.shape[0]} countries × {ov.shape[1]} cols)")
        except Exception as e:
            print(f"  (xlsx skipped: {e}); writing CSV")
            ov.to_csv(tables_dir / f"country_overview_{tag}.csv", index=False)
        ov.to_csv(tables_dir / f"country_overview_{tag}.csv", index=False)

    _write_long_table()


# ---- tidy long table (origin + destination) for 9h_negative_estimates_detail ----
_LONG_FORMULAS = [
    ("employees_payroll", "employees + payroll", None),
    ("ccctb", "CCCTB", "ccctb_destcombined"),
    ("three_factors", "Three-factor", "three_factors_destcombined"),
    ("double_weighted_sales", "Double-weighted sales", "double_weighted_sales_destcombined"),
    ("sales_employees", "Sales + employees", "sales_employees_destcombined"),
]
_LONG_SPECS = [
    ("full sample (imputed)", "baseline (resources ignored)", "unitary_taxation_disaggregated"),
    ("full sample (imputed)", "resources excluded", "unitary_taxation_excl_resource"),
    ("full sample (imputed)", "resources excluded + min. royalty floor", "unitary_taxation_excl_resource_floored"),
    ("reported-only sample", "baseline (resources ignored)", "unitary_taxation_disaggregated_reported"),
    ("reported-only sample", "resources excluded", "unitary_taxation_excl_resource_reported"),
    ("reported-only sample", "resources excluded + min. royalty floor", "unitary_taxation_excl_resource_floored_reported"),
]
_BASIS_LBL = {"destination": "destination sales", "origin": "origin sales"}


def _net(df, formula):
    if df is None or formula is None or formula not in set(df.get("formula_name", [])):
        return pd.Series(dtype=float)
    d = df[(df["formula_name"] == formula) & (df["etr_name"] == ETR)
           & (df["rate_mode"] == RATE_ETR_CIT) & (df["year"].isin(YEARS))]
    return d.groupby("iso_partner")["revenue_gain_from_ut"].sum()


def _write_long_table():
    topic_long = {t: load_summary(t) for _, _, t in _LONG_SPECS}
    meta = None
    for _, _, t in _LONG_SPECS:
        df = topic_long[t]
        if df is not None:
            mc = [c for c in ["iso_partner", "partner_jurisdiction", "wb_income_group", "region_tjn"]
                  if c in df.columns]
            meta = df[mc].drop_duplicates("iso_partner").rename(columns={
                "partner_jurisdiction": "Country", "wb_income_group": "Income group",
                "region_tjn": "Region", "iso_partner": "ISO3"})
            break
    # Floored scenarios: net revenue = UT revenue + the (full) minimum royalty,
    # so the long table matches the overview / script-8 headline. Map the long
    # table's sample labels to the royalty_by_partner sample keys.
    _ROY_SAMPLE = {"reported-only sample": "reported only",
                   "full sample (imputed)": "gravity (full sample)"}
    floored_roy = {lbl: royalty_by_partner(key) for lbl, key in _ROY_SAMPLE.items()}
    rows = []
    for sample, scen, topic in _LONG_SPECS:
        df = topic_long[topic]
        is_floored = "floor" in scen
        for fkey, flabel, destf in _LONG_FORMULAS:
            for basis, fname in [("origin", fkey), ("destination", destf)]:
                s = _net(df, fname)
                if s.empty:
                    continue
                if is_floored:
                    s = s + floored_roy.get(sample, pd.Series(dtype=float)).reindex(
                        s.index).fillna(0.0)
                rows.append(pd.DataFrame({
                    "ISO3": s.index, "sample": sample, "scenario": scen, "formula": flabel,
                    "sales_basis": _BASIS_LBL[basis], "net_taxrev_change_USDm": s.values.round(1)}))
    if not rows:
        return
    long = pd.concat(rows, ignore_index=True).merge(meta, on="ISO3", how="left")
    long = long[["ISO3", "Country", "Income group", "Region", "sample", "scenario",
                 "formula", "sales_basis", "net_taxrev_change_USDm"]]
    tables_dir, _ = output_dirs("deliverables/country_sheet")
    long.to_csv(tables_dir / "country_estimates_long.csv", index=False)
    print(f"wrote country_estimates_long.csv ({len(long):,} rows) for 9h")


if __name__ == "__main__":
    main()
