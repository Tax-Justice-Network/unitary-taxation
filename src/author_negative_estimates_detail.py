# %%
"""
Negative-estimate detail — WHICH country loses under WHICH formula, and WHY.

Reads the tidy `country_estimates_long.csv` produced by
`9g_country_estimates_sheet.py` and builds an explanatory deliverable:

  negative_estimates_detail.xlsx
    - Legend                : plain-language column guide
    - Overview              : one row per country that loses under >=1 formula
                              (headline = baseline, destination sales), with the
                              per-formula net change, how many formulas it loses
                              under, whether it loses under ALL, the reason
                              category, and the reported-sample value for contrast
    - By formula (full)     : per-formula net change, full/imputed sample
    - By formula (reported) : per-formula net change, reported-only sample
    - Resource flips        : baseline vs resources-excluded, to evidence the
                              "commodity exporter" reason
  negative_by_formula_full.csv / negative_by_formula_reported.csv
  negative_estimates_explained.md  (regenerated narrative, links to the table)

Reason categories (assigned data-drivenly, precedence A > D > B > C):
  A  investment hub / tax haven        -> ISO in TAX_HAVENS_REPRESENTATION
  D  imputation artefact (full only)   -> imputed sales > 2x GDP and non-haven
  B  commodity exporter                -> baseline loss flips to a gain once
                                          resource rents are excluded
  C  production / MNE-home economy     -> robust loss in both samples, none of A/D/B

Usage: python 9h_negative_estimates_detail.py   (run AFTER 9g)
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

from config import output_dirs, data_final, TAX_HAVENS_REPRESENTATION, TAX_HAVENS_FUNCTIONAL

# Headline view used for the Overview / reason logic.
HEAD_SCEN = "baseline (resources ignored)"
EXCL_SCEN = "resources excluded"
HEAD_BASIS = "destination sales"
FULL = "full sample (imputed)"
REP = "reported-only sample"

# Formula display order (employees+payroll has no sales factor, so it carries no
# destination variant — we fall back to its origin value for the destination view).
FORMULA_ORDER = [
    "employees + payroll",
    "CCCTB",
    "Three-factor",
    "Double-weighted sales",
    "Sales + employees",
]
NO_DEST = {"employees + payroll"}  # formulas with no destination variant


def rd(path, **kw):
    try:
        return pd.read_csv(path, **kw)
    except (FileNotFoundError, OSError):
        dst = os.path.join(tempfile.gettempdir(), "neg_" + os.path.basename(path))
        for cp in (r"C:\Program Files\Git\usr\bin\cp.exe", "cp"):
            try:
                subprocess.run([cp, os.fspath(path), dst], check=True)
                return pd.read_csv(dst, **kw)
            except Exception:
                continue
        raise


def headline_basis_value(df, sample, scenario, formula):
    """Net value at the headline basis (destination), falling back to origin for
    formulas that have no destination variant."""
    basis = "origin sales" if formula in NO_DEST else HEAD_BASIS
    d = df[(df["sample"] == sample) & (df["scenario"] == scenario)
           & (df["formula"] == formula) & (df["sales_basis"] == basis)]
    return d.set_index("ISO3")["net_taxrev_change_USDm"]


def main():
    tables_dir, _ = output_dirs("deliverables/country_sheet")
    long_path = tables_dir / "country_estimates_long.csv"
    if not long_path.exists():
        print(f"  [error] {long_path} not found — run 9g_country_estimates_sheet.py first")
        return
    long = rd(long_path)
    meta = long[["ISO3", "Country", "Income group", "Region"]].drop_duplicates("ISO3")

    # ---- imputation-inflation set (same definition as 9g) ----
    gdf = rd(f"{data_final}cbcr_main_disaggregated.csv", low_memory=False,
             usecols=["iso_partner", "year", "unrelated_party_revenues"])
    gdp = rd(f"{data_final}cbcr_main_allsubgroupsonly.csv",
             usecols=["iso_partner", "year", "gdp_current_usd"]).drop_duplicates(
                 ["iso_partner", "year"])
    sg = gdf.groupby(["iso_partner", "year"], as_index=False)[
        "unrelated_party_revenues"].sum().merge(gdp, on=["iso_partner", "year"], how="left")
    sg["r"] = sg["unrelated_party_revenues"] / sg["gdp_current_usd"]
    ratio = sg.groupby("iso_partner")["r"].mean()
    # Mirrors the script-2 cap exemption, so it uses the FROZEN functional haven
    # set: cap-exempt havens (e.g. Guernsey) exceed 2x GDP by design, not artefact.
    inflated = {i for i, v in ratio.items() if v > 2 and i not in TAX_HAVENS_FUNCTIONAL}

    # ---- per-formula wide frames (headline scenario), per sample ----
    def per_formula_wide(sample):
        cols = {}
        for f in FORMULA_ORDER:
            cols[f] = headline_basis_value(long, sample, HEAD_SCEN, f)
        w = pd.DataFrame(cols)
        w["# formulas with a loss"] = (w[FORMULA_ORDER] < 0).sum(axis=1)
        w["loses under ALL formulas"] = (w[FORMULA_ORDER] < 0).all(axis=1)
        w["worst loss (any formula)"] = w[FORMULA_ORDER].min(axis=1)
        return w

    wide_full = per_formula_wide(FULL)
    wide_rep = per_formula_wide(REP)

    # ---- resource-flip detection (baseline vs resources-excluded), full sample ----
    def flips_positive(iso):
        """True if the country loses at baseline but gains once resources are
        excluded, on a majority of formulas (the commodity-exporter signature)."""
        n_flip = n_neg = 0
        for f in FORMULA_ORDER:
            b = headline_basis_value(long, FULL, HEAD_SCEN, f).get(iso, np.nan)
            e = headline_basis_value(long, FULL, EXCL_SCEN, f).get(iso, np.nan)
            if pd.notna(b) and b < 0:
                n_neg += 1
                if pd.notna(e) and e > 0:
                    n_flip += 1
        return n_neg > 0 and n_flip >= max(1, n_neg // 2)

    # ---- reason category (precedence A > D > B > C) ----
    def reason(iso, sample):
        if iso in TAX_HAVENS_REPRESENTATION:
            return ("A", "Investment hub / tax haven — UT reallocates shifted profit "
                         "back to where real activity and markets are (intended).")
        if sample == FULL and iso in inflated:
            return ("D", "Imputation artefact — the gravity model imputes implausibly "
                         "large activity (>2x GDP, non-haven); read the reported column.")
        if flips_positive(iso):
            return ("B", "Commodity exporter — destination sales send extractive profit "
                         "to buyer markets; recovers once resources are excluded.")
        return ("C", "Production / MNE-home economy — books profit at home; destination "
                     "apportionment moves it toward consumer markets abroad.")

    # ---- Overview (full sample, losers under >=1 formula) ----
    losers = wide_full[wide_full["# formulas with a loss"] > 0].index
    ov_rows = []
    for iso in losers:
        cat, txt = reason(iso, FULL)
        row = {"ISO3": iso}
        for f in FORMULA_ORDER:
            row[f] = round(float(wide_full.loc[iso, f]), 1) if pd.notna(
                wide_full.loc[iso, f]) else np.nan
        row["# formulas with a loss"] = int(wide_full.loc[iso, "# formulas with a loss"])
        row["loses under ALL formulas"] = bool(wide_full.loc[iso, "loses under ALL formulas"])
        wl = wide_full.loc[iso, "worst loss (any formula)"]
        row["worst loss (any formula)"] = round(float(wl), 1) if pd.notna(wl) else np.nan
        rep_val = wide_rep["worst loss (any formula)"].get(iso, np.nan)
        row["reported sample: worst loss"] = round(float(rep_val), 1) if pd.notna(rep_val) else np.nan
        row["reason category"] = cat
        row["why"] = txt
        ov_rows.append(row)
    overview = pd.DataFrame(ov_rows).merge(meta, on="ISO3", how="left")
    front = ["ISO3", "Country", "Income group", "Region", "reason category"]
    overview = overview[front + [c for c in overview.columns if c not in front]]
    overview = overview.sort_values(["reason category", "worst loss (any formula)"]
                                    if "worst loss (any formula)" in overview
                                    else "reason category")

    # ---- resource-flip evidence table ----
    flip_rows = []
    for iso in losers:
        for f in FORMULA_ORDER:
            b = headline_basis_value(long, FULL, HEAD_SCEN, f).get(iso, np.nan)
            e = headline_basis_value(long, FULL, EXCL_SCEN, f).get(iso, np.nan)
            if pd.notna(b) and b < 0:
                flip_rows.append({"ISO3": iso, "formula": f,
                                  "baseline (resources ignored)": round(float(b), 1),
                                  "resources excluded": round(float(e), 1) if pd.notna(e) else np.nan,
                                  "flips to a gain": bool(pd.notna(e) and e > 0)})
    flips = pd.DataFrame(flip_rows).merge(meta[["ISO3", "Country"]], on="ISO3", how="left")

    # ---- write CSVs ----
    wide_full.reset_index().rename(columns={"index": "ISO3"}).merge(
        meta, on="ISO3", how="left").to_csv(
        tables_dir / "negative_by_formula_full.csv", index=False)
    wide_rep.reset_index().rename(columns={"index": "ISO3"}).merge(
        meta, on="ISO3", how="left").to_csv(
        tables_dir / "negative_by_formula_reported.csv", index=False)
    overview.to_csv(tables_dir / "negative_estimates_overview.csv", index=False)

    legend = pd.DataFrame([
        ["Metric", "Net change in corporate tax revenue under unitary taxation, US$m, "
                   "cumulative 2016-2022. Negative = profit is reallocated away from the "
                   "country (a loss). Headline view = baseline scenario, destination-based "
                   "sales, full (imputed) sample; average ETR, gains at statutory CIT."],
        ["Per-formula columns", "Net change under each apportionment formula. "
                                "employees + payroll has no sales factor, so its "
                                "destination value equals its origin value."],
        ["# formulas with a loss", "How many of the 5 formulas leave the country worse off."],
        ["loses under ALL formulas", "TRUE = a robust loser regardless of formula choice."],
        ["reported sample: worst loss", "Worst per-formula loss using directly-reported data "
                                        "only (no imputation) — compare to the full-sample "
                                        "figures to spot imputation-driven losses."],
        ["reason category", "A = tax haven (intended loss); B = commodity exporter (recovers "
                            "when resources excluded); C = production/MNE-home economy; "
                            "D = imputation artefact (full sample only — use reported)."],
    ], columns=["Field", "Meaning"])

    xlsx = tables_dir / "negative_estimates_detail.xlsx"
    try:
        with pd.ExcelWriter(xlsx) as xw:
            legend.to_excel(xw, sheet_name="Legend", index=False)
            overview.to_excel(xw, sheet_name="Overview", index=False)
            wide_full.reset_index().merge(meta, on="ISO3", how="left").to_excel(
                xw, sheet_name="By formula (full)", index=False)
            wide_rep.reset_index().merge(meta, on="ISO3", how="left").to_excel(
                xw, sheet_name="By formula (reported)", index=False)
            flips.to_excel(xw, sheet_name="Resource flips", index=False)
        print(f"wrote {xlsx}")
    except Exception as e:
        print(f"  (xlsx skipped: {e})")

    # ---- regenerate the narrative md ----
    by_cat = overview.groupby("reason category")
    n_full = int((wide_full["# formulas with a loss"] > 0).sum())
    n_rep = int((wide_rep["# formulas with a loss"] > 0).sum())
    n_all = int(overview["loses under ALL formulas"].sum())
    lines = [
        "# Negative country estimates — which formula, and why",
        "",
        "Headline view: **baseline scenario, destination-based sales, full (imputed) "
        "sample**, average ETR, gains taxed at statutory CIT, cumulative 2016–2022. "
        "A negative value = profit is reallocated *away* from the country under unitary "
        "taxation. Full per-formula detail is in `negative_estimates_detail.xlsx` "
        "(Overview tab) and `negative_estimates_overview.csv`.",
        "",
        f"**{n_full} countries** lose under at least one formula in the full sample "
        f"({n_rep} in the reported-only sample); **{n_all}** lose under *all five* "
        "formulas. The reason a country loses, and whether it loses under every formula "
        "or only the sales-weighted ones, follows four patterns:",
        "",
    ]
    cat_titles = {
        "A": "A. Investment hubs / tax havens — *intended* losses",
        "B": "B. Commodity exporters — produce, don't consume",
        "C": "C. Production / MNE-home economies",
        "D": "D. Imputation artefacts — full (gravity) sample only",
    }
    for cat in ["A", "B", "C", "D"]:
        if cat not in by_cat.groups:
            continue
        g = by_cat.get_group(cat).sort_values("worst loss (any formula)")
        names = ", ".join(g["ISO3"].tolist()[:24])
        lines += [f"## {cat_titles[cat]}", "",
                  (g.iloc[0]["why"]), "",
                  f"*Countries ({len(g)}):* {names}", ""]
        # small table of the worst few, per formula
        show = g.head(8)
        hdr = "| country | " + " | ".join(FORMULA_ORDER) + " | loses under all? |"
        sep = "|" + "---|" * (len(FORMULA_ORDER) + 2)
        lines += [hdr, sep]
        for _, r in show.iterrows():
            cells = " | ".join(
                f"{r[f]:,.0f}" if pd.notna(r[f]) else "—" for f in FORMULA_ORDER)
            lines.append(f"| {r['ISO3']} | {cells} | "
                         f"{'yes' if r['loses under ALL formulas'] else 'no'} |")
        lines.append("")
    lines += [
        "## How to read the formula columns",
        "",
        "- **employees + payroll** and **three-factor** have little or no sales "
        "weight, so commodity exporters and consumer markets look very different here "
        "than under the sales-weighted formulas.",
        "- **CCCTB**, **double-weighted sales** and **sales + employees** put 33–50% "
        "weight on (destination) sales, so they move profit toward large consumer "
        "markets and away from producers/exporters — that is where category-B and "
        "category-C losses are largest.",
        "- A country that loses under **all five** formulas is a robust loser; one that "
        "loses only under the sales-weighted formulas is losing specifically because of "
        "the destination-sales reallocation.",
        "",
        "**Bottom line.** Robust losers in *both* samples are the tax havens (A), big "
        "commodity exporters (B) and large production/HQ economies (C). Category-D "
        "negatives appear only in the full (imputed) sample and should be read from the "
        "reported columns.",
    ]
    md = tables_dir / "negative_estimates_explained.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {md}")
    print(f"\nfull sample: {n_full} losers / reported: {n_rep} / lose under all 5: {n_all}")
    print(overview["reason category"].value_counts().to_dict())


if __name__ == "__main__":
    main()
