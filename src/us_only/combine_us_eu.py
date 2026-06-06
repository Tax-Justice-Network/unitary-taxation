# Combined US-vs-EU multinationals comparison.
#
# Reads the per-group country-estimates produced by
# estimate_us_multinationals.py (run once with HOME_GROUP=USA and once with
# HOME_GROUP=EU27) and builds combined figures comparing how much profit US- and
# EU-headquartered MNEs shift, in absolute terms and as a share of their total
# profit. "Profit shifted" = total positive misalignment (profit booked away
# from where it is earned), INCLUDING profit that ends up in EU havens.
#
# Run AFTER both group runs:
#     HOME_GROUP=USA  python src/us_only/estimate_us_multinationals.py
#     HOME_GROUP=EU27 python src/us_only/estimate_us_multinationals.py
#     python src/us_only/combine_us_eu.py
import os
import sys
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import output_dirs, output_root  # noqa: E402

# Country-estimate file (positive_misalignment + reported_profit are
# rate-independent; loss_cit_gain_etr is just a concrete spec that exists).
_STUB = "country_estimates__employees_payroll__etrdef_average__etrmax_inf__loss_cit_gain_etr.csv"
GROUPS = {"US": "us_multinationals", "EU": "eu_multinationals"}
COLORS = {"US": "#b2182b", "EU": "#2166ac"}

SHARED_OUTPUT_ROOT = Path(os.environ.get(
    "SHARED_OUTPUT_ROOT",
    r"C:\Users\aliso\Tax Justice Network Ltd\TJN - Shared Documents"
    r"\Research team\Projects one-off\2605 The quiet tax war\3_output",
))


def _longpath(p):
    s = os.fspath(p)
    if sys.platform == "win32" and len(s) > 240 and not s.startswith("\\\\?\\"):
        s = "\\\\?\\" + os.path.abspath(s)
    return s


def load_group(topic):
    path = Path(output_root) / topic / "tables" / "disaggregated" / _STUB
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run estimate_us_multinationals.py for this group first.")
    df = pd.read_csv(_longpath(path))
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["positive_misalignment"] = pd.to_numeric(df["positive_misalignment"], errors="coerce")
    df["reported_profit"] = pd.to_numeric(df["reported_profit"], errors="coerce")
    g = df.groupby("year", as_index=False).agg(
        shifted_bn=("positive_misalignment", lambda x: x.clip(lower=0).sum() / 1000.0),
        total_profit_bn=("reported_profit", lambda x: x.clip(lower=0).sum() / 1000.0),
    )
    g["shifted_pct_of_profit"] = np.where(
        g["total_profit_bn"] > 0, 100.0 * g["shifted_bn"] / g["total_profit_bn"], np.nan)
    return g


def main():
    data = {label: load_group(topic) for label, topic in GROUPS.items()}
    years = sorted(set().union(*[set(g["year"].dropna().astype(int)) for g in data.values()]))

    # Tidy combined CSV.
    parts = []
    for label, g in data.items():
        gg = g.copy()
        gg.insert(0, "mne_group", label)
        parts.append(gg)
    combined = pd.concat(parts, ignore_index=True)
    tables_dir, figures_dir = output_dirs("combined_us_eu")
    combined.to_csv(tables_dir / "combined_profit_shifted_us_eu.csv", index=False)

    # Two-panel figure: absolute shifted (left) and share of profit (right).
    fig, axes = plt.subplots(1, 2, figsize=(16, 6.5))
    x = np.arange(len(years))
    w = 0.38
    for i, (label, g) in enumerate(data.items()):
        gi = g.set_index("year").reindex(years)
        axes[0].bar(x + (i - 0.5) * w, gi["shifted_bn"].to_numpy(), w,
                    label=f"{label} MNEs", color=COLORS[label], edgecolor="white")
        axes[1].bar(x + (i - 0.5) * w, gi["shifted_pct_of_profit"].to_numpy(), w,
                    label=f"{label} MNEs", color=COLORS[label], edgecolor="white")

    axes[0].set_title("Total profit shifted (booked away from where earned)\nincl. profit ending in EU havens")
    axes[0].set_ylabel("Profit shifted, USD bn")
    axes[1].set_title("Profit shifted as a share of total profit")
    axes[1].set_ylabel("Profit shifted, % of total reported profit")
    for ax in axes:
        ax.set_xticks(x)
        ax.set_xticklabels(years)
        ax.set_xlabel("Year")
        ax.grid(True, axis="y", linewidth=0.3, alpha=0.5)
        ax.legend()

    fig.suptitle(f"US vs EU multinationals: profit shifting, {min(years)}–{max(years)}",
                 fontsize=14, fontweight="bold")
    fig.text(0.01, -0.02,
             "Note: 'Profit shifted' = total positive misalignment — profit booked beyond what an employees+payroll "
             "(50/50) unitary split implies, i.e. shifted away from where it is earned (including profit that ends up "
             "in EU havens). Share = shifted ÷ total positive reported profit of the group. Baseline disaggregated "
             "CbCR. US = US-parented MNEs; EU = EU-27-parented MNEs.",
             ha="left", va="top", fontsize=9, wrap=True)
    plt.tight_layout()
    out = figures_dir / f"combined_profit_shifted_us_eu_{min(years)}_{max(years)}.png"
    plt.savefig(_longpath(out), dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")
    for label, g in data.items():
        first, last = g.iloc[0], g.iloc[-1]
        print(f"  {label}: shifted {first['shifted_bn']:,.0f}->{last['shifted_bn']:,.0f} bn | "
              f"share {first['shifted_pct_of_profit']:.0f}%->{last['shifted_pct_of_profit']:.0f}%")

    # Mirror to the shared folder (flat, combined_ prefix, 1_tables / 2_figures).
    if SHARED_OUTPUT_ROOT.exists():
        base = tables_dir.parent
        n = 0
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            rel = list(p.relative_to(base).parts)
            rel[0] = {"figures": "2_figures", "tables": "1_tables"}.get(rel[0], rel[0])
            rel[-1] = rel[-1] if rel[-1].startswith("combined_") else "combined_" + rel[-1]
            target = SHARED_OUTPUT_ROOT.joinpath(*rel)
            os.makedirs(_longpath(str(target.parent)), exist_ok=True)
            shutil.copy2(_longpath(str(p)), _longpath(str(target)))
            n += 1
        print(f"[mirror] copied {n} combined files to {SHARED_OUTPUT_ROOT}")


main()
