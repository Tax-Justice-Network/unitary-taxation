# %% [markdown]
# Download the CEPII Gravity database (Conte, Cotterlaz & Mayer 2022,
# V202211) — the core of the García-Bernardo & Janský (2024) gravity feature
# set. One bulk file provides, per (country1, country2, year):
#   - distance, contiguity, common language/colonial/legal/currency/religion
#     dummies, GSP, hegemony, EU/ACP, GATT/WTO, etc.
#   - unilateral GDP, GDP p.c., population, area, entry cost/procedures, English
#   - BILATERAL TRADE FLOWS (tradeflow_comtrade_o/d, tradeflow_baci) -> covers
#     the Comtrade imports/exports variables, so no separate Comtrade API pull.
#
# Pull-and-cache: downloads the zip to data/raw/gravity/ once and extracts the
# CSV; skips if already present.

# %%
import os
import ssl
import urllib.request
import zipfile

RAW_GRAVITY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "raw", "gravity",
)
os.makedirs(RAW_GRAVITY, exist_ok=True)
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

URL = "https://www.cepii.fr/DATA_DOWNLOAD/gravity/data/Gravity_csv_V202211.zip"
ZIP_PATH = os.path.join(RAW_GRAVITY, "Gravity_csv_V202211.zip")

# %%
if not os.path.exists(ZIP_PATH):
    print(f"Downloading CEPII Gravity V202211 (~207 MB) ...", flush=True)
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=600, context=_CTX) as r, open(ZIP_PATH, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    print(f"  saved {os.path.getsize(ZIP_PATH)/1e6:.0f} MB", flush=True)
else:
    print(f"  cached zip ({os.path.getsize(ZIP_PATH)/1e6:.0f} MB)")

# Extract the gravity CSV.
with zipfile.ZipFile(ZIP_PATH) as z:
    names = [n for n in z.namelist() if n.lower().endswith(".csv")]
    print("  zip contents:", names)
    for n in names:
        dest = os.path.join(RAW_GRAVITY, os.path.basename(n))
        if not os.path.exists(dest):
            with z.open(n) as src, open(dest, "wb") as out:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
            print(f"  extracted {os.path.basename(n)} ({os.path.getsize(dest)/1e6:.0f} MB)")
        else:
            print(f"  already extracted {os.path.basename(n)}")

print("\nCEPII Gravity cached in data/raw/gravity/")
