"""
Diagnostic for the EITI XLSX extraction.

For every (iso3, year, hs_code) cell in data/final/eiti_production_clean_long.csv
it compares the EITI-*reported* sales value (`value_money_total`, FX-converted
to USD where the currency is not already USD) against the value our pipeline
*reconstructs* from `volume_total × reference_price` — the same arithmetic
2_9_combined_rents.py / 2_8a use. A ratio far from 1 signals either:
  - a parse problem (wrong cell read, unit string leaked into a numeric or
    currency field, decimal-separator confusion), or
  - a price-proxy mismatch (our benchmark price differs a lot from the
    realized price — quality discounts, FOB vs benchmark, etc.).

It also runs a few structural parse checks (mixed units within an HS code,
absurd magnitudes, currency field that isn't a 3-letter code, …).

Reads:
  data/final/eiti_production_clean_long.csv
  data/raw/macro_variables/wb_fx_official_rate_2026-02.csv   (WB official exchange
                                                     rate, LCU per USD,
                                                     period average)
Writes:
  output/extractive/tables/eiti_extraction_diagnostic.csv   (full per-cell table)
  console summary

This is a read-only diagnostic — it does not change any pipeline output.
"""

import sys
from pathlib import Path

import pandas as pd
import numpy as np

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # src/ on path
from config import output_dirs                                  # noqa: E402
from _paths import RAW, EXT_INT                                  # noqa: E402
from _reference_prices import (                                 # noqa: E402
    MINERAL_PRICES, HS_PRICE_UNIT, MINERAL_VOL_TO_PRICE_MULT,
    BRENT_USD_BBL, HENRY_HUB_USD_MMBTU, COAL_AUS_USD_T,
)

EITI_CLEAN = EXT_INT / "eiti_production_clean_long.csv"
FX_CSV = RAW / "macro_variables/wb_fx_official_rate_2026-02.csv"
OUT_TABLES, _ = output_dirs("extractive")
OUT_CSV = OUT_TABLES / "eiti_extraction_diagnostic.csv"

# A reconstructed/reported ratio outside this band (and above a $-floor so we
# don't flag tiny rounding cells) gets flagged.
RATIO_LOW, RATIO_HIGH = 0.20, 5.0
MIN_FLAG_USD = 1.0e6   # only flag cells where at least one side exceeds this


def _yearly_lookup(table, year):
    year = int(year)
    if year in table:
        return table[year]
    avail = sorted(table.keys())
    return table[avail[0]] if year < avail[0] else table[avail[-1]]


def load_fx() -> dict:
    """Return {(country_iso3, year): LCU_per_USD}. World Bank PA.NUS.FCRF."""
    if not FX_CSV.exists():
        print(f"  [warn] {FX_CSV} not present — local-currency values can't be "
              f"converted; those rows get flagged 'no_fx'.")
        return {}
    # WB Open Data CSV has 4 metadata rows before the header.
    raw = pd.read_csv(FX_CSV, skiprows=4)
    year_cols = [c for c in raw.columns if c.strip().isdigit()]
    long = raw.melt(
        id_vars=["Country Code"], value_vars=year_cols,
        var_name="year", value_name="fx",
    )
    long["year"] = long["year"].astype(int)
    long["fx"] = pd.to_numeric(long["fx"], errors="coerce")
    long = long.dropna(subset=["fx"])
    long = long[long["fx"] > 0]
    return {(r["Country Code"], int(r["year"])): float(r["fx"])
            for _, r in long.iterrows()}


def reconstructed_revenue_usd(row) -> float:
    """Mirror the volume×price revenue computation used by 2_9 / 2_8a."""
    cat = row["category"]
    hs = str(row["hs_code"]).strip()
    year = int(row["year"])
    vol = row["volume_total"]
    unit = str(row["volume_unit"]).strip()
    if pd.isna(vol) or vol <= 0:
        return np.nan
    if cat == "minerals":
        if hs not in MINERAL_PRICES:
            return np.nan
        mult = MINERAL_VOL_TO_PRICE_MULT.get((unit, HS_PRICE_UNIT.get(hs)))
        if mult is None:
            return np.nan
        price = MINERAL_PRICES[hs].get(year)
        if price is None:
            return np.nan
        return vol * mult * price
    if cat == "oil_gas" and hs in ("2709", "2710"):
        if unit not in ("Sm3", "Sm3 o.e."):
            return np.nan
        return vol * 6.2898 * _yearly_lookup(BRENT_USD_BBL, year)   # Sm3 -> bbl
    if cat == "oil_gas" and hs == "2711":
        if unit not in ("Sm3", "Sm3 o.e."):
            return np.nan
        return vol * 0.0383 * _yearly_lookup(HENRY_HUB_USD_MMBTU, year)  # Sm3 gas -> MMBtu
    if cat == "coal":
        if unit != "tonnes":
            return np.nan
        return vol * _yearly_lookup(COAL_AUS_USD_T, year)
    return np.nan


