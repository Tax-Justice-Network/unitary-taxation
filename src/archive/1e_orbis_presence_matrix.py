# %% [markdown]
# Orbis HQ -> subsidiary presence matrix, for the nexus restriction on
# destination-based sales (WIFO 2026, Information Box 3): a parent (source)
# country's market-j sales are only counted if the parent's MNEs have a
# subsidiary in j.
#
# Built from the Orbis ownership Links file. BvD IDs encode the country in
# their first two characters, so for each ownership link we read:
#   - subsidiary country  = first 2 chars of "Subsidiary BvD ID"  (the market j)
#   - HQ / source country = first 2 chars of "GUO 50" (ultimate owner >50%) (c)
# and count active links per (hq, market) pair. The 281 GB Links file is
# streamed line by line (never loaded into memory); only the small
# (hq, market) -> count dictionary is kept.
#
# Output: data/intermediate/orbis_hq_subsidiary_presence.csv
#   columns hq_iso3, market_iso3, n_links  (one row per ownership country pair).
# Consumed by 5_estimate_profit_shifting.py to build the nexus-restricted
# destination-based-sales factor.

# %%
import time

import pandas as pd
import pycountry

from config import *

LINKS_PATH = r"D:\data\Orbis_raw\Ownership histo June text\Links_current.txt"

# %%
# Stream the Links file. Columns (tab-separated): 0 Subsidiary BvD ID,
# 11 Active/archived, 13 GUO 50. Keep only active links with a non-empty GUO.
pairs = {}
n = 0
active = 0
t0 = time.time()
with open(LINKS_PATH, encoding="latin-1", errors="ignore") as f:
    header = f.readline()
    for line in f:
        n += 1
        p = line.rstrip("\n").split("\t", 14)
        if len(p) < 14:
            continue
        if p[11] != "active":
            continue
        sub = p[0][:2]
        guo = p[13][:2]
        if not guo.strip() or not sub.strip():
            continue
        active += 1
        key = (guo, sub)
        pairs[key] = pairs.get(key, 0) + 1
        if n % 50_000_000 == 0:
            dt = time.time() - t0
            print(f"  {n/1e6:.0f}M lines, {active/1e6:.1f}M active, "
                  f"{len(pairs)} pairs, {dt/60:.1f} min", flush=True)

print(f"\nDone: {n} lines, {active} active links, {len(pairs)} (hq, market) "
      f"ISO2 pairs, {(time.time()-t0)/60:.1f} min.")

# %%
# Map the two-letter codes to ISO3 (pycountry); drop pairs where either side is
# not a recognised country (supranational / unknown prefixes).
iso2_to_iso3 = {}
for code in {c for pair in pairs for c in pair}:
    obj = pycountry.countries.get(alpha_2=code)
    if obj is not None:
        iso2_to_iso3[code] = obj.alpha_3

rows = []
for (guo, sub), cnt in pairs.items():
    hq = iso2_to_iso3.get(guo)
    market = iso2_to_iso3.get(sub)
    if hq and market:
        rows.append({"hq_iso3": hq, "market_iso3": market, "n_links": cnt})

presence = pd.DataFrame(rows)
presence = presence.groupby(["hq_iso3", "market_iso3"], as_index=False)["n_links"].sum()
presence = presence.sort_values(["hq_iso3", "market_iso3"]).reset_index(drop=True)

out = f"{data_intermediate}/orbis_hq_subsidiary_presence.csv"
presence.to_csv(out, index=False)
print(f"Wrote {len(presence)} (hq_iso3, market_iso3) rows; "
      f"{presence['hq_iso3'].nunique()} HQ countries, "
      f"{presence['market_iso3'].nunique()} market countries.")
print("data/intermediate/orbis_hq_subsidiary_presence.csv")
