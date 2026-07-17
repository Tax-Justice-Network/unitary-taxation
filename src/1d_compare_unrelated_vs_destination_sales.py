# %% [markdown]
# Compare the existing unrelated-party-revenue (origin-based "sales") shares
# with the new destination-based-sales shares (CFB, ADS).
#
# Question: how strongly does each jurisdiction's share of GLOBAL unrelated-
# party revenue (where the selling MNE entity is located -> origin) correlate
# with its share of global destination-based sales (where the customer is)?
# This is the origin-vs-destination comparison discussed in WIFO (2026).
#
# Reads the disaggregated dataset (which now carries cfb_share / ads_share from
# 1b_destination_based_sales.py) and writes a partner-year comparison table, a
# correlation summary and scatter figures to output/destination_sales/.

# %%
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import *

TABLES_DIR, FIGURES_DIR = output_dirs("destination_sales")

# %%
# 1. Build the partner-year share of global unrelated-party revenue.
df = pd.read_csv(f"{data_final}/cbcr_main_disaggregated.csv")
df["unrelated_party_revenues"] = pd.to_numeric(
    df["unrelated_party_revenues"], errors="coerce"
)

# Unrelated-party revenue summed over all parent groups into each market
# jurisdiction (origin-based). Clip negatives to 0 before sharing.
upr = df.copy()
upr["upr"] = upr["unrelated_party_revenues"].clip(lower=0)
upr = upr.groupby(["iso_partner", "year"], as_index=False)["upr"].sum()
upr["upr_share"] = upr["upr"] / upr.groupby("year")["upr"].transform("sum")

# 2. Destination-based shares (one row per partner-year in the disaggregated file).
dest = df[["iso_partner", "year", "cfb_share", "ads_share"]].drop_duplicates(
    ["iso_partner", "year"]
)

# 3. Combine.
comp = upr.merge(dest, on=["iso_partner", "year"], how="inner")
comp = comp[["iso_partner", "year", "upr_share", "cfb_share", "ads_share"]]
comp.to_csv(f"{TABLES_DIR}/shares_unrelated_vs_destination.csv", index=False)
print(f"Comparison table: {len(comp)} partner-year rows, "
      f"{comp['iso_partner'].nunique()} jurisdictions.")

# %%
# 4. Correlations. For each pair compute, on the rows where both shares exist,
#    Pearson (levels), Spearman (rank) and Pearson on logs (positive rows only).
pairs = [
    ("upr_share", "cfb_share"),
    ("upr_share", "ads_share"),
    ("cfb_share", "ads_share"),
]

rows = []
# Pooled across all years, then per year.
scopes = [("pooled", comp)] + [(str(y), comp[comp["year"] == y]) for y in sorted(comp["year"].unique())]
for scope_name, d in scopes:
    for a, b in pairs:
        sub = d[[a, b]].dropna()
        pear = sub[a].corr(sub[b])
        spear = sub[a].corr(sub[b], method="spearman")
        pos = sub[(sub[a] > 0) & (sub[b] > 0)]
        log_pear = np.log(pos[a]).corr(np.log(pos[b])) if len(pos) > 2 else np.nan
        rows.append(
            {
                "scope": scope_name,
                "pair": f"{a} vs {b}",
                "n": len(sub),
                "pearson": round(pear, 3),
                "spearman": round(spear, 3),
                "log_pearson": round(log_pear, 3),
            }
        )

corr_summary = pd.DataFrame(rows)
corr_summary.to_csv(f"{TABLES_DIR}/correlation_summary.csv", index=False)

print("\nCorrelation summary (pooled across years):")
print(corr_summary[corr_summary["scope"] == "pooled"].to_string(index=False))

# %%
# 5. Scatter plots (log-log) for the pooled sample.
for a, b in [("upr_share", "cfb_share"), ("upr_share", "ads_share")]:
    pos = comp[(comp[a] > 0) & (comp[b] > 0)]
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(pos[a], pos[b], s=10, alpha=0.4)
    lo = min(pos[a].min(), pos[b].min())
    hi = max(pos[a].max(), pos[b].max())
    ax.plot([lo, hi], [lo, hi], color="grey", lw=0.8, ls="--", label="45-degree line")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(f"{a} (global share)")
    ax.set_ylabel(f"{b} (global share)")
    ax.set_title(f"{a} vs {b} (pooled, log-log)")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(f"{FIGURES_DIR}/scatter_{a}_vs_{b}.png", dpi=150)
    plt.close(fig)

# %%
# 6. Largest divergences in the latest year: where destination favours a
#    jurisdiction relative to origin (consumer markets) and vice versa
#    (production / conduit jurisdictions).
latest = comp[comp["year"] == comp["year"].max()].copy()
latest["cfb_minus_upr"] = latest["cfb_share"] - latest["upr_share"]
latest = latest.dropna(subset=["cfb_minus_upr"])

print(f"\nLatest year ({int(comp['year'].max())}) - CFB favours these markets "
      f"most vs unrelated-party revenue:")
print(latest.nlargest(10, "cfb_minus_upr")[
    ["iso_partner", "upr_share", "cfb_share", "cfb_minus_upr"]
].round(4).to_string(index=False))

print("\n... and unrelated-party revenue favours these most vs CFB:")
print(latest.nsmallest(10, "cfb_minus_upr")[
    ["iso_partner", "upr_share", "cfb_share", "cfb_minus_upr"]
].round(4).to_string(index=False))

print("\nWrote tables and figures to output/destination_sales/")
