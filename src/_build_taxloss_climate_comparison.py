# Consolidated comparison: SOTJ profit-shifting tax losses (annual avg 2021/22)
# vs CPI Africa climate finance — adaptation flows, total flows, and TOTAL
# annual climate-finance need (from the CPI dashboard needs map).
import sys
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from config import output_dirs

TABLES, FIGURES = output_dirs("unitary_taxation_sotj_15_avg")

# Profit-shifting tax loss is read straight from the NORMAL misalignment run
# (disaggregated baseline, headline SOTJ spec: employees_payroll / average ETR /
# 15% threshold / loss_cit_gain_etr). No separate misalignment run is needed.
MISALIGN_FILE = ("../output/sotj2026/disaggregated_data/"
                 "country_estimates__employees_payroll__etrdef_average__"
                 "etrmax_0_15__loss_cit_gain_etr.csv")

name_to_iso = {
 'Algeria':'DZA','Angola':'AGO','Benin':'BEN','Botswana':'BWA','Burkina Faso':'BFA',
 'Burundi':'BDI','Cameroon':'CMR','Cape Verde':'CPV','Central African Republic':'CAF',
 'Chad':'TCD','Comoros':'COM','Republic of the Congo':'COG','Ivory Coast':'CIV',
 'Democratic Republic of the Congo':'COD','Djibouti':'DJI','Egypt':'EGY',
 'Equatorial Guinea':'GNQ','Eritrea':'ERI','Eswatini':'SWZ','Ethiopia':'ETH',
 'Gabon':'GAB','Gambia':'GMB','Ghana':'GHA','Guinea':'GIN','Guinea-Bissau':'GNB',
 'Kenya':'KEN','Lesotho':'LSO','Liberia':'LBR','Libya':'LBY','Madagascar':'MDG',
 'Malawi':'MWI','Mali':'MLI','Mauritania':'MRT','Mauritius':'MUS','Morocco':'MAR',
 'Mozambique':'MOZ','Namibia':'NAM','Niger':'NER','Nigeria':'NGA','Rwanda':'RWA',
 'Sao Tome and Principe':'STP','Senegal':'SEN','Seychelles':'SYC','Sierra Leone':'SLE',
 'Somalia':'SOM','South Africa':'ZAF','South Sudan':'SSD','Sudan':'SDN','Tanzania':'TZA',
 'Togo':'TGO','Tunisia':'TUN','Uganda':'UGA','Zambia':'ZMB','Zimbabwe':'ZWE'}
# CPI tables use a few alternative country spellings.
use_name_to_iso = {**name_to_iso, 'Congo': 'COG', "Cote d'Ivoire": 'CIV',
                   'Democratic Republic of Congo': 'COD'}
iso_to_name = {v: k for k, v in name_to_iso.items()}

# ---- tax loss: per-country annual average over 2021/22 from the normal run ---
loss = pd.read_csv(MISALIGN_FILE)
loss = loss[loss["year"].isin([2021, 2022])]
loss = (loss.groupby("iso_partner", as_index=False)["tax_revenue_loss"].mean()
            .rename(columns={"tax_revenue_loss": "tax_loss_musd"}))
loss = loss[loss["iso_partner"].isin(name_to_iso.values())].copy()
loss["country"] = loss["iso_partner"].map(iso_to_name)

# ---- climate finance flows by use (2021/22), from CPI Africa 2024 ----------
use = pd.read_csv("../data/raw/climate_finance/cpi_africa_country_use_2024.csv")
use = use[use["year"] == "2021/2022"].copy()
use["iso_partner"] = use["country"].map(use_name_to_iso)
assert use["iso_partner"].notna().all(), use[use.iso_partner.isna()].country.tolist()
use = use.rename(columns={"Adaptation": "adaptation_flow_musd",
                          "Dual Benefits": "dual_flow_musd"})
use["adapt_plus_dual_flow_musd"] = use["adaptation_flow_musd"] + use["dual_flow_musd"]

m = loss.merge(use[["iso_partner", "adaptation_flow_musd", "dual_flow_musd",
                    "adapt_plus_dual_flow_musd"]], on="iso_partner", how="left")

# ---- climate finance NEED (annualised), from the CPI dashboard needs map ----
needs = pd.read_csv("../data/raw/climate_finance/cpi_africa_needs_map.csv")
needs["iso_partner"] = needs["Country"].map(name_to_iso)
assert needs["iso_partner"].notna().all(), needs[needs.iso_partner.isna()].Country.tolist()
needs = needs.rename(columns={"Needs": "annual_total_need_musd",
                              "Annual average": "total_flow_annavg_musd",
                              "Pct need met": "cpi_pct_need_met"})

