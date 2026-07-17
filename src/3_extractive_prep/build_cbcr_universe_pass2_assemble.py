"""
CbCR-universe build — PASS 2 ASSEMBLE (Links join → entity universe + nexus).

Consumes:
  data/intermediate/extractive/cbcr_inscope_groups.csv   (pass 1: in-scope GUO bvd_ids + peak consolidated rev)
  data/intermediate/extractive/cbcr_links_filtered.tsv    (pass 2 awk: (subsidiary_bvd, guo50) for active links whose GUO 50 is in-scope; has duplicates)

Produces:
  data/intermediate/extractive/cbcr_universe_entities.csv
      bvd_id, country_iso2, country_iso3, guo_bvd_id, hq_iso2, hq_iso3,
      is_guo, group_peak_oprev_eur, group_qualifying_years
  data/intermediate/extractive/cbcr_hq_market_presence.csv
      hq_iso3, market_iso3, n_entities          (the HQ <-> market nexus matrix)

Country is taken from the first 2 chars of the BvD ID (Orbis ISO2 prefix),
mapped to ISO3. Entity NAMES are not joined here (needs a separate Entities.txt
pass) — add later if required.
"""
import csv
import sys
from pathlib import Path
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import EXT_INT

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


def iso3(bvd):
    return ISO2_TO_ISO3.get(bvd[:2].upper(), bvd[:2].upper())


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
            w.writerow([bvd, c2, c3, guo, h2, h3, is_guo, peak, qy])
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


if __name__ == "__main__":
    main()
