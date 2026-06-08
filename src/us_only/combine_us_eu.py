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

# Figure house style — The Left palette (see 4_docs/figure_style_guide.md).
PALETTE = {"red": "#e42728", "navy": "#2c324c", "teal": "#28a186",
           "slate": "#5c7090", "amber": "#c29a11", "ink": "#1c1c1c", "grid": "#d1dae5"}
plt.rcParams.update({
    "grid.color": PALETTE["grid"], "grid.linewidth": 0.7,
    "axes.edgecolor": PALETTE["ink"], "axes.labelcolor": PALETTE["ink"],
    "text.color": PALETTE["ink"], "xtick.color": PALETTE["ink"], "ytick.color": PALETTE["ink"],
})
TCJA_GREY = "#9c9c9c"


def add_tcja_marker(ax, xpos=2017, label=True):
    """Vertical dashed 2017 'Tax Cuts and Jobs Act' marker (house style)."""
    ax.axvline(xpos, color=TCJA_GREY, linestyle="--", linewidth=1.2, zorder=0)
    if label:
        ax.annotate("Tax Cuts and Jobs Act", xy=(xpos, 0.99),
                    xycoords=("data", "axes fraction"), xytext=(4, 0),
                    textcoords="offset points", ha="left", va="top",
                    fontsize=8, color=TCJA_GREY)


SUBTITLE_BLUE = "#2e7d9e"


def house_style(ax, title, subtitle=None, title_size=15, sub_size=11):
    """Left-aligned bold title + teal-blue subtitle, top/right spines removed
    (see 4_docs/figure_style_guide.md §7)."""
    ax.spines[["top", "right"]].set_visible(False)
    ax.text(0.0, 1.13 if subtitle else 1.04, title, transform=ax.transAxes,
            fontsize=title_size, fontweight="bold", color=PALETTE["ink"], va="bottom", ha="left")
    if subtitle:
        ax.text(0.0, 1.03, subtitle, transform=ax.transAxes, fontsize=sub_size,
                color=SUBTITLE_BLUE, va="bottom", ha="left")


def fig_title(fig, axes, title, subtitle=None):
    """House-style title for a multi-panel figure: left-aligned bold title (and
    optional subtitle) at the top-left, top/right spines removed on every panel."""
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.01, 1.0, title, fontsize=15, fontweight="bold", color=PALETTE["ink"], va="bottom", ha="left")
    if subtitle:
        fig.text(0.01, 0.965, subtitle, fontsize=11, color=SUBTITLE_BLUE, va="bottom", ha="left")

# Apportionment formula for the figures. Must match the FIG_FORMULA the estimate
# script was run with: 'ccctb' (default) reads the CCCTB topics; SOTJ
# (employees_payroll) reads the `_sotj` topics and tags the combined output to
# match, so the two formula sets sit side by side.
FIG_FORMULA = os.environ.get("FIG_FORMULA", "ccctb").strip()
_FIG_FORMULA_META = {
    "ccctb": ("CCCTB formula (1/3 sales, 1/3 assets, 1/6 employees, 1/6 payroll)", "CCCTB", ""),
    "employees_payroll": ("SOTJ formula (50% employees, 50% payroll)", "SOTJ", "_sotj"),
}
if FIG_FORMULA not in _FIG_FORMULA_META:
    raise ValueError(f"FIG_FORMULA must be one of {list(_FIG_FORMULA_META)}; got {FIG_FORMULA!r}")
FIG_FORMULA_DESC, FIG_FORMULA_LABEL, _FIG_FORMULA_TAG = _FIG_FORMULA_META[FIG_FORMULA]

