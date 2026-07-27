# %%
"""
1b (pass 1 — financials) — In-scope CbCR groups from Key_financials.

Streams the local Orbis flatfile Key_financials-EUR.txt (~49 GB, long format,
one row per entity-statement) and finds every entity whose CONSOLIDATED
(Consolidation code C1/C2) Operating revenue (Turnover) is >= EUR 750M in any
year of the window — i.e. the set of group tops that clear the CbCR threshold.
Operating-revenue values in this file are absolute EUR (verified: Walmart
US710415188 ~ EUR 563bn), NOT thousands.

Pipeline step 1b (Orbis CbCR-universe / destination nexus) — FIRST pass: selects
the in-scope GUO groups that the pass-2 assemble step expands via the Links join.

Reads:
  D:\\data\\Orbis_raw\\...\\Key_financials-EUR.txt        — Orbis financials flatfile (proprietary, local)

Writes:
  data/intermediate/extractive/cbcr_inscope_groups.csv   — in-scope GUO bvd_ids; columns bvd_id, peak_consolidated_oprev_eur, n_qualifying_years, qualifying_years

Usage:
  python 1b_1_financials.py

Author: Alison Schultz (based on Javier Garcia-Bernardo's work).
Last updated: 2026-07-25.
"""
# %% MARK: 1. Setup
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import EXT_INT

# %% MARK: 2. Config
FIN = Path(r"D:\data\Orbis_raw\Financials - Global format incl histo for industries June text\Key_financials-EUR.txt")
OUT = EXT_INT / "cbcr_inscope_groups.csv"

THRESHOLD_EUR = 750_000_000.0          # EUR 750M, absolute units
YEARS = set(range(2016, 2024))         # 2016..2022 closers + Jan-2023 closers (~FY2022; filtered below)


# %% MARK: 3. Helpers
def _num(x):
    x = x.strip().replace(",", "")
    if not x or x[0].isalpha():
        return None
    try:
        return float(x)
    except ValueError:
        return None


# %% MARK: 4. Scan and write
def main():
    print(f"PASS 1: {FIN}", flush=True)
    print(f"threshold: EUR {THRESHOLD_EUR:,.0f} (absolute); years {min(YEARS)}-{max(YEARS)}", flush=True)
    peak = {}        # bvd_id -> max consolidated op-rev (EUR) within window
    years = {}       # bvd_id -> set of qualifying years
    n = 0
    n_qual_rows = 0
    with open(FIN, encoding="utf-8-sig", errors="replace") as fh:
        hdr = fh.readline().rstrip("\n").split("\t")
        idx = {c.strip().lower(): i for i, c in enumerate(hdr)}
        i_bvd = idx["bvd id number"]
        i_con = idx["consolidation code"]
        i_close = idx["closing date"]
        i_rev = idx["operating revenue (turnover)"]
        need = max(i_bvd, i_con, i_close, i_rev)
        for line in fh:
            n += 1
            if n % 20_000_000 == 0:
                print(f"  {n:,} rows scanned; {len(peak):,} in-scope groups so far", flush=True)
            row = line.rstrip("\n").split("\t")
            if len(row) <= need:
                continue
            con = row[i_con].strip()
            if not con or con[0] != "C":          # consolidated accounts only
                continue
            cd = row[i_close].strip()
            if len(cd) < 4:
                continue
            try:
                yr = int(cd[:4])
            except ValueError:
                continue
            if yr not in YEARS:
                continue
            # FY alignment: 2023 closers belong to FY2023 — beyond the sample
            # window — EXCEPT January-2023 closers, which cover FY2022.
            # Accept only those (month "01"); reject when the month is absent.
            if yr == 2023 and cd[4:6] != "01":
                continue
            rev = _num(row[i_rev])
            if rev is None or rev < THRESHOLD_EUR:
                continue
            bvd = row[i_bvd].strip()
            if not bvd:
                continue
            n_qual_rows += 1
            if rev > peak.get(bvd, 0.0):
                peak[bvd] = rev
            years.setdefault(bvd, set()).add(yr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write("bvd_id,peak_consolidated_oprev_eur,n_qualifying_years,qualifying_years\n")
        for bvd in sorted(peak):
            ys = sorted(years[bvd])
            fh.write(f"{bvd},{peak[bvd]:.0f},{len(ys)},{';'.join(map(str, ys))}\n")
    print(f"\nDONE. scanned {n:,} statement rows; {n_qual_rows:,} qualifying rows.", flush=True)
    print(f"In-scope groups (consolidated op-rev >= EUR 750M in >=1 window year): {len(peak):,}", flush=True)
    print(f"Wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