# ---- merge ----------------------------------------------------------------
d = m.merge(needs[["iso_partner", "annual_total_need_musd",
                   "total_flow_annavg_musd", "cpi_pct_need_met"]],
            on="iso_partner", how="left")
d = d[d["country"].notna()].copy()

d["loss_pct_adaptation"] = 100 * d["tax_loss_musd"] / d["adaptation_flow_musd"]
d["loss_pct_adapt_plus_dual"] = 100 * d["tax_loss_musd"] / d["adapt_plus_dual_flow_musd"]
d["loss_pct_total_need"] = 100 * d["tax_loss_musd"] / d["annual_total_need_musd"]

cols = ["country", "iso_partner", "tax_loss_musd", "adaptation_flow_musd",
        "dual_flow_musd", "adapt_plus_dual_flow_musd", "total_flow_annavg_musd",
        "annual_total_need_musd", "cpi_pct_need_met", "loss_pct_adaptation",
        "loss_pct_adapt_plus_dual", "loss_pct_total_need"]
out = d[cols].sort_values("loss_pct_adaptation", ascending=False).round(1)

# Africa total row
tot = {"country": "AFRICA (total)", "iso_partner": "—",
       "tax_loss_musd": d["tax_loss_musd"].sum(),
       "adaptation_flow_musd": d["adaptation_flow_musd"].sum(),
       "dual_flow_musd": d["dual_flow_musd"].sum(),
       "adapt_plus_dual_flow_musd": d["adapt_plus_dual_flow_musd"].sum(),
       "total_flow_annavg_musd": d["total_flow_annavg_musd"].sum(),
       "annual_total_need_musd": d["annual_total_need_musd"].sum()}
tot["cpi_pct_need_met"] = 100 * tot["total_flow_annavg_musd"] / tot["annual_total_need_musd"]
tot["loss_pct_adaptation"] = 100 * tot["tax_loss_musd"] / tot["adaptation_flow_musd"]
tot["loss_pct_adapt_plus_dual"] = 100 * tot["tax_loss_musd"] / tot["adapt_plus_dual_flow_musd"]
tot["loss_pct_total_need"] = 100 * tot["tax_loss_musd"] / tot["annual_total_need_musd"]
out = pd.concat([pd.DataFrame([tot]).round(1), out], ignore_index=True)
out.to_csv(TABLES / "africa_taxloss_vs_climate_finance_and_needs.csv", index=False)
pd.options.display.float_format = "{:,.1f}".format
print(out.to_string(index=False))

SEL = ['South Africa','Morocco','Egypt','Kenya','Nigeria','Ethiopia','Ghana',
       'Tanzania','Tunisia','Mozambique','Democratic Republic of the Congo',
       'Senegal','Malawi','Namibia']


def shortnames(s):
    return (s.replace('Democratic Republic of the Congo', 'DR Congo')
             .replace('Democratic Republic of Congo', 'DR Congo'))


# ===========================================================================
# FIGURE 1 (provided framing): tax loss as a share of TOTAL climate finance
# received (adaptation + mitigation). Normalized bars (each bar = that
# country's total finance provided = 100%).
# ===========================================================================
d["loss_pct_total_provided"] = 100 * d["tax_loss_musd"] / d["total_flow_annavg_musd"]
tot["loss_pct_total_provided"] = 100 * tot["tax_loss_musd"] / tot["total_flow_annavg_musd"]

f = d[d["country"].isin(SEL)].copy()
f["pct"] = f["loss_pct_total_provided"]
f = f.sort_values("pct", ascending=False)
rows = list(zip(f["country"], f["pct"])) + \
    [("AFRICA (all)", tot["loss_pct_total_provided"])]
labels = [shortnames(c) for c, _ in rows]
pcts = np.array([p for _, p in rows])

x = np.arange(len(rows))
covered = np.minimum(pcts, 100)
fig, ax = plt.subplots(figsize=(12, 6.2))
ax.bar(x, covered, 0.64, color="#c0392b",
       label="Share matched by recovering corporate-tax losses from profit shifting")
ax.bar(x, 100 - covered, 0.64, bottom=covered, color="#cdd6da",
       label="Remaining climate finance received")