# Country-estimate file (positive_misalignment + reported_profit are
# rate-independent; loss_cit_gain_etr is just a concrete spec that exists). The
# etrmax tag in the filename matches the active ETR_MAX (inf or e.g. 0_15).
_etrmax_fn = os.environ.get("ETR_MAX", "inf").strip().lower()
_etrmax_fn = "inf" if _etrmax_fn in ("inf", "infinity", "none", "") else _etrmax_fn.replace(".", "_")
_STUB = f"country_estimates__{FIG_FORMULA}__etrdef_average__etrmax_{_etrmax_fn}__loss_cit_gain_etr.csv"
# ETR-max config: combine the matching per-group topics (inf -> untagged;
# 0.15 -> *_etr15) so `ETR_MAX=0.15 python combine_us_eu.py` builds the 0.15
# combined figures alongside the inf ones. The _sotj formula tag is appended
# after the ETR tag, matching the estimate script's topic naming.
_etr_env = os.environ.get("ETR_MAX", "inf").strip().lower()
ETR_TAG = "inf" if _etr_env in ("inf", "infinity", "none", "") else f"etr{int(round(float(_etr_env) * 100))}"
_TS = ("" if ETR_TAG == "inf" else f"_{ETR_TAG}") + _FIG_FORMULA_TAG
GROUPS = {"US": "us_multinationals" + _TS, "EU": "eu_multinationals" + _TS,
          "All": "all_multinationals" + _TS}
COLORS = {"US": "#e42728", "EU": "#2c324c", "All": "#5c7090"}

# German municipal (Kommunen) core-budget debt, Destatis end-2023 (Kernhaushalte
# der Gemeinden/Gv.): EUR 154.6bn. USD_PER_EUR converts the USD-denominated
# modelled loss to EUR for the contrast (period-average, for scale only).
KOMMUNEN_DEBT_EUR_BN = 154.6      # Destatis end-2023, core municipal budgets
# Municipal investment backlog (Investitionsrückstand), KfW Kommunalpanel:
DAYCARE_BACKLOG_EUR_BN = 10.5     # childcare/Kitas (2021; ~11.2bn in 2024)
SCHOOL_BACKLOG_EUR_BN = 67.8      # school buildings (2025 panel)
USD_PER_EUR = 1.10

