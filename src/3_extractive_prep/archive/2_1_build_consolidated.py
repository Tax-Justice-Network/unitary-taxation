"""
Build a single clean consolidated dataset for the extractive royalty analysis.

Output: data/final/extractive_royalty_dataset.csv
One row per country. For each metric, uses the latest year where that specific
metric is populated (so totals and sub-components can come from different years).

Columns:
  - WB rents (extraction value) — by commodity, in USD
  - GRD — total + sub-components (resource_taxes, cit_resource, indirect_taxes,
    nontax_rev_resource), each with its own year column and USD conversion
  - EITI — total + payment-type breakdown, each with its own year column
  - Three derived comparators for the carve-out:
      actual_captured_total_usd      — broad (all government revenue from resources)
                                        used for step-5 system comparison
      actual_captured_deductible_usd — narrow (royalty-type payments only, i.e.
                                        flows that reduce CbCR profit). Used for
                                        the step-2b floor adjustment.
      actual_captured_cit_usd        — CIT only. Not typically used directly but
                                        exposed for sensitivity analysis.
"""

import csv, os
from collections import defaultdict

from _paths import RAW, FINAL  # noqa: E402

os.makedirs(FINAL, exist_ok=True)

# ── ISO3 to country name ──
ISO_NAMES = {
    "ABW": "Aruba",
    "AFG": "Afghanistan",
    "AGO": "Angola",
    "ALB": "Albania",
    "AND": "Andorra",
    "ARE": "United Arab Emirates",
    "ARG": "Argentina",
    "ARM": "Armenia",
    "ASM": "American Samoa",
    "AUS": "Australia",
    "AUT": "Austria",
    "AZE": "Azerbaijan",
    "BEL": "Belgium",
    "BEN": "Benin",
    "BFA": "Burkina Faso",
    "BGD": "Bangladesh",
    "BGR": "Bulgaria",
    "BHR": "Bahrain",
    "BHS": "Bahamas",
    "BIH": "Bosnia and Herzegovina",
    "BLR": "Belarus",
    "BLZ": "Belize",
    "BMU": "Bermuda",
    "BOL": "Bolivia",
    "BRA": "Brazil",
    "BRB": "Barbados",
    "BRN": "Brunei",
    "BWA": "Botswana",
    "CAF": "Central African Republic",
    "CAN": "Canada",
    "CHE": "Switzerland",
    "CHL": "Chile",
    "CHN": "China",
    "CIV": "Cote d'Ivoire",
    "CMR": "Cameroon",
    "COD": "DR Congo",
    "COG": "Congo",
    "COL": "Colombia",
    "CRI": "Costa Rica",
    "CUW": "Curacao",
    "CYM": "Cayman Islands",
    "CYP": "Cyprus",
    "CZE": "Czech Republic",
    "DEU": "Germany",
    "DNK": "Denmark",
    "DOM": "Dominican Republic",
    "DZA": "Algeria",
    "ECU": "Ecuador",
    "EGY": "Egypt",
    "ESP": "Spain",
    "EST": "Estonia",
    "ETH": "Ethiopia",
    "FIN": "Finland",
    "FJI": "Fiji",
    "FRA": "France",
    "FRO": "Faroe Islands",
    "GAB": "Gabon",
    "GBR": "United Kingdom",
    "GEO": "Georgia",
    "GGY": "Guernsey",
    "GHA": "Ghana",
    "GIB": "Gibraltar",
    "GIN": "Guinea",
    "GLP": "Guadeloupe",
    "GNB": "Guinea-Bissau",
    "GNQ": "Equatorial Guinea",
    "GRC": "Greece",
    "GRL": "Greenland",
    "GTM": "Guatemala",
    "GUM": "Guam",
    "HKG": "Hong Kong",
    "HND": "Honduras",
    "HRV": "Croatia",
    "HTI": "Haiti",
    "HUN": "Hungary",
    "IDN": "Indonesia",
    "IMN": "Isle of Man",
    "IND": "India",
    "IRL": "Ireland",
    "IRN": "Iran",
    "IRQ": "Iraq",
    "ISL": "Iceland",
    "ISR": "Israel",
    "ITA": "Italy",
    "JAM": "Jamaica",
    "JEY": "Jersey",
    "JOR": "Jordan",
    "JPN": "Japan",
    "KAZ": "Kazakhstan",
    "KEN": "Kenya",
    "KGZ": "Kyrgyz Republic",
    "KHM": "Cambodia",
    "KNA": "St. Kitts and Nevis",
    "KOR": "South Korea",
    "KWT": "Kuwait",
    "LAO": "Lao PDR",
    "LBN": "Lebanon",
    "LBR": "Liberia",
    "LBY": "Libya",
    "LCA": "St. Lucia",
    "LKA": "Sri Lanka",
    "LSO": "Lesotho",
    "LTU": "Lithuania",
    "LUX": "Luxembourg",
    "LVA": "Latvia",
    "MAC": "Macao",
    "MAR": "Morocco",
    "MCO": "Monaco",
    "MDA": "Moldova",
    "MDG": "Madagascar",
    "MEX": "Mexico",
    "MKD": "North Macedonia",
    "MLI": "Mali",
    "MLT": "Malta",
    "MMR": "Myanmar",
    "MNE": "Montenegro",
    "MNG": "Mongolia",
    "MOZ": "Mozambique",
    "MRT": "Mauritania",
    "MUS": "Mauritius",
    "MWI": "Malawi",
    "MYS": "Malaysia",
    "NAM": "Namibia",
    "NCL": "New Caledonia",
    "NER": "Niger",
    "NGA": "Nigeria",
    "NIC": "Nicaragua",
    "NLD": "Netherlands",
    "NOR": "Norway",
    "NZL": "New Zealand",
    "OMN": "Oman",
    "PAK": "Pakistan",
    "PAN": "Panama",
    "PER": "Peru",
    "PHL": "Philippines",
    "PNG": "Papua New Guinea",
    "POL": "Poland",
    "PRI": "Puerto Rico",
    "PRT": "Portugal",
    "PRY": "Paraguay",
    "PYF": "French Polynesia",
    "QAT": "Qatar",
    "ROU": "Romania",
    "RUS": "Russia",
    "RWA": "Rwanda",
    "SAU": "Saudi Arabia",
    "SDN": "Sudan",
    "SEN": "Senegal",
    "SGP": "Singapore",
    "SLB": "Solomon Islands",
    "SLE": "Sierra Leone",
    "SLV": "El Salvador",
    "SRB": "Serbia",
    "SSD": "South Sudan",
    "SVK": "Slovakia",
    "SVN": "Slovenia",
    "SWE": "Sweden",
    "SWZ": "Eswatini",
    "SYC": "Seychelles",
    "SYR": "Syria",
    "TCD": "Chad",
    "TGO": "Togo",
    "THA": "Thailand",
    "TJK": "Tajikistan",
    "TLS": "Timor-Leste",
    "TTO": "Trinidad and Tobago",
    "TUN": "Tunisia",
    "TUR": "Turkey",
    "TWN": "Taiwan",
    "TZA": "Tanzania",
    "UGA": "Uganda",
    "UKR": "Ukraine",
    "URY": "Uruguay",
    "USA": "United States",
    "UZB": "Uzbekistan",
    "VEN": "Venezuela",
    "VGB": "British Virgin Islands",
    "VIR": "US Virgin Islands",
    "VNM": "Vietnam",
    "YEM": "Yemen",
    "ZAF": "South Africa",
    "ZMB": "Zambia",
    "ZWE": "Zimbabwe",
}

