# %% [markdown]
# Fetch the World Bank unilateral indicators for the García-Bernardo & Janský
# (2024) gravity/ML imputation feature set (see docs/gravity_features_sources.md).
#
# Pull-and-cache: each indicator is fetched once from the World Bank API and
# written to data/raw/gravity/wb_<CODE>.csv (long: iso3, year, value). On later
# runs the cached CSV is read and the API is not called again — frozen for
# reproducibility. Delete a file to force a refresh.

# %%
import json
import os
import time
import urllib.request

import pandas as pd

RAW_GRAVITY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "raw", "gravity",
)
os.makedirs(RAW_GRAVITY, exist_ok=True)

YEAR_FROM, YEAR_TO = 2014, 2022  # paper uses 2014-2018 means; pull through 2022 for our panel

# Table A.2 World Bank indicators (code -> short name).
# Note: WGI governance (GE/RL/RQ/CC/PV/VA) is archived in the classic v2 API and
# is fetched instead from WB Data360 (GOV_WGI_*) in fetch_data360.py.
# IC.TAX.DURS (tax_complex / time to pay taxes) is a retired Doing Business
# indicator no longer served by the API -> omitted (documented in the manifest).
WB_INDICATORS = {
    # Socio-economic / macro
    "SP.POP.TOTL": "population",
    "NY.GDP.MKTP.CD": "gdp_current_usd",
    "NY.GDP.PCAP.CD": "gdp_per_capita_usd",
    "NE.CON.PRVT.KD": "hh_consumption_kd",
    "NE.GDI.FTOT.KD": "gross_fixed_cap_formation_kd",
    "BX.KLT.DINV.CD.WD": "fdi_inflows_usd",
    "NE.IMP.GNFS.CD": "imports_gs_usd",
    "NE.EXP.GNFS.CD": "exports_gs_usd",
    "BM.GSR.ROYL.CD": "ip_payments_usd",
    "BX.GSR.ROYL.CD": "ip_receipts_usd",
    "DT.DOD.DECT.CD": "external_debt_stocks_usd",
    "SE.XPD.TOTL.GD.ZS": "govt_educ_exp_pct_gdp",
    "SH.MED.NUMW.P3": "nurses_per_1000",
    "SH.MED.PHYS.ZS": "physicians_per_1000",
    "SH.XPD.GHED.GD.ZS": "govt_health_exp_pct_gdp",
}


def _fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    payload = json.loads(urllib.request.urlopen(req, timeout=60).read())
    if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
        return []
    return [
        {"iso3": r["countryiso3code"], "year": int(r["date"]), "value": r["value"]}
        for r in payload[1]
    ]


def fetch_indicator(code):
    """Fetch one WB indicator for all countries, YEAR_FROM..YEAR_TO -> long df.

    Tries the full date range; some indicators 400 on a multi-year range, so
    fall back to fetching year by year.
    """
    base = f"https://api.worldbank.org/v2/country/all/indicator/{code}?format=json&per_page=20000"
    try:
        rows = _fetch_url(f"{base}&date={YEAR_FROM}:{YEAR_TO}")
    except Exception:
        rows = []
        for y in range(YEAR_FROM, YEAR_TO + 1):
            try:
                rows.extend(_fetch_url(f"{base}&date={y}"))
            except Exception:
                pass
    df = pd.DataFrame(rows, columns=["iso3", "year", "value"])
    return df[df["iso3"].astype(bool)]


# %%
for code, name in WB_INDICATORS.items():
    out = os.path.join(RAW_GRAVITY, f"wb_{code}.csv")
    if os.path.exists(out):
        n = len(pd.read_csv(out))
        print(f"  cached  {code:<22} {name:<28} ({n} rows)")
        continue
    try:
        df = fetch_indicator(code)
        df.to_csv(out, index=False)
        print(f"  fetched {code:<22} {name:<28} ({len(df)} rows)")
        time.sleep(0.5)
    except Exception as e:
        print(f"  FAIL    {code:<22} {name:<28} {type(e).__name__}: {str(e)[:60]}")

print(f"\nWorld Bank indicators cached in data/raw/gravity/")
