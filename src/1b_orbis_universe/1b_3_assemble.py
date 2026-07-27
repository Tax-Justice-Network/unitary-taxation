# %%
"""
1b (pass 2 — assemble) — Member-entity universe via the Links join.

Joins the in-scope GUO groups (pass 1) to the filtered GUO-50 links (links
filter) to expand each in-scope group top into all its subsidiaries, building
the member-entity universe and the HQ <-> market presence nexus. Country is
taken from the first 2 chars of the BvD ID (Orbis ISO2 prefix), mapped to ISO3;
entity NAMES are not joined here (needs a separate Entities.txt pass). The whole
chain is reproducible from the flatfiles — pass 1 -> links filter -> assemble
-> presence.

Pipeline step 1b (Orbis CbCR-universe / destination nexus) — pass-2 assemble:
expands the pass-1 groups over the filtered links; pass-2 presence then group-bys
the resulting entity universe into the distinct-group matrix.

Reads:
  data/intermediate/extractive/cbcr_inscope_groups.csv    — in-scope GUO bvd_ids + peak consolidated rev (pass 1)
  data/intermediate/extractive/cbcr_links_filtered.tsv     — (subsidiary_bvd, guo50) active in-scope links (links filter; has duplicates)

Writes:
  data/intermediate/extractive/cbcr_universe_entities.csv  — member-entity universe; columns bvd_id, country_iso2, country_iso3, guo_bvd_id, hq_iso2, hq_iso3, is_guo, group_peak_oprev_eur, group_qualifying_years
  data/intermediate/extractive/cbcr_hq_market_presence.csv — HQ <-> market nexus matrix; columns hq_iso3, market_iso3, n_entities

Usage:
  python 1b_3_assemble.py

Author: Alison Schultz (based on Javier Garcia-Bernardo's work).
Last updated: 2026-07-25.
"""
# %% MARK: 1. Setup
import csv
import sys
from pathlib import Path
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import EXT_INT

# %% MARK: 2. Config and ISO mapping
INSCOPE = EXT_INT / "cbcr_inscope_groups.csv"
LINKS = EXT_INT / "cbcr_links_filtered.tsv"
OUT_ENT = EXT_INT / "cbcr_universe_entities.csv"
OUT_NEXUS = EXT_INT / "cbcr_hq_market_presence.csv"

ISO2_TO_ISO3 = {
    "AD": "AND", "AE": "ARE", "AF": "AFG", "AG": "ATG", "AI": "AIA", "AL": "ALB",
    "AM": "ARM", "AO": "AGO", "AR": "ARG", "AT": "AUT", "AU": "AUS", "AW": "ABW",
    "AZ": "AZE", "BA": "BIH", "BB": "BRB", "BD": "BGD", "BE": "BEL", "BF": "BFA",
    "BG": "BGR", "BH": "BHR", "BI": "BDI", "BJ": "BEN", "BM": "BMU", "BN": "BRN",
    "BO": "BOL", "BR": "BRA", "BS": "BHS", "BT": "BTN", "BW": "BWA", "BY": "BLR",
    "BZ": "BLZ", "CA": "CAN", "CD": "COD", "CF": "CAF", "CG": "COG", "CH": "CHE",
    "CI": "CIV", "CK": "COK", "CL": "CHL", "CM": "CMR", "CN": "CHN", "CO": "COL",
    "CR": "CRI", "CU": "CUB", "CV": "CPV", "CW": "CUW", "CY": "CYP", "CZ": "CZE",
    "DE": "DEU", "DJ": "DJI", "DK": "DNK", "DM": "DMA", "DO": "DOM", "DZ": "DZA",
    "EC": "ECU", "EE": "EST", "EG": "EGY", "ER": "ERI", "ES": "ESP", "ET": "ETH",
    "FI": "FIN", "FJ": "FJI", "FM": "FSM", "FO": "FRO", "FR": "FRA", "GA": "GAB",
    "GB": "GBR", "GD": "GRD", "GE": "GEO", "GF": "GUF", "GG": "GGY", "GH": "GHA",
    "GI": "GIB", "GL": "GRL", "GM": "GMB", "GN": "GIN", "GP": "GLP", "GQ": "GNQ",
    "GR": "GRC", "GT": "GTM", "GU": "GUM", "GW": "GNB", "GY": "GUY", "HK": "HKG",
    "HN": "HND", "HR": "HRV", "HT": "HTI", "HU": "HUN", "ID": "IDN", "IE": "IRL",
    "IL": "ISR", "IM": "IMN", "IN": "IND", "IQ": "IRQ", "IR": "IRN", "IS": "ISL",
    "IT": "ITA", "JE": "JEY", "JM": "JAM", "JO": "JOR", "JP": "JPN", "KE": "KEN",
    "KG": "KGZ", "KH": "KHM", "KI": "KIR", "KM": "COM", "KN": "KNA", "KR": "KOR",
    "KW": "KWT", "KY": "CYM", "KZ": "KAZ", "LA": "LAO", "LB": "LBN", "LC": "LCA",
    "LI": "LIE", "LK": "LKA", "LR": "LBR", "LS": "LSO", "LT": "LTU", "LU": "LUX",
    "LV": "LVA", "LY": "LBY", "MA": "MAR", "MC": "MCO", "MD": "MDA", "ME": "MNE",
    "MG": "MDG", "MH": "MHL", "MK": "MKD", "ML": "MLI", "MM": "MMR", "MN": "MNG",
    "MO": "MAC", "MP": "MNP", "MQ": "MTQ", "MR": "MRT", "MS": "MSR", "MT": "MLT",
    "MU": "MUS", "MV": "MDV", "MW": "MWI", "MX": "MEX", "MY": "MYS", "MZ": "MOZ",
    "NA": "NAM", "NC": "NCL", "NE": "NER", "NG": "NGA", "NI": "NIC", "NL": "NLD",
    "NO": "NOR", "NP": "NPL", "NR": "NRU", "NZ": "NZL", "OM": "OMN", "PA": "PAN",
    "PE": "PER", "PF": "PYF", "PG": "PNG", "PH": "PHL", "PK": "PAK", "PL": "POL",
    "PR": "PRI", "PS": "PSE", "PT": "PRT", "PW": "PLW", "PY": "PRY", "QA": "QAT",
    "RE": "REU", "RO": "ROU", "RS": "SRB", "RU": "RUS", "RW": "RWA", "SA": "SAU",
    "SB": "SLB", "SC": "SYC", "SD": "SDN", "SE": "SWE", "SG": "SGP", "SI": "SVN",
    "SK": "SVK", "SL": "SLE", "SM": "SMR", "SN": "SEN", "SO": "SOM", "SR": "SUR",
    "SS": "SSD", "ST": "STP", "SV": "SLV", "SX": "SXM", "SY": "SYR", "SZ": "SWZ",
    "TC": "TCA", "TD": "TCD", "TG": "TGO", "TH": "THA", "TJ": "TJK", "TL": "TLS",
    "TM": "TKM", "TN": "TUN", "TO": "TON", "TR": "TUR", "TT": "TTO", "TV": "TUV",
    "TW": "TWN", "TZ": "TZA", "UA": "UKR", "UG": "UGA", "US": "USA", "UY": "URY",
    "UZ": "UZB", "VC": "VCT", "VE": "VEN", "VG": "VGB", "VI": "VIR", "VN": "VNM",
    "VU": "VUT", "WS": "WSM", "YE": "YEM", "ZA": "ZAF", "ZM": "ZMB", "ZW": "ZWE",
}