TARGET_ISOS = sorted(ISO_NAMES.keys())

# ── 1. Read WB rents — get latest year per country ──
print("Reading WB resource rents...")
wb_latest = {}  # iso -> row dict (latest year)
with open(os.path.join(RAW, "wb_resource_rents.csv"), encoding="utf-8") as f:
    for row in csv.DictReader(f):
        iso = row["country_iso3"]
        yr = int(row["year"])
        val = row.get("total_rents_pct_gdp", "")
        if val and val.strip():
            if iso not in wb_latest or yr > int(wb_latest[iso]["year"]):
                wb_latest[iso] = row

# ── 2. Read GRD — per-field latest year (different fields may be reported in different years) ──
print("Reading GRD 2025...")
GRD_FIELDS = [
    "total_resource_rev",
    "resource_taxes",
    "cit_resource",
    "tax_income_profits_capgains_resource",
    "indirect_taxes_resource",
    "nontax_rev_resource",
    "total_rev_exgrants_exsc",
]
# per-field: iso -> {"year": yr, "value": val}
grd_by_field = {fld: {} for fld in GRD_FIELDS}
with open(os.path.join(RAW, "grd_resource_revenue.csv"), encoding="utf-8") as f:
    for row in csv.DictReader(f):
        iso = row["iso"]
        try:
            yr = int(float(row["year"]))
        except:
            continue
        for fld in GRD_FIELDS:
            v = (row.get(fld, "") or "").strip()
            try:
                fv = float(v) if v else 0.0
            except ValueError:
                continue
            if fv > 0:
                if iso not in grd_by_field[fld] or yr > grd_by_field[fld][iso]["year"]:
                    grd_by_field[fld][iso] = {"year": yr, "value": fv}

