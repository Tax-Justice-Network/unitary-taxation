# %% [markdown]
# Targeted refetches to close gaps found at the first model checkpoint:
#   1. WGI — keep COMP_BREAKDOWN_1 and filter to WGI_EST (the estimate); the
#      first pull mixed all six sub-measures (estimate/rank/stderr/sources).
#   2. CPIS — fill the 2016 and 2021 years that hit transient 502s.

# %%
import json
import os
import ssl
import time
import urllib.request

import pandas as pd

RAW = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "raw", "gravity",
)
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
BASE = "https://data360api.worldbank.org/data360"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=120, context=_CTX).read())


def page(database_id, indicator, year, keep):
    rows, skip = [], 0
    while True:
        d = _get(f"{BASE}/data?DATABASE_ID={database_id}&INDICATOR={indicator}"
                 f"&TIME_PERIOD={year}&skip={skip}")
        vals = d.get("value", [])
        rows += [{k: r.get(k) for k in keep} for r in vals]
        skip += len(vals)
        if not vals or skip >= d.get("count", 0):
            break
        time.sleep(0.2)
    return rows


# %%
# 1. WGI estimate only.
WGI = ["GOV_WGI_GE", "GOV_WGI_RL", "GOV_WGI_RQ", "GOV_WGI_CC", "GOV_WGI_PV", "GOV_WGI_VA"]
keep = ["REF_AREA", "COMP_BREAKDOWN_1", "TIME_PERIOD", "OBS_VALUE"]
for ind in WGI:
    rows = []
    for y in range(2014, 2023):
        try:
            rows += page("WB_WGI", ind, y, keep)
        except Exception as e:
            print(f"  {ind} {y} FAIL {str(e)[:50]}")
    df = pd.DataFrame(rows)
    df = df[df["COMP_BREAKDOWN_1"] == "WGI_EST"]
    df = df[["REF_AREA", "TIME_PERIOD", "OBS_VALUE"]]
    df.to_csv(os.path.join(RAW, f"wgi_{ind}.csv"), index=False)
    print(f"  WGI {ind}: {len(df)} estimate rows")

# %%
# 2. CPIS missing years (same indicator as the main pull).
cpis_path = os.path.join(RAW, "imf_cpis_assets.csv")
cpis = pd.read_csv(cpis_path)
have = set(cpis["TIME_PERIOD"].unique())
keepb = ["REF_AREA", "COMP_BREAKDOWN_1", "TIME_PERIOD", "OBS_VALUE"]
add = []
for y in [2016, 2021]:
    if y in have:
        continue
    try:
        r = page("IMF_CPIS", "IMF_CPIS_I_A_D_L_T_BP6", y, keepb)
        add += r
        print(f"  CPIS {y}: {len(r)} rows")
    except Exception as e:
        print(f"  CPIS {y} FAIL {str(e)[:50]}")
if add:
    cpis = pd.concat([cpis, pd.DataFrame(add)], ignore_index=True)
    cpis.to_csv(cpis_path, index=False)
    print(f"  CPIS now {len(cpis)} rows, years {sorted(cpis.TIME_PERIOD.unique())}")
