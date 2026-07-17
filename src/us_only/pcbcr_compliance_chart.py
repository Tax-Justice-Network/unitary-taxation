# Fair Tax Foundation public-CbCR compliance gap — supporting chart.
#
# Standalone figure for the "US multinationals under-report public CbCR"
# argument (see docs/pcbcr_us_noncompliance.md). All numbers are taken directly
# from the Fair Tax Foundation analyses cited in that note; nothing here depends
# on the estimation pipeline. Run from anywhere:
#     python src/us_only/pcbcr_compliance_chart.py
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

# Windows stdout defaults to cp1252 and crashes when a printed path embeds the
# Arabic characters from the OneDrive project root. Use UTF-8 with replacement.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import output_dirs  # noqa: E402

_, FIG_DIR = output_dirs("us_multinationals")

# --- Data (Fair Tax Foundation) -------------------------------------------------
# Panel A: "good application" of the EU pCbCR directive by HQ country, latest
# FTF analysis (12 Jan 2026, 190 reports). Overall solid compliance = 56%.
HQ_LABELS = ["Japan", "UK", "Switzerland", "United States"]
HQ_GOOD = [72, 71, 43, 40]
OVERALL_GOOD = 56

# Panel B: US trend across the two FTF analyses (Jul 2025, 137 reports →
# Jan 2026, 190 reports): good application falls while the single-country
# ("Romania-only") dodge rises and overtakes it.
US_METRICS = ["Good application\nof directive", "Single-country\n(Romania-only) only"]
US_JUL2025 = [43, 36]
US_JAN2026 = [40, 48]

# --- Figure --------------------------------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(15, 6.5))

# Panel A — compliance gap by HQ country.
axA = axes[0]
colors = ["#1b7837", "#1b7837", "#d9a300", "#b2182b"]
bars = axA.bar(HQ_LABELS, HQ_GOOD, color=colors, edgecolor="white", width=0.65)
axA.axhline(OVERALL_GOOD, color="black", linestyle="--", linewidth=1)
axA.annotate(f"All filers: {OVERALL_GOOD}%", (3.35, OVERALL_GOOD + 1.5),
             ha="right", fontsize=9, fontstyle="italic")
for b, v in zip(bars, HQ_GOOD):
    axA.annotate(f"{v}%", (b.get_x() + b.get_width() / 2, v + 1.2),
                 ha="center", fontsize=11, fontweight="bold")
axA.set_ylim(0, 85)
axA.set_ylabel("Share of filers with 'good application' of the directive, %")
axA.set_title("US multinationals are the pCbCR laggards\n(EU public-CbCR directive, by HQ country)")
axA.grid(True, axis="y", linewidth=0.3, alpha=0.5)

# Panel B — US deterioration / crossover.
axB = axes[1]
x = np.arange(len(US_METRICS))
w = 0.38
b1 = axB.bar(x - w / 2, US_JUL2025, w, label="FTF Jul 2025 (137 reports)",
             color="#9ecae1", edgecolor="white")
b2 = axB.bar(x + w / 2, US_JAN2026, w, label="FTF Jan 2026 (190 reports)",
             color="#08519c", edgecolor="white")
for bars in (b1, b2):
    for b in bars:
        axB.annotate(f"{b.get_height():.0f}%",
                     (b.get_x() + b.get_width() / 2, b.get_height() + 1),
                     ha="center", fontsize=10, fontweight="bold")
axB.set_xticks(x)
axB.set_xticklabels(US_METRICS)
axB.set_ylim(0, 60)
axB.set_ylabel("Share of US-headquartered filers, %")
axB.set_title("US compliance is deteriorating:\nthe 'Romania-only' dodge now overtakes solid compliance")
axB.legend(loc="upper left", fontsize=9)
axB.grid(True, axis="y", linewidth=0.3, alpha=0.5)

fig.suptitle("Public country-by-country reporting: US multinationals under-report",
             fontsize=14, fontweight="bold")
fig.text(0.01, -0.02,
         "Source: Fair Tax Foundation analyses of EU public-CbCR filings (1 Jul 2025, 137 reports; 12 Jan 2026, "
         "190 reports). 'Good application' = solid implementation of the directive; 'single-country only' = filing "
         "only the Romania row. See docs/pcbcr_us_noncompliance.md. Details on the data and methods can be found "
         "in the accompanying methodology note.",
         ha="left", va="top", fontsize=9, wrap=True)

plt.tight_layout()
out = FIG_DIR / "pcbcr_us_compliance_gap.png"
plt.savefig(out, dpi=300, bbox_inches="tight")
plt.close()
print(f"Saved: {out}")
