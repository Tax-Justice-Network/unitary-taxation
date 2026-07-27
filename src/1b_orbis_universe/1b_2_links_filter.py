# %%
"""
1b (pass 2 — links filter) — Filter the Orbis Links flatfile to in-scope GUO-50 links.

Streams the proprietary Links_current.txt (~13 GB extracted, tab-separated,
header row) and keeps, for every ACTIVE link row whose GUO 50 (50%-threshold
global ultimate owner) is one of the in-scope CbCR groups from pass 1, the two
columns (subsidiary_bvd, guo50); duplicates allowed (the assemble step dedups).
Column layout (June-2022 vintage, verified): Subsidiary BvD ID [0], ...,
Active/archived [11], GUO 25 [12], GUO 50 [13], ...

Pipeline step 1b (Orbis CbCR-universe / destination nexus) — helper between
pass 1 and pass-2 assemble: prunes the Links flatfile to the in-scope links the
assemble step joins.

Reads:
  D:\\data\\Orbis_raw\\...\\Links_current.txt             — Orbis ownership links flatfile (proprietary, local)
  data/intermediate/extractive/cbcr_inscope_groups.csv   — in-scope GUO bvd_ids (pass 1)

Writes:
  data/intermediate/extractive/cbcr_links_filtered.tsv   — (subsidiary_bvd, guo50) for in-scope active links; duplicates allowed

Usage:
  python 1b_2_links_filter.py

Author: Alison Schultz (based on Javier Garcia-Bernardo's work).
Last updated: 2026-07-25.
"""
# %% MARK: 1. Setup
import csv
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import EXT_INT

# %% MARK: 2. Config
LINKS = Path(r"D:\data\Orbis_raw\Ownership histo June text\Links_current.txt")
INSCOPE = EXT_INT / "cbcr_inscope_groups.csv"
OUT = EXT_INT / "cbcr_links_filtered.tsv"

COL_SUB, COL_STATUS, COL_GUO50 = 0, 11, 13


# %% MARK: 3. Filter and write
def main():
    with open(INSCOPE, encoding="utf-8-sig", newline="") as f:
        inscope = {r["bvd_id"] for r in csv.DictReader(f)}
    print(f"in-scope GUO-50 groups: {len(inscope):,}")

    t0 = time.time()
    n_in = n_out = 0
    with open(LINKS, encoding="utf-8", errors="replace", newline="") as fin, \
         open(OUT, "w", encoding="utf-8", newline="") as fout:
        header = fin.readline().rstrip("\n").split("\t")
        assert header[COL_SUB] == "Subsidiary BvD ID", header[COL_SUB]
        assert header[COL_STATUS] == "Active/archived", header[COL_STATUS]
        assert header[COL_GUO50] == "GUO 50", header[COL_GUO50]
        for line in fin:
            n_in += 1
            parts = line.rstrip("\n").split("\t")
            if len(parts) <= COL_GUO50:
                continue
            if parts[COL_STATUS] != "active":
                continue
            guo50 = parts[COL_GUO50]
            if guo50 in inscope:
                fout.write(f"{parts[COL_SUB]}\t{guo50}\n")
                n_out += 1
            if n_in % 20_000_000 == 0:
                print(f"  {n_in/1e6:,.0f}M rows read, {n_out/1e6:,.1f}M kept "
                      f"({(time.time()-t0)/60:.1f} min)", flush=True)
    print(f"done: {n_in:,} rows read, {n_out:,} kept -> {OUT} "
          f"({(time.time()-t0)/60:.1f} min)")


if __name__ == "__main__":
    main()