# ── 3. Read EITI — per-field latest year + coherent "detail-year" selection ──
print("Reading EITI revenues...")
# Map internal column name → EITI payment-type label in raw CSV
EITI_FIELD_MAP = {
    "total_rev":            "revenue_government_total_usd",  # summary total
    # Cost-side non-tax (royalty-type, expensed by MNE)
    "royalties":            "Royalties",
    "bonuses":              "Bonuses",
    "production_ent":       "Production entitlements (in-kind or cash)",
    "licence_fees":         "Licence fees",
    "other_rent":           "Other rent payments",
    "delivered_directly":   "Delivered/paid directly to government",
    "rent":                 "Rent",
    # Cost-side tax (expensed by MNE before profit_before_tax)
    "customs":              "Customs and other import duties",
    "excise":               "Excise taxes",
    "export_tax":           "Taxes on exports",
    "property_tax":         "Taxes on property",
    "payroll_tax":          "Taxes on payroll and workforce",
    "social_emp":           "Social security employer contributions",
    "social_contrib":       "Social contributions",
    "other_taxes_natres":   "Other taxes payable by natural resource companies",
    "admin_fees":           "Administrative fees for government services",
    "compulsory_transfers": "Compulsory transfers to government (infrastructure and other)",
    "fines":                "Fines, penalties, and forfeits",
    "emission_tax":         "Emission and pollution taxes",
    "motor_vehicle":        "Motor vehicle taxes",
    "voluntary_transfers":  "Voluntary transfers to government (donations)",
    "sales_govt_units":     "Sales of goods and services by government units",
    "unclassified":         "Revenues not classified",
    # CIT-side (NOT expensed; sits below profit_before_tax in CbCR)
    "cit":                  "Ordinary taxes on income, profits and capital gains",
    "extraordinary_cit":    "Extraordinary taxes on income, profits and capital gains",
    # Equity-side (outside MNE accounts entirely — state's own ownership flows)
    "soe_profits":          "Profits of natural resource export monopolies",
    "from_soe":             "From state-owned enterprises",
    "dividends":            "Dividends",
    "govt_participation":   "From government participation (equity)",
    "delivered_to_soe":     "Delivered/paid to state-owned enterprise(s)",
    "quasi_corp":           "Withdrawals from income of quasi-corporations",
    # Pass-through (kept separate, NOT in any rollup)
    "vat":                  "General taxes on goods and services (VAT, sales tax, turnover tax)",
}

