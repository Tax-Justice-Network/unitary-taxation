"""
CbCR-universe build — PASS 2 PRESENCE (entities -> distinct-group nexus matrix).

Single source of truth for the throwback-nexus matrix consumed by
`5_estimate_profit_shifting.py:_attach_destination_factors`.

Derives the matrix from the entity universe (`cbcr_universe_entities.csv`, written
by `build_cbcr_universe_pass2_assemble.py`) rather than re-streaming the 281 GB
Links file: every member entity already carries its in-scope GUO and both the
member's and the GUO's ISO3, so the nexus is one group-by.

    n_groups   = COUNT(DISTINCT guo_bvd_id) per (hq_iso3, market_iso3)
                 = number of distinct in-scope (>=EUR 750M consolidated) GUO
                   groups HQ'd in `hq` with >=1 entity in `market`.
    n_entities = number of member entities (QA only).

Counting DISTINCT GROUPS is the whole point: two subsidiaries of the same group
in one market count once, so the downstream coverage fraction

    coverage = min(n_groups / n_cbcr, 1)

measures the share of a CbCR cell's *reported groups* that have a real presence —
NOT the size of the full ownership universe. The denominator n_cbcr is the OECD
CbCR cell's MNE-group count and lives in the CbCR dataset (propagated through
script 2); it is deliberately NOT written into this file, to avoid any ambiguity
about which "group count" the nexus divides by.

Output: data/intermediate/extractive/cbcr_universe_presence.csv
  columns hq_iso3, market_iso3, n_groups, n_entities
"""
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

from _paths import EXT_INT

ENT = EXT_INT / "cbcr_universe_entities.csv"
OUT = EXT_INT / "cbcr_universe_presence.csv"


def main():
    ent = pd.read_csv(ENT, usecols=["hq_iso3", "country_iso3", "guo_bvd_id"])
    print(f"entity universe: {len(ent):,} rows  ({ENT})", flush=True)

    pres = (
        ent.groupby(["hq_iso3", "country_iso3"])
        .agg(n_groups=("guo_bvd_id", "nunique"), n_entities=("guo_bvd_id", "size"))
        .reset_index()
        .rename(columns={"country_iso3": "market_iso3"})
        .sort_values(["hq_iso3", "market_iso3"])
    )

    pres.to_csv(OUT, index=False)
    print(
        f"wrote {OUT}\n  {len(pres):,} (hq_iso3, market_iso3) pairs; "
        f"{pres['hq_iso3'].nunique()} HQ countries, "
        f"{pres['market_iso3'].nunique()} market countries; "
        f"total distinct groups summed = {pres['n_groups'].sum():,}",
        flush=True,
    )


if __name__ == "__main__":
    main()