_UNMAPPED_PREFIXES = {}


def iso3(bvd):
    """BvD-id prefix -> ISO3, or None for non-country prefixes (e.g. WW/YY).
    Returning the raw prefix would silently never match a CbCR partner in the
    script-5 merge — unmapped prefixes are counted and reported instead."""
    p = bvd[:2].upper()
    c = ISO2_TO_ISO3.get(p)
    if c is None:
        _UNMAPPED_PREFIXES[p] = _UNMAPPED_PREFIXES.get(p, 0) + 1
    return c


# %% MARK: 3. Assemble and write
def main():
    # in-scope groups: guo -> (peak_oprev, qualifying_years)
    grp = {}
    with open(INSCOPE, encoding="utf-8") as fh:
        r = csv.DictReader(fh)
        for d in r:
            grp[d["bvd_id"]] = (d["peak_consolidated_oprev_eur"], d["qualifying_years"])

    # member -> guo (dedup; if a subsidiary maps to >1 in-scope guo, keep the one
    # with the larger group revenue).
    member_guo = {}
    n_pairs = 0
    with open(LINKS, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            sub, guo = parts[0].strip(), parts[1].strip()
            if not sub or guo not in grp:
                continue
            n_pairs += 1
            cur = member_guo.get(sub)
            if cur is None or float(grp[guo][0]) > float(grp[cur][0]):
                member_guo[sub] = guo

    # the GUOs themselves are members (group tops), guo = self
    for guo in grp:
        member_guo.setdefault(guo, guo)

    # Collapse sub-holdings: an in-scope GUO that is itself a member of a
    # larger in-scope group must not count as a separate group (it would
    # double-count the same multinational in the nexus matrix). Resolve every
    # entity's group id to the ultimate group top.
    def _resolve(g):
        seen = set()
        while member_guo.get(g, g) != g and g not in seen:
            seen.add(g)
            g = member_guo[g]
        return g

    member_guo = {sub: _resolve(guo) for sub, guo in member_guo.items()}

    # write entity universe + accumulate nexus
    nexus = defaultdict(int)
    n_rows = 0
    with open(OUT_ENT, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["bvd_id", "country_iso2", "country_iso3", "guo_bvd_id",
                    "hq_iso2", "hq_iso3", "is_guo", "group_peak_oprev_eur",
                    "group_qualifying_years"])
        for bvd, guo in member_guo.items():
            c2, h2 = bvd[:2].upper(), guo[:2].upper()
            c3, h3 = iso3(bvd), iso3(guo)
            is_guo = int(bvd == guo)
            peak, qy = grp[guo]
            w.writerow([bvd, c2, c3 or "", guo, h2, h3 or "", is_guo, peak, qy])
            if c3 is not None and h3 is not None:
                nexus[(h3, c3)] += 1
            n_rows += 1

    with open(OUT_NEXUS, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["hq_iso3", "market_iso3", "n_entities"])
        for (h3, c3), n in sorted(nexus.items(), key=lambda kv: -kv[1]):
            w.writerow([h3, c3, n])

    print(f"in-scope groups:        {len(grp):,}")
    print(f"filtered link pairs:    {n_pairs:,}")
    print(f"universe entities:      {n_rows:,}  -> {OUT_ENT}")
    print(f"HQ x market cells:      {len(nexus):,}  -> {OUT_NEXUS}")
    if _UNMAPPED_PREFIXES:
        print(f"non-country BvD prefixes excluded from the nexus: "
              f"{dict(sorted(_UNMAPPED_PREFIXES.items(), key=lambda kv: -kv[1]))}")


if __name__ == "__main__":
    main()