# Economic partition — see module docstring.
# The line is between EXPENSED flows (already removed from CbCR profit_before_tax)
# and non-expensed flows. This matters for the carve-out double-counting analysis.
DEDUCTIBLE_KEYS = (
    # cost-side non-tax
    "royalties", "bonuses", "production_ent", "licence_fees",
    "other_rent", "delivered_directly", "rent",
    # cost-side tax
    "customs", "excise", "export_tax", "property_tax",
    "payroll_tax", "social_emp", "social_contrib",
    "other_taxes_natres", "admin_fees", "compulsory_transfers",
    "fines", "emission_tax", "motor_vehicle",
)
CIT_KEYS = ("cit", "extraordinary_cit")
EQUITY_KEYS = (
    "soe_profits", "from_soe", "dividends",
    "govt_participation", "delivered_to_soe", "quasi_corp",
)
# VAT excluded from rollups — it's a pass-through/indirect tax, not really a company cost

eiti_by_field = {k: {} for k in EITI_FIELD_MAP}
eiti_sector = {}  # iso -> (year, oil, gas, mining) from latest total-year

# For single-year-coherent sums, track per (iso, year) the row values for deductible/CIT keys.
eiti_year_records = defaultdict(dict)  # (iso, year) -> {key: value}

with open(os.path.join(RAW, "eiti_revenues.csv"), encoding="utf-8") as f:
    for row in csv.DictReader(f):
        iso = row.get("country_iso3", "")
        if not iso:
            continue
        try:
            yr = int(row["year"])
        except:
            continue
        for key, col in EITI_FIELD_MAP.items():
            v = (row.get(col, "") or "").strip()
            try:
                fv = float(v) if v else 0.0
            except ValueError:
                continue
            if fv > 0:
                if iso not in eiti_by_field[key] or yr > eiti_by_field[key][iso]["year"]:
                    eiti_by_field[key][iso] = {"year": yr, "value": fv}
                eiti_year_records[(iso, yr)][key] = fv
        # Track sector flags from latest total-reporting year
        total_v = (row.get("revenue_government_total_usd", "") or "").strip()
        try:
            total_fv = float(total_v) if total_v else 0.0
        except ValueError:
            total_fv = 0.0
        if total_fv > 0 and (iso not in eiti_sector or yr > eiti_sector[iso][0]):
            eiti_sector[iso] = (yr, row.get("sector_oil", ""), row.get("sector_gas", ""), row.get("sector_mining", ""))

# For each country, pick the latest year where at least one deductible key is reported;
# similarly for CIT. These are used for coherent single-year sums in the derived columns.
def latest_year_with_any(iso, keys):
    best = None
    for (i, y), rec in eiti_year_records.items():
        if i != iso:
            continue
        if any(k in rec and rec[k] > 0 for k in keys):
            if best is None or y > best:
                best = y
    return best

eiti_deductible_year_and_sum = {}
eiti_cit_year_and_sum = {}
eiti_equity_year_and_sum = {}
for iso in {i for (i, _) in eiti_year_records}:
    yr_ded = latest_year_with_any(iso, DEDUCTIBLE_KEYS)
    if yr_ded is not None:
        rec = eiti_year_records[(iso, yr_ded)]
        s = sum(rec.get(k, 0.0) for k in DEDUCTIBLE_KEYS)
        if s > 0:
            eiti_deductible_year_and_sum[iso] = (yr_ded, s)
    yr_cit = latest_year_with_any(iso, CIT_KEYS)
    if yr_cit is not None:
        rec = eiti_year_records[(iso, yr_cit)]
        s = sum(rec.get(k, 0.0) for k in CIT_KEYS)
        if s > 0:
            eiti_cit_year_and_sum[iso] = (yr_cit, s)
    yr_eq = latest_year_with_any(iso, EQUITY_KEYS)
    if yr_eq is not None:
        rec = eiti_year_records[(iso, yr_eq)]
        s = sum(rec.get(k, 0.0) for k in EQUITY_KEYS)
        if s > 0:
            eiti_equity_year_and_sum[iso] = (yr_eq, s)