def main():
    if not EITI_CLEAN.exists():
        sys.exit(f"{EITI_CLEAN} not present — run 2_7_eiti_to_clean_panel.py first.")
    e = pd.read_csv(EITI_CLEAN)
    e["hs_code"] = e["hs_code"].astype(str).str.strip()
    print(f"Loaded {len(e):,} EITI cells (iso3 × year × hs_code).")

    fx = load_fx()
    print(f"Loaded {len(fx):,} (country, year) FX rates.")

    # ── Value reported in USD ──
    val = pd.to_numeric(e["value_money_total"], errors="coerce")
    ccy = e["value_currency"].astype(str).str.strip()
    has_val = val.fillna(0) > 0

    def _to_usd(r_idx):
        v = val.iloc[r_idx]
        c = ccy.iloc[r_idx]
        if pd.isna(v) or v <= 0:
            return np.nan, ""
        if c.upper() == "USD":
            return float(v), "usd_as_is"
        if not (isinstance(c, str) and len(c) == 3 and c.isalpha()):
            return np.nan, "bad_currency_field"   # e.g. "Tonnes" leaked in
        rate = fx.get((e.iloc[r_idx]["iso3"], int(e.iloc[r_idx]["year"])))
        if rate is None or rate <= 0:
            return np.nan, "no_fx"
        return float(v) / rate, "fx_converted"

    usd_vals, conv_notes = [], []
    for i in range(len(e)):
        u, note = _to_usd(i)
        usd_vals.append(u)
        conv_notes.append(note)
    e["value_reported_usd"] = usd_vals
    e["value_conversion"] = conv_notes

    # ── Reconstructed revenue ──
    e["revenue_reconstructed_usd"] = e.apply(reconstructed_revenue_usd, axis=1)

    # ── Ratio ──
    e["ratio_reported_over_reconstructed"] = np.where(
        (e["revenue_reconstructed_usd"].fillna(0) > 0)
        & (e["value_reported_usd"].fillna(0) > 0),
        e["value_reported_usd"] / e["revenue_reconstructed_usd"],
        np.nan,
    )

    # ── Structural parse checks ──
    # A cell's volume_unit is "unconvertible" if the pipeline's reconstruction
    # path can't turn it into revenue (so the cell silently drops out of the
    # rent estimate). That's the unit-related parse problem worth flagging —
    # NOT the mere fact that an HS code appears with different (all
    # convertible) units across countries.
    def _unit_convertible(cat, hs, unit):
        unit = str(unit).strip()
        if cat == "minerals":
            return (unit, HS_PRICE_UNIT.get(hs)) in MINERAL_VOL_TO_PRICE_MULT
        if cat == "oil_gas":
            return unit in ("Sm3", "Sm3 o.e.")
        if cat == "coal":
            return unit == "tonnes"
        return True

    # "absurd magnitude" — a single (iso, year, hs) cell whose reconstructed
    # OR reported gross revenue exceeds the largest plausible single-commodity
    # single-country annual figure on record (Australia iron ore ~$120B in
    # 2021; nothing has exceeded ~$150B). Anything above that is a unit bug.
    ABSURD_USD = 1.5e11

    flags = []
    for _, r in e.iterrows():
        f = []
        cat, hs, unit = r["category"], str(r["hs_code"]).strip(), r["volume_unit"]
        rep = r["value_reported_usd"] if pd.notna(r["value_reported_usd"]) else 0.0
        rec = r["revenue_reconstructed_usd"] if pd.notna(r["revenue_reconstructed_usd"]) else 0.0
        ratio = r["ratio_reported_over_reconstructed"]
        raw_val = pd.to_numeric(r["value_money_total"], errors="coerce") or 0.0

        if r["value_conversion"] == "bad_currency_field":
            f.append("bad_currency_field")
        if r["value_conversion"] == "no_fx" and raw_val > 0:
            f.append("no_fx_for_local_value")
        if pd.notna(r["volume_total"]) and r["volume_total"] > 0 and not _unit_convertible(cat, hs, unit):
            f.append(f"unconvertible_unit({unit})")
        if rec > ABSURD_USD:
            f.append(f"reconstructed_${rec/1e9:.0f}B_absurd")
        if rep > ABSURD_USD:
            f.append(f"reported_${rep/1e9:.0f}B_absurd")
        # Reported value present and substantial, but diverges a lot from the
        # reconstruction → likely a parse/unit problem on one side.
        if pd.notna(ratio) and min(rep, rec) > MIN_FLAG_USD and (ratio < RATIO_LOW or ratio > RATIO_HIGH):
            f.append(f"reported/reconstructed={ratio:.2g}")
        # Reconstruction yields a substantial number but EITI disclosed no
        # value (or zero) — informational coverage gap, not necessarily a bug.
        elif rec > MIN_FLAG_USD and raw_val <= 0:
            f.append("value_not_disclosed")
        flags.append("; ".join(f))
    e["flags"] = flags

    out_cols = [
        "iso3", "year", "category", "hs_code", "commodity_name_canonical",
        "volume_total", "volume_unit", "n_volume_rows",
        "value_money_total", "value_currency", "value_conversion",
        "value_reported_usd", "revenue_reconstructed_usd",
        "ratio_reported_over_reconstructed", "flags", "source_files",
    ]
    for c in out_cols:
        if c not in e.columns:
            e[c] = np.nan
    out = e[out_cols].sort_values(["category", "iso3", "year", "hs_code"]).reset_index(drop=True)
    try:
        out.to_csv(OUT_CSV, index=False)
        print(f"\nWrote per-cell diagnostic ({len(out):,} rows) -> {OUT_CSV}")
    except PermissionError:
        alt = OUT_CSV.with_name("eiti_extraction_diagnostic_new.csv")
        out.to_csv(alt, index=False)
        print(f"\n[warn] {OUT_CSV.name} is locked (open elsewhere?) — wrote to "
              f"{alt} instead. Console summary follows regardless.")

    # ── Console summary ──
    print("\n=== Coverage ===")
    for cat in ("minerals", "oil_gas", "coal"):
        sub = e[e["category"] == cat]
        n = len(sub)
        n_val = int((pd.to_numeric(sub["value_money_total"], errors="coerce").fillna(0) > 0).sum())
        n_usd = int((sub["value_conversion"] == "usd_as_is").sum())
        n_fxok = int((sub["value_conversion"] == "fx_converted").sum())
        n_nofx = int((sub["value_conversion"] == "no_fx").sum())
        n_bad = int((sub["value_conversion"] == "bad_currency_field").sum())
        n_volonly = n - n_val
        print(f"  {cat:<9s}: {n:>4d} cells | value reported {n_val:>4d} "
              f"(USD {n_usd}, FX-converted {n_fxok}, no-FX {n_nofx}, bad-ccy {n_bad}) "
              f"| volume-only {n_volonly}")

    print("\n=== Reported-vs-reconstructed ratio (cells with both, > $1M) ===")
    rr = e[(e["ratio_reported_over_reconstructed"].notna())].copy()
    big = rr[
        np.maximum(rr["value_reported_usd"].fillna(0),
                   rr["revenue_reconstructed_usd"].fillna(0)) > MIN_FLAG_USD
    ]
    if len(big):
        q = big["ratio_reported_over_reconstructed"].quantile([.05, .25, .5, .75, .95])
        print(f"  {len(big)} comparable cells. ratio percentiles: "
              f"p5={q.loc[.05]:.2f}  p25={q.loc[.25]:.2f}  median={q.loc[.5]:.2f}  "
              f"p75={q.loc[.75]:.2f}  p95={q.loc[.95]:.2f}")
        n_in_band = int(((big["ratio_reported_over_reconstructed"] >= 0.5)
                         & (big["ratio_reported_over_reconstructed"] <= 2.0)).sum())
        print(f"  within [0.5, 2.0]: {n_in_band}/{len(big)} = {100*n_in_band/len(big):.0f}%")
    else:
        print("  (no comparable cells)")

    flagged = e[e["flags"].astype(str).str.len() > 0]
    print(f"\n=== {len(flagged)} flagged cells ===")
    if len(flagged):
        from collections import Counter
        ftypes = Counter()
        for fs in flagged["flags"]:
            for f in str(fs).split("; "):
                if f.startswith("reported/reconstructed="):
                    ftypes["reported_vs_reconstructed_off_by_>5x"] += 1
                elif f.startswith("unconvertible_unit("):
                    ftypes["unconvertible_volume_unit"] += 1
                elif f.startswith(("reconstructed_$", "reported_$")):
                    ftypes["absurd_magnitude_(unit_bug)"] += 1
                else:
                    ftypes[f] += 1
        for f, n in ftypes.most_common():
            print(f"  {f}: {n}")

        # Worst divergences (likely parse/unit bugs, not just missing-disclosure)
        bug_like = flagged[
            flagged["flags"].astype(str).str.contains(
                "reported/reconstructed=|unconvertible_unit|_absurd|bad_currency"
            )
        ].copy()
        print(f"\n  {len(bug_like)} of these look like parse/unit bugs "
              f"(the rest are 'value_not_disclosed' coverage gaps).")
        print("\n  worst 20 bug-like cells by |log(reported/reconstructed)|:")
        bug_like["_absl"] = bug_like["ratio_reported_over_reconstructed"].apply(
            lambda x: abs(np.log(x)) if pd.notna(x) and x > 0 else 0.0
        )
        bug_like = bug_like.sort_values("_absl", ascending=False)
        for _, r in bug_like.head(20).iterrows():
            rep = r["value_reported_usd"]
            rec = r["revenue_reconstructed_usd"]
            rep_s = f"${rep/1e6:,.1f}M" if pd.notna(rep) else "n/a"
            rec_s = f"${rec/1e6:,.1f}M" if pd.notna(rec) else "n/a"
            print(f"    {r['iso3']} {int(r['year'])} {r['category']:<8s} HS{r['hs_code']:<5s} "
                  f"{str(r['commodity_name_canonical'])[:16]:<16s} "
                  f"vol={r['volume_total']:>12,.1f} {str(r['volume_unit']):<8s} "
                  f"reported={rep_s:>13s} reconstructed={rec_s:>13s}  [{r['flags']}]")
    print(f"\nFull table: {OUT_CSV}")


if __name__ == "__main__":
    main()