EU27 = {
    "AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA",
    "DEU", "GRC", "HUN", "IRL", "ITA", "LVA", "LTU", "LUX", "MLT", "NLD",
    "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE",
}

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
    for c in ["positive_misalignment", "negative_misalignment", "reported_profit"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # Profit shifted OUT OF the EU = profit generated in EU-27 partner countries
    # but booked elsewhere (their negative misalignment, stored positive).
    df["_eu_out"] = np.where(df["iso_partner"].isin(EU27),
                             df["negative_misalignment"].clip(lower=0), 0.0)
    g = df.groupby("year", as_index=False).agg(
        shifted_bn=("positive_misalignment", lambda x: x.clip(lower=0).sum() / 1000.0),
        eu_out_bn=("_eu_out", lambda x: x.sum() / 1000.0),
        total_profit_bn=("reported_profit", lambda x: x.clip(lower=0).sum() / 1000.0),
    )
    g["shifted_pct_of_profit"] = np.where(
        g["total_profit_bn"] > 0, 100.0 * g["shifted_bn"] / g["total_profit_bn"], np.nan)
    g["eu_out_pct_of_profit"] = np.where(
        g["total_profit_bn"] > 0, 100.0 * g["eu_out_bn"] / g["total_profit_bn"], np.nan)
    return g


def main():
    data = {}
    for label, topic in GROUPS.items():
        try:
            data[label] = load_group(topic)
        except FileNotFoundError as e:
            print(f"[skip] {label} group not available: {e}")
    if not data:
        raise SystemExit("No groups available — run estimate_us_multinationals.py first.")
    years = sorted(set().union(*[set(g["year"].dropna().astype(int)) for g in data.values()]))

    # Tidy combined CSV.
    parts = []
    for label, g in data.items():
        gg = g.copy()
        gg.insert(0, "mne_group", label)
        parts.append(gg)
    combined = pd.concat(parts, ignore_index=True)
    tables_dir, figures_dir = output_dirs("combined_us_eu" + _TS)
    combined.to_csv(tables_dir / "combined_profit_shifted_us_eu.csv", index=False)

    # Two-panel comparison (absolute left, share of profit right), reused for
    # ALL activity and for profit shifted OUT OF the EU only.
    _NOTE_BASE = (f"Baseline disaggregated CbCR, {FIG_FORMULA_DESC}. "
                  "Share = ÷ total positive reported profit of the group. "
                  "US = US-parented MNEs; EU = EU-27-parented MNEs.")

    def _two_panel(metric, pct, title_abs, suptitle, note, fname):
        fig, axes = plt.subplots(1, 2, figsize=(16, 6.5))
        x = np.arange(len(years))
        ng = len(data)
        w = 0.8 / ng
        for i, (label, g) in enumerate(data.items()):
            gi = g.set_index("year").reindex(years)
            off = (i - (ng - 1) / 2) * w
            axes[0].bar(x + off, gi[metric].to_numpy(), w,
                        label=f"{label} MNEs", color=COLORS[label], edgecolor="white")
            axes[1].bar(x + off, gi[pct].to_numpy(), w,
                        label=f"{label} MNEs", color=COLORS[label], edgecolor="white")
        axes[0].set_title(title_abs)
        axes[0].set_ylabel("Profit shifted, USD bn")
        axes[1].set_title("As a share of total profit")
        axes[1].set_ylabel("Profit shifted, % of total reported profit")
        for ax in axes:
            ax.set_xticks(x)
            ax.set_xticklabels(years)
            ax.set_xlabel("Year")
            ax.grid(True, axis="y", linewidth=0.3, alpha=0.5)
            ax.legend(frameon=False)
            ax.spines[["top", "right"]].set_visible(False)
        fig.suptitle(suptitle, fontsize=15, fontweight="bold", x=0.012, ha="left", color=PALETTE["ink"])
        fig.text(0.01, -0.02, note, ha="left", va="top", fontsize=9, wrap=True)
        plt.tight_layout()
        out = figures_dir / f"{fname}_{min(years)}_{max(years)}.png"
        plt.savefig(_longpath(out), dpi=300, bbox_inches="tight")
        plt.close()
        print(f"Saved: {out}")
        return out

    _two_panel(
        "shifted_bn", "shifted_pct_of_profit",
        "Total profit shifted (booked away from where earned)\nALL activity, any destination (incl. EU havens)",
        f"US vs EU multinationals: total profit shifting (all activity), {min(years)}–{max(years)}",
        f"Note: 'Profit shifted' = total positive misalignment (profit booked beyond the {FIG_FORMULA_LABEL}-implied split), to "
        "any destination. " + _NOTE_BASE,
        "combined_profit_shifted_us_eu")
    _two_panel(
        "eu_out_bn", "eu_out_pct_of_profit",
        "Profit shifted OUT OF the EU\n(generated in EU-27 countries, booked elsewhere)",
        f"US vs EU multinationals: profit shifted out of the EU, {min(years)}–{max(years)}",
        f"Note: 'Shifted out of the EU' = sum over EU-27 partner countries of profit a {FIG_FORMULA_LABEL} split would assign them "
        "but that is booked elsewhere (their negative misalignment). " + _NOTE_BASE,
        "combined_profit_shifted_out_of_eu_us_eu")
    for label, g in data.items():
        print(f"  {label}: all-shifted {g['shifted_bn'].iloc[0]:,.0f}->{g['shifted_bn'].iloc[-1]:,.0f}bn | "
              f"out-of-EU {g['eu_out_bn'].iloc[0]:,.0f}->{g['eu_out_bn'].iloc[-1]:,.0f}bn")

    # ---- Combined home-share: real activity vs profit kept at home, US vs EU ----
    hs = {}
    for label, topic in GROUPS.items():
        hp = Path(output_root) / topic / "tables" / "home_share_activity_vs_profit.csv"
        if hp.exists():
            hs[label] = pd.read_csv(_longpath(hp)).sort_values("year")
    if hs:
        fig, axes = plt.subplots(1, 2, figsize=(16, 6.5))
        for label, h in hs.items():
            axes[0].plot(h["year"], h["Employees"], marker="o", linewidth=2.6,
                         color=COLORS[label], label=f"{label} MNEs")
            axes[1].plot(h["year"], h["Reported profit"], marker="o", linewidth=2.6,
                         color=COLORS[label], label=f"{label} MNEs")
        axes[0].set_title("Share of employees kept in the home region")
        axes[0].set_ylabel("Home share of worldwide employees, %")
        axes[1].set_title("Share of profit booked in the home region")
        axes[1].set_ylabel("Home share of worldwide reported profit, %")
        for ax in axes:
            ax.set_ylim(0, 100)
            ax.set_xlabel("Year")
            add_tcja_marker(ax)
            ax.grid(True, axis="y", linewidth=0.3, alpha=0.5)
            ax.legend(frameon=False)
            ax.spines[["top", "right"]].set_visible(False)
        fig.suptitle("US vs EU multinationals: where activity sits vs where profit is booked, "
                     f"{min(years)}–{max(years)}", fontsize=15, fontweight="bold",
                     x=0.012, ha="left", color=PALETTE["ink"])
        fig.text(0.01, -0.02,
                 "Note: Home region = the group's parent jurisdiction(s) (USA; EU-27). Left = share of worldwide "
                 "employees located at home (real activity); right = share of worldwide profit booked at home. "
                 "Baseline disaggregated CbCR.",
                 ha="left", va="top", fontsize=9, wrap=True)
        plt.tight_layout()
        out_hs = figures_dir / f"combined_home_share_us_eu_{min(years)}_{max(years)}.png"
        plt.savefig(_longpath(out_hs), dpi=300, bbox_inches="tight")
        plt.close()
        print(f"Saved: {out_hs}")

    # ---- Germany Kommunen: cumulative tax lost to profit shifting vs debt ----
    muni_eur = {}
    for label, topic in GROUPS.items():
        gp = Path(output_root) / topic / "tables" / "germany_tax_loss_by_level.csv"
        if gp.exists():
            d = pd.read_csv(_longpath(gp))
            row = d[d["level"].astype(str).str.contains("Kommunen", na=False)]
            if not row.empty:
                muni_eur[label] = float(row["tax_loss_bn_total"].iloc[0]) / USD_PER_EUR
    if muni_eur:
        bars = {}
        if "US" in muni_eur:
            bars["Lost to US MNEs"] = muni_eur["US"]
        if "EU" in muni_eur:
            bars["Lost to EU MNEs"] = muni_eur["EU"]
        if "All" in muni_eur:
            bars["Lost to ALL MNEs"] = muni_eur["All"]
        elif "US" in muni_eur and "EU" in muni_eur:
            bars["Lost to US+EU MNEs"] = muni_eur["US"] + muni_eur["EU"]
        labels, vals = list(bars.keys()), list(bars.values())
        colors = ["#e42728", "#2c324c", "#5c7090"][:len(vals)]
        fig, ax = plt.subplots(figsize=(11, 6.5))
        b = ax.bar(labels, vals, color=colors, edgecolor="white", width=0.6, zorder=3)
        for bar, v in zip(b, vals):
            ax.annotate(f"€{v:,.0f}bn\n({v / DAYCARE_BACKLOG_EUR_BN:.1f}× daycare backlog)",
                        (bar.get_x() + bar.get_width() / 2, v), textcoords="offset points",
                        xytext=(0, 3), ha="center", fontsize=9, fontweight="bold")
        # Daycare is a municipal task; schools are a Länder matter (shown in a
        # separate Länder-vs-school figure in the estimate script), so only the
        # daycare backlog is referenced here.
        for yv, lab, col in [
            (DAYCARE_BACKLOG_EUR_BN, f"Daycare/Kita investment backlog (€{DAYCARE_BACKLOG_EUR_BN:.1f}bn, KfW)", "#28a186"),
        ]:
            ax.axhline(yv, color=col, linestyle="--", linewidth=1.4, zorder=2)
            ax.annotate(lab, (len(labels) - 0.5, yv), xytext=(0, 2), textcoords="offset points",
                        ha="right", va="bottom", fontsize=8, color=col)
        ax.set_ylabel("EUR bn")
        ax.set_ylim(0, max(DAYCARE_BACKLOG_EUR_BN * 1.6, max(vals) * 1.3))
        house_style(ax, "What German municipalities lose to profit shifting",
                    f"Municipal (Kommunen) tax lost vs the daycare investment backlog, "
                    f"cumulative {min(years)}–{max(years)}")
        ax.grid(True, axis="y", linewidth=0.3, alpha=0.5)
        _basis = ("all misalignment (ETR max = ∞)" if ETR_TAG == "inf"
                  else f"haven-only (ETR max = {float(_etr_env):.0%})")
        fig.text(0.01, -0.02,
                 f"Note: Bars = municipal (Kommunen) share of Germany's modelled corporate-tax loss to US/EU MNEs, "
                 f"cumulative {min(years)}–{max(years)}, USD→EUR at {USD_PER_EUR}; basis: {_basis}. The ≈€"
                 f"{muni_eur.get('US', 0):.0f}bn lost to US MNEs alone ≈ the entire national daycare (Kita) investment "
                 f"backlog (€{DAYCARE_BACKLOG_EUR_BN:.1f}bn, KfW Kommunalpanel). For context, total municipal debt is "
                 f"€{KOMMUNEN_DEBT_EUR_BN:.0f}bn (Destatis end-2023). Baseline disaggregated CbCR.",
                 ha="left", va="top", fontsize=9, wrap=True)
        plt.tight_layout()
        out_k = figures_dir / f"germany_kommunen_loss_vs_needs_{min(years)}_{max(years)}.png"
        plt.savefig(_longpath(out_k), dpi=300, bbox_inches="tight")
        plt.close()
        print(f"Saved: {out_k} | "
              + ", ".join(f"{k}: €{v:,.1f}bn ({v / DAYCARE_BACKLOG_EUR_BN:.1f}x daycare backlog)"
                          for k, v in muni_eur.items()))

        # Focused figure: ALL-MNE (any HQ) Kommunen loss vs TOTAL municipal debt.
        if "All" in muni_eur:
            all_loss = muni_eur["All"]
            fig, ax = plt.subplots(figsize=(8, 6.5))
            vv = [KOMMUNEN_DEBT_EUR_BN, all_loss]
            b = ax.bar(["Total Kommunen debt\n(Destatis end-2023)", "Lost to ALL multinationals\n(2016–2022)"],
                       vv, color=["#5c7090", "#e42728"], edgecolor="white", width=0.6)
            for bar, v in zip(b, vv):
                pct = "" if v == KOMMUNEN_DEBT_EUR_BN else f"\n({100 * v / KOMMUNEN_DEBT_EUR_BN:.0f}% of debt)"
                ax.annotate(f"€{v:,.0f}bn{pct}", (bar.get_x() + bar.get_width() / 2, v),
                            textcoords="offset points", xytext=(0, 3), ha="center",
                            fontsize=10, fontweight="bold")
            ax.set_ylabel("EUR bn")
            house_style(ax, "German municipalities' loss to all multinationals vs their debt",
                        f"Municipal (Kommunen) tax lost to ALL multinationals vs total municipal debt, "
                        f"cumulative {min(years)}–{max(years)}")
            ax.grid(True, axis="y", linewidth=0.3, alpha=0.5)
            fig.text(0.01, -0.02,
                     f"Note: Municipal (Kommunen) share of Germany's modelled corporate-tax loss to ALL "
                     f"multinationals (any HQ), cumulative {min(years)}–{max(years)}, USD→EUR at {USD_PER_EUR}; "
                     f"basis: {_basis}. Total municipal debt = Destatis core municipal budgets (Kernhaushalte), "
                     "end-2023. Baseline disaggregated CbCR.",
                     ha="left", va="top", fontsize=9, wrap=True)
            plt.tight_layout()
            out_kd = figures_dir / f"germany_kommunen_all_loss_vs_debt_{min(years)}_{max(years)}.png"
            plt.savefig(_longpath(out_kd), dpi=300, bbox_inches="tight")
            plt.close()
            print(f"Saved: {out_kd} | all-MNE €{all_loss:,.1f}bn = "
                  f"{100 * all_loss / KOMMUNEN_DEBT_EUR_BN:.0f}% of total municipal debt")

    # Mirror to the shared folder (subfolder per topic, 1_tables / 2_figures).
    if SHARED_OUTPUT_ROOT.exists():
        base = tables_dir.parent
        n = 0
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            rel = list(p.relative_to(base).parts)
            top = {"figures": "2_figures", "tables": "1_tables"}.get(rel[0], rel[0])
            target = SHARED_OUTPUT_ROOT.joinpath(top, "combined_us_eu" + _TS, *rel[1:])
            os.makedirs(_longpath(str(target.parent)), exist_ok=True)
            shutil.copy2(_longpath(str(p)), _longpath(str(target)))
            n += 1
        print(f"[mirror] copied {n} combined files to {SHARED_OUTPUT_ROOT}")


main()