# ── 3b. Load manual resource-revenue fills ──
print("Reading manual resource-revenue fills...")
manual_fills = {}  # iso3 -> (value_usd, year, source, confidence, prefer_over_eiti)
manual_path = os.path.join(FINAL, "manual_resource_revenue_fills.csv")
if os.path.exists(manual_path):
    with open(manual_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = next(csv.reader([line]))
            if parts and parts[0] == "iso3":
                continue
            if len(parts) < 5:
                continue
            iso3 = parts[0].strip()
            try:
                val = float(parts[2])
            except (ValueError, IndexError):
                continue
            year = parts[3].strip() if len(parts) > 3 else ""
            source = parts[4].strip() if len(parts) > 4 else ""
            conf = parts[5].strip() if len(parts) > 5 else ""
            prefer = parts[6].strip().upper() in ("TRUE", "1", "YES") if len(parts) > 6 else False
            if iso3 and val > 0:
                manual_fills[iso3] = (val, year, source, conf, prefer)
print(f"  {len(manual_fills)} manual fills loaded.\n")

# ── 4. HQ shares (hardcoded from build_hq_shares.py output) ──
# These are the shares to apply when computing royalty deductions
# Stored separately in Extractive_HQ_Shares.xlsx — referenced here for documentation

# ── 5. Build consolidated output ──
print("Building consolidated dataset...")

output_cols = [
    "iso3",
    "country_name",
    # WB rents (Variable 1)
    "wb_year",
    "wb_gdp_usd",
    "wb_total_rents_pct_gdp",
    "wb_oil_rents_pct_gdp",
    "wb_gas_rents_pct_gdp",
    "wb_coal_rents_pct_gdp",
    "wb_mineral_rents_pct_gdp",
    "wb_forest_rents_pct_gdp",
    "wb_total_rents_usd",
    "wb_oil_rents_usd",
    "wb_gas_rents_usd",
    "wb_coal_rents_usd",
    "wb_mineral_rents_usd",
    "wb_forest_rents_usd",
    # GRD (Variable 2a) — per-field latest year (fractions of GDP in `_frac_gdp` columns)
    "grd_total_resource_rev_year", "grd_total_resource_rev_frac_gdp", "grd_total_resource_rev_usd",
    "grd_resource_taxes_year",     "grd_resource_taxes_frac_gdp",     "grd_resource_taxes_usd",
    "grd_cit_resource_year",       "grd_cit_resource_frac_gdp",       "grd_cit_resource_usd",
    "grd_tax_income_profits_capgains_resource_year", "grd_tax_income_profits_capgains_resource_frac_gdp", "grd_tax_income_profits_capgains_resource_usd",
    "grd_indirect_taxes_resource_year", "grd_indirect_taxes_resource_frac_gdp", "grd_indirect_taxes_resource_usd",
    "grd_nontax_rev_resource_year", "grd_nontax_rev_resource_frac_gdp", "grd_nontax_rev_resource_usd",
    # EITI (Variable 2b) — each field comes from its own latest year
    "eiti_total_year",              "eiti_total_rev_usd",
    # cost-side non-tax
    "eiti_royalties_year",          "eiti_royalties_usd",
    "eiti_bonuses_year",            "eiti_bonuses_usd",
    "eiti_production_ent_year",     "eiti_production_ent_usd",
    "eiti_licence_fees_year",       "eiti_licence_fees_usd",
    "eiti_other_rent_year",         "eiti_other_rent_usd",
    "eiti_delivered_directly_year", "eiti_delivered_directly_usd",
    "eiti_rent_year",               "eiti_rent_usd",
    # cost-side tax
    "eiti_customs_year",            "eiti_customs_usd",
    "eiti_excise_year",             "eiti_excise_usd",
    "eiti_export_tax_year",         "eiti_export_tax_usd",
    "eiti_property_tax_year",       "eiti_property_tax_usd",
    "eiti_payroll_tax_year",        "eiti_payroll_tax_usd",
    "eiti_social_emp_year",         "eiti_social_emp_usd",
    "eiti_social_contrib_year",     "eiti_social_contrib_usd",
    "eiti_other_taxes_natres_year", "eiti_other_taxes_natres_usd",
    "eiti_admin_fees_year",         "eiti_admin_fees_usd",
    "eiti_compulsory_transfers_year","eiti_compulsory_transfers_usd",
    "eiti_fines_year",              "eiti_fines_usd",
    "eiti_emission_tax_year",       "eiti_emission_tax_usd",
    "eiti_motor_vehicle_year",      "eiti_motor_vehicle_usd",
    "eiti_voluntary_transfers_year","eiti_voluntary_transfers_usd",
    "eiti_sales_govt_units_year",   "eiti_sales_govt_units_usd",
    "eiti_unclassified_year",       "eiti_unclassified_usd",
    # CIT-side
    "eiti_cit_year",                "eiti_cit_usd",
    "eiti_extraordinary_cit_year",  "eiti_extraordinary_cit_usd",
    # Equity-side
    "eiti_soe_profits_year",        "eiti_soe_profits_usd",
    "eiti_from_soe_year",           "eiti_from_soe_usd",
    "eiti_dividends_year",          "eiti_dividends_usd",
    "eiti_govt_participation_year", "eiti_govt_participation_usd",
    "eiti_delivered_to_soe_year",   "eiti_delivered_to_soe_usd",
    "eiti_quasi_corp_year",         "eiti_quasi_corp_usd",
    # Pass-through (separate, not in rollups)
    "eiti_vat_year",                "eiti_vat_usd",
    "eiti_sector_oil",
    "eiti_sector_gas",
    "eiti_sector_mining",
    # Data availability flags
    "has_wb_rents",
    "has_grd_resource_rev",
    "has_eiti",
    # Derived carve-out comparators — economic partition.
    # Identity: captured_total ≈ captured_deductible + captured_cit + captured_equity (+ VAT)
    # captured_deductible = the cost-side bucket that is ALREADY removed from CbCR profit_before_tax;
    #                       the only one with double-count risk if subtracted from MNE pool again.
    # captured_cit        = paid out of profit_before_tax; subsumed inside Orbis local profit
    #                       (so do NOT add to floor-comparison capture, only diagnostic).
    # captured_equity     = state-ownership flows outside MNE CbCR.
    "actual_captured_total_usd",        "actual_captured_total_source",
    "actual_captured_deductible_usd",   "actual_captured_deductible_source",
    "actual_captured_cit_usd",          "actual_captured_cit_source",
    "actual_captured_equity_usd",       "actual_captured_equity_source",
]

rows_out = []
for iso in TARGET_ISOS:
    row = {"iso3": iso, "country_name": ISO_NAMES.get(iso, iso)}

    # WB rents
    if iso in wb_latest:
        wb = wb_latest[iso]
        row["wb_year"] = wb["year"]
        row["wb_gdp_usd"] = wb["gdp_current_usd"]
        for col in [
            "total_rents_pct_gdp",
            "oil_rents_pct_gdp",
            "gas_rents_pct_gdp",
            "coal_rents_pct_gdp",
            "mineral_rents_pct_gdp",
            "forest_rents_pct_gdp",
            "total_rents_usd",
            "oil_rents_usd",
            "gas_rents_usd",
            "coal_rents_usd",
            "mineral_rents_usd",
            "forest_rents_usd",
        ]:
            row[f"wb_{col}"] = wb.get(col, "")
        row["has_wb_rents"] = "Yes"
    else:
        row["has_wb_rents"] = "No"

    # GRD — per-field (each field's latest year; USD uses WB GDP of the WB-latest year)
    try:
        gdp_wb = float(row.get("wb_gdp_usd", "") or "0")
    except (ValueError, TypeError):
        gdp_wb = 0.0

    grd_field_to_cols = [
        ("total_resource_rev",  "grd_total_resource_rev"),
        ("resource_taxes",      "grd_resource_taxes"),
        ("cit_resource",        "grd_cit_resource"),
        ("tax_income_profits_capgains_resource", "grd_tax_income_profits_capgains_resource"),
        ("indirect_taxes_resource", "grd_indirect_taxes_resource"),
        ("nontax_rev_resource", "grd_nontax_rev_resource"),
    ]
    has_any_grd = False
    for grd_fld, col_prefix in grd_field_to_cols:
        entry = grd_by_field.get(grd_fld, {}).get(iso)
        if entry:
            row[f"{col_prefix}_year"] = str(entry["year"])
            row[f"{col_prefix}_frac_gdp"] = f"{entry['value']:.6f}"
            row[f"{col_prefix}_usd"] = f"{entry['value'] * gdp_wb:.0f}" if gdp_wb > 0 else ""
            has_any_grd = True
    row["has_grd_resource_rev"] = "Yes" if iso in grd_by_field["total_resource_rev"] else "No"

    # EITI — per-field (each payment type's latest year)
    has_any_eiti = False
    for key in EITI_FIELD_MAP:
        entry = eiti_by_field.get(key, {}).get(iso)
        if entry:
            has_any_eiti = True
            if key == "total_rev":
                row["eiti_total_year"] = str(entry["year"])
                row["eiti_total_rev_usd"] = f"{entry['value']:.0f}"
            else:
                row[f"eiti_{key}_year"] = str(entry["year"])
                row[f"eiti_{key}_usd"] = f"{entry['value']:.0f}"
    # Sector flags from latest total-year row
    if iso in eiti_sector:
        _, oil, gas, mining = eiti_sector[iso]
        row["eiti_sector_oil"] = oil
        row["eiti_sector_gas"] = gas
        row["eiti_sector_mining"] = mining
    row["has_eiti"] = "Yes" if has_any_eiti else "No"

    # ── Derived comparators ──
    def _f(s):
        try: return float(s) if s else 0.0
        except ValueError: return 0.0

    # (A) actual_captured_total_usd — all government resource revenue (for step-5 comparison)
    # Source priority: GRD > MANUAL (if prefer_over_eiti) > EITI > MANUAL > 0
    grd_total = _f(row.get("grd_total_resource_rev_usd"))
    eiti_total = _f(row.get("eiti_total_rev_usd"))
    manual_tuple = manual_fills.get(iso)
    manual_prefers = bool(manual_tuple and manual_tuple[4])

    if grd_total > 0:
        row["actual_captured_total_usd"] = f"{grd_total:.0f}"
        row["actual_captured_total_source"] = "GRD"
    elif manual_prefers:
        val, yr, src, conf, _ = manual_tuple
        row["actual_captured_total_usd"] = f"{val:.0f}"
        row["actual_captured_total_source"] = f"MANUAL:{src[:60]}"
    elif eiti_total > 0:
        row["actual_captured_total_usd"] = f"{eiti_total:.0f}"
        row["actual_captured_total_source"] = "EITI"
    elif manual_tuple is not None:
        val, yr, src, conf, _ = manual_tuple
        row["actual_captured_total_usd"] = f"{val:.0f}"
        row["actual_captured_total_source"] = f"MANUAL:{src[:60]}"
    else:
        row["actual_captured_total_usd"] = ""
        row["actual_captured_total_source"] = ""

    # (B) actual_captured_deductible_usd — flows expensed BEFORE CbCR profit_before_tax.
    # Now broad: cost-side non-tax (royalties, bonuses, production entitlements,
    # licence fees, other rent, delivered-directly, rent) + cost-side tax (excise,
    # customs, export, property, payroll, social, fines, emission, motor vehicle,
    # admin fees, compulsory transfers, other natres taxes).
    # CIT and equity flows are NOT here — they have their own columns.
    # Preferred: EITI single-year coherent sum across DEDUCTIBLE_KEYS.
    # Fallback: GRD = indirect_taxes_resource + nontax_rev_resource. Caveat:
    #   GRD nontax mixes royalties (cost-side) with SOE/dividends (equity), so
    #   this overstates the deductible bucket for SOE-heavy countries. EITI is
    #   cleaner where available.
    eiti_ded = eiti_deductible_year_and_sum.get(iso)
    grd_indirect = _f(row.get("grd_indirect_taxes_resource_usd"))
    grd_nontax = _f(row.get("grd_nontax_rev_resource_usd"))
    if eiti_ded is not None:
        row["actual_captured_deductible_usd"] = f"{eiti_ded[1]:.0f}"
        row["actual_captured_deductible_source"] = f"EITI_sum_{eiti_ded[0]}"
    elif grd_indirect > 0 or grd_nontax > 0:
        row["actual_captured_deductible_usd"] = f"{grd_indirect + grd_nontax:.0f}"
        row["actual_captured_deductible_source"] = "GRD_indirect+nontax_proxy"
    else:
        row["actual_captured_deductible_usd"] = ""
        row["actual_captured_deductible_source"] = ""

    # (C) actual_captured_cit_usd — CIT specifically (diagnostic / sensitivity use).
    # Preferred: GRD cit_resource. Fallback: EITI single-year sum (Ordinary + Extraordinary).
    grd_cit = _f(row.get("grd_cit_resource_usd"))
    eiti_cit = eiti_cit_year_and_sum.get(iso)
    if grd_cit > 0:
        row["actual_captured_cit_usd"] = f"{grd_cit:.0f}"
        row["actual_captured_cit_source"] = "GRD"
    elif eiti_cit is not None:
        row["actual_captured_cit_usd"] = f"{eiti_cit[1]:.0f}"
        row["actual_captured_cit_source"] = f"EITI_sum_{eiti_cit[0]}"
    else:
        row["actual_captured_cit_usd"] = ""
        row["actual_captured_cit_source"] = ""

    # (D) actual_captured_equity_usd — state-ownership flows outside MNE CbCR.
    # EITI-only (GRD has no equivalent breakdown — its nontax_rev_resource mixes
    # cost-side with equity flows). Single-year coherent sum across SOE profits,
    # from-SOE, dividends, govt participation, delivered-to-SOE, quasi-corp.
    eiti_eq = eiti_equity_year_and_sum.get(iso)
    if eiti_eq is not None:
        row["actual_captured_equity_usd"] = f"{eiti_eq[1]:.0f}"
        row["actual_captured_equity_source"] = f"EITI_sum_{eiti_eq[0]}"
    else:
        row["actual_captured_equity_usd"] = ""
        row["actual_captured_equity_source"] = ""

    rows_out.append(row)

# Write
outpath = os.path.join(FINAL, "extractive_royalty_dataset.csv")
with open(outpath, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=output_cols, extrasaction="ignore")
    writer.writeheader()
    for row in rows_out:
        writer.writerow(row)

print(f"\nSaved to: {outpath}")
print(f"Rows: {len(rows_out)}")

# Stats
n_wb = sum(1 for r in rows_out if r.get("has_wb_rents") == "Yes")
n_grd = sum(1 for r in rows_out if r.get("has_grd_resource_rev") == "Yes")
n_eiti = sum(1 for r in rows_out if r.get("has_eiti") == "Yes")
print(f"\nCoverage:")
print(f"  WB rents:              {n_wb}/{len(rows_out)}")
print(f"  GRD resource rev:      {n_grd}/{len(rows_out)}")
print(f"  EITI (any field):      {n_eiti}/{len(rows_out)}")
for comp in ("total", "deductible", "cit", "equity"):
    n_has = sum(1 for r in rows_out if r.get(f"actual_captured_{comp}_usd"))
    from collections import Counter
    src_counts = Counter(r.get(f"actual_captured_{comp}_source", "") for r in rows_out if r.get(f"actual_captured_{comp}_usd"))
    src_str = ", ".join(f"{k}={v}" for k, v in sorted(src_counts.items()))
    print(f"  actual_captured_{comp:<10}  {n_has}/{len(rows_out)}  ({src_str})")

# Top 10 by WB total rents
print("\nTop 15 countries by WB total resource rents (USD):")
rents_ranked = [
    (r["iso3"], r["country_name"], float(r.get("wb_total_rents_usd") or "0"))
    for r in rows_out
    if r.get("wb_total_rents_usd")
]
rents_ranked.sort(key=lambda x: -x[2])
for iso, name, val in rents_ranked[:15]:
    print(f"  {iso} {name}: ${val/1e9:.1f}bn")