ax.axvline(len(rows) - 1.5, color="0.6", lw=0.8, ls=":")
ax.set_ylim(0, 118)
ax.set_ylabel("% of total climate finance received\n(adaptation + mitigation, 2021/22 avg)")
ax.set_title("Profit-shifting tax losses vs the total climate finance African countries actually receive",
             fontsize=12.5)
ax.set_xticks(x); ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=9)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.26), frameon=False, fontsize=9)
ax.spines[["top", "right"]].set_visible(False)
for xi, p in enumerate(pcts):
    over = p > 100
    ax.text(xi, (100 if over else p) + 1.5, f"{p:.0f}%", ha="center", va="bottom",
            fontsize=8.5, fontweight="bold", color="#c0392b" if over else "#333")
    if over:
        ax.annotate("", xy=(xi, 116), xytext=(xi, 108),
                    arrowprops=dict(arrowstyle="-|>", color="#c0392b", lw=1.4))
plt.tight_layout()
fig.savefig(FIGURES / "fig_loss_vs_total_finance_provided.png", dpi=150, bbox_inches="tight")
fig.savefig(FIGURES / "fig_loss_vs_total_finance_provided.pdf", bbox_inches="tight")
plt.close(fig)

# ===========================================================================
# FIGURE 2 (context): the annual TOTAL climate-finance NEED, and how little
# of it is met — current flows vs the extra that recovered tax losses add.
# Each bar = that country's annual total need = 100%.
# ===========================================================================
# Select the largest-NEED countries (where need >> flows), so the
# "share of need" framing is well defined (flows never exceed need).
g = d.dropna(subset=["annual_total_need_musd"]).copy()
g = g.sort_values("annual_total_need_musd", ascending=False).head(12)
g["met_by_flows"] = g["cpi_pct_need_met"].clip(upper=100)
g["from_taxloss"] = (100 * g["tax_loss_musd"] / g["annual_total_need_musd"])
g = g.sort_values("annual_total_need_musd", ascending=False)
rows2 = list(zip(g["country"], g["met_by_flows"], g["from_taxloss"])) + [
    ("AFRICA (all)", 100 * tot["total_flow_annavg_musd"] / tot["annual_total_need_musd"],
     tot["loss_pct_total_need"])]
labels2 = [shortnames(c) for c, _, _ in rows2]
met = np.array([a for _, a, _ in rows2])
extra = np.array([b for _, _, b in rows2])
x = np.arange(len(rows2))
fig, ax = plt.subplots(figsize=(12, 6.2))
ax.bar(x, met, 0.64, color="#2980b9", label="Met by climate finance currently received")
ax.bar(x, extra, 0.64, bottom=met, color="#c0392b",
       label="Extra that recovered profit-shifting tax could fund")
ax.bar(x, np.clip(100 - met - extra, 0, None), 0.64, bottom=met + extra,
       color="#e8ebec", label="Remaining unmet need")
ax.axvline(len(rows2) - 1.5, color="0.6", lw=0.8, ls=":")
ax.set_ylim(0, 105)
ax.set_ylabel("% of annual TOTAL climate-finance need\n(adaptation + mitigation; need annualised by CPI)")
ax.set_title("Against total climate-finance NEEDS, both current flows and recovered\n"
             "profit-shifting tax remain a small share", fontsize=12.5)
ax.set_xticks(x); ax.set_xticklabels(labels2, rotation=40, ha="right", fontsize=9)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.26), frameon=False, fontsize=9)
ax.spines[["top", "right"]].set_visible(False)
for xi, (a, b) in enumerate(zip(met, extra)):
    ax.text(xi, a + b + 1.0, f"{b:.1f}%", ha="center", va="bottom", fontsize=7.5,
            color="#c0392b")
plt.tight_layout()
fig.savefig(FIGURES / "fig_loss_and_flows_vs_total_need.png", dpi=150, bbox_inches="tight")
fig.savefig(FIGURES / "fig_loss_and_flows_vs_total_need.pdf", bbox_inches="tight")
plt.close(fig)

print("\nsaved figures:")
print("  fig_loss_vs_adaptation_flows.png   (main: loss vs adaptation flows)")
print("  fig_loss_and_flows_vs_total_need.png  (context: vs total annual need)")
print("Africa: loss = {:.1f}% of adaptation, {:.1f}% of adapt+dual, {:.2f}% of total need".format(
    tot["loss_pct_adaptation"], tot["loss_pct_adapt_plus_dual"], tot["loss_pct_total_need"]))
