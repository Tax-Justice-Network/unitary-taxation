# %% [markdown]
# Fetch WB Data360-hosted sources for the gravity feature set:
#   - IMF CDIS  (bilateral direct investment positions)  -> FDI inward/outward
#   - IMF CPIS  (bilateral portfolio investment)         -> portfolio in/out
#   - WB  WGI   (Worldwide Governance Indicators, 6 dims) -> governance PCA
#
# Pull-and-cache to data/raw/gravity/. Data360 paginates at 1000 rows, so we
# page with `skip` until `count`. Bilateral counterpart is in COMP_BREAKDOWN_1
# (IMF IFS numeric codes for CDIS/CPIS); REF_AREA is ISO3. IFS->ISO3 mapping is
# resolved later in build_features.

# %%
import json
import os
import ssl
import time
import urllib.request

import pandas as pd

RAW_GRAVITY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "raw", "gravity",
)
os.makedirs(RAW_GRAVITY, exist_ok=True)
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
BASE = "https://data360api.worldbank.org/data360"
YEARS = list(range(2014, 2023))


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=120, context=_CTX).read())


def fetch_indicator_year(database_id, indicator, year, keep):
    """Page through one (indicator, year); return list of dicts with `keep` cols."""
    rows = []
    skip = 0
    while True:
        url = (f"{BASE}/data?DATABASE_ID={database_id}&INDICATOR={indicator}"
               f"&TIME_PERIOD={year}&skip={skip}")
        d = _get(url)
        vals = d.get("value", [])
        for r in vals:
            rows.append({k: r.get(k) for k in keep})
        count = d.get("count", 0)
        skip += len(vals)
        if not vals or skip >= count:
            break
        time.sleep(0.2)
    return rows


def fetch_dataset(database_id, indicator, out_name, bilateral):
    out = os.path.join(RAW_GRAVITY, out_name)
    if os.path.exists(out):
        print(f"  cached  {out_name} ({len(pd.read_csv(out))} rows)")
        return
    keep = (["REF_AREA", "COMP_BREAKDOWN_1", "TIME_PERIOD", "OBS_VALUE"] if bilateral
            else ["REF_AREA", "TIME_PERIOD", "OBS_VALUE", "INDICATOR"])
    allrows = []
    for y in YEARS:
        try:
            r = fetch_indicator_year(database_id, indicator, y, keep)
            allrows.extend(r)
            print(f"    {indicator} {y}: {len(r)} rows", flush=True)
        except Exception as e:
            print(f"    {indicator} {y}: FAIL {str(e)[:60]}", flush=True)
    pd.DataFrame(allrows).to_csv(out, index=False)
    print(f"  wrote   {out_name} ({len(allrows)} rows)")


# %%
# WGI: 6 unilateral governance dimensions.
WGI = ["GOV_WGI_GE", "GOV_WGI_RL", "GOV_WGI_RQ", "GOV_WGI_CC", "GOV_WGI_PV", "GOV_WGI_VA"]
for ind in WGI:
    fetch_dataset("WB_WGI", ind, f"wgi_{ind}.csv", bilateral=False)

# CDIS: inward total direct-investment positions, bilateral. outward derived by
# mirror in build_features (A inward from B == B outward to A).
fetch_dataset("IMF_CDIS", "IMF_CDIS_IWDA_BP6", "imf_cdis_inward.csv", bilateral=True)

# CPIS: total portfolio investment assets, bilateral. Pick the total-instrument
# indicator from the dataset's list (fallback to a known code).
try:
    cpis = _get(f"{BASE}/indicators?datasetId=IMF_CPIS")
    totals = [c for c in cpis if c.endswith("_T_BP6") and "_A_" in c]
    cpis_ind = totals[0] if totals else "IMF_CPIS_I_A_T_T_T_BP6"
except Exception:
    cpis_ind = "IMF_CPIS_I_A_T_T_T_BP6"
print(f"  CPIS indicator chosen: {cpis_ind}")
fetch_dataset("IMF_CPIS", cpis_ind, "imf_cpis_assets.csv", bilateral=True)

print("\nData360 sources cached in data/raw/gravity/")
