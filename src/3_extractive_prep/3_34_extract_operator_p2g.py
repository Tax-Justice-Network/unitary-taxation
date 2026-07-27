"""
Extract operator-side Payments-to-Governments data from major IOC/NOC disclosures.

Consumes (from data/raw/resources/resource_profits_manual_sources/company/):
  Operator documents named `{HQISO3}_{Operator}_{DocType}_{year}.{ext}`
  (e.g. ITA_Eni_P2G_2019.pdf, GBR_BP_P2G_2020.pdf, FRA_TotalEnergies_URD_2022.pdf,
  GBR_Shell_P2G_2016.pdf, CHE_Glencore_P2G_2018.pdf, BRA_Vale_TTR_2019.pdf,
  SAU_Aramco_AR_2019.pdf, ...). See the folder's _rename_manifest_2026-07-21.csv
  for the mapping from the original download names.

Produces:
  data/intermediate/extractive/operator_payments_by_hq_source_yearly.csv
  Columns: hq_iso3, source_iso3, year, value_usd, operator_name, doc_source, bucket

Where `bucket` ∈ {pre_profit, post_profit, equity, fee, other} maps payment categories:
  - Royalties, Licence Fees, Production Entitlements, Bonuses → pre_profit (state's pre-profit take)
  - Taxes (income tax) → post_profit
  - Dividends → equity
  - Infrastructure Improvements, Fees → fee (excluded from main bucket aggregation; small)

Downstream consumer: `1_8_resource_payments_by_hq_source.py:_eiti_hq_share_overrides()`
should be extended to merge in operator data so manual_distributed totals get
HQ-shares anchored on operator-paid data wherever it exists (not just generic Orbis).
"""
from __future__ import annotations
import sys, re, csv
from pathlib import Path
import fitz   # pymupdf
import pycountry

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import RAW, EXT_INT  # noqa: E402

SOURCES = RAW / "resources" / "resource_profits_manual_sources" / "company"
OUT = EXT_INT / "operator_payments_by_hq_source_yearly.csv"

# Country-name → ISO3 lookups for parsing P2G tables
_NAME_TO_ISO3 = {
    "United States": "USA", "United States of America": "USA", "USA": "USA",
    "United Kingdom": "GBR", "UK": "GBR", "U.K.": "GBR",
    "United Arab Emirates": "ARE", "UAE": "ARE",
    "Republic of the Congo": "COG", "Congo": "COG", "Congo (Republic)": "COG",
    "Democratic Republic of the Congo": "COD", "DRC": "COD", "DR Congo": "COD",
    "Republic of Congo": "COG",
    "Côte d'Ivoire": "CIV", "Cote d'Ivoire": "CIV", "Ivory Coast": "CIV",
    "Russia": "RUS", "Russian Federation": "RUS",
    "Venezuela": "VEN", "Bolivia": "BOL", "Brunei": "BRN",
    "São Tomé and Principe": "STP", "Sao Tome and Principe": "STP",
    "Trinidad and Tobago": "TTO", "Czech Republic": "CZE", "Vietnam": "VNM",
    "Iran": "IRN", "South Korea": "KOR", "Korea": "KOR",
    "Tanzania": "TZA", "Egypt": "EGY", "Algeria": "DZA", "Angola": "AGO",
    "Iraq": "IRQ", "Kuwait": "KWT", "Qatar": "QAT", "Oman": "OMN",
    "Saudi Arabia": "SAU", "Israel": "ISR", "Lebanon": "LBN", "Cyprus": "CYP",
    "Norway": "NOR", "Netherlands": "NLD", "Italy": "ITA", "France": "FRA",
    "Germany": "DEU", "Spain": "ESP", "Belgium": "BEL", "Austria": "AUT",
    "Denmark": "DNK", "Bulgaria": "BGR", "Greece": "GRC", "Romania": "ROU",
    "Croatia": "HRV", "Slovakia": "SVK", "Slovenia": "SVN", "Lithuania": "LTU",
    "Latvia": "LVA", "Estonia": "EST", "Hungary": "HUN", "Poland": "POL",
    "Sweden": "SWE", "Finland": "FIN", "Ireland": "IRL", "Switzerland": "CHE",
    "Luxembourg": "LUX", "Malta": "MLT", "Portugal": "PRT",
    "Argentina": "ARG", "Brazil": "BRA", "Chile": "CHL", "Colombia": "COL",
    "Ecuador": "ECU", "Mexico": "MEX", "Peru": "PER", "Uruguay": "URY",
    "Paraguay": "PRY", "Canada": "CAN", "Guyana": "GUY",
    "Nigeria": "NGA", "Mauritania": "MRT", "Mozambique": "MOZ", "Gabon": "GAB",
    "Ghana": "GHA", "Mali": "MLI", "Senegal": "SEN", "Burkina Faso": "BFA",
    "Madagascar": "MDG", "Niger": "NER", "Chad": "TCD", "Sudan": "SDN",
    "South Sudan": "SSD", "Libya": "LBY", "Tunisia": "TUN", "Morocco": "MAR",
    "Kenya": "KEN", "Uganda": "UGA", "Tanzania": "TZA", "Zambia": "ZMB",
    "Namibia": "NAM", "Botswana": "BWA", "Eritrea": "ERI", "Liberia": "LBR",
    "Sierra Leone": "SLE", "Mauritius": "MUS", "South Africa": "ZAF",
    "Yemen": "YEM", "Bahrain": "BHR", "Jordan": "JOR", "Syria": "SYR",
    "Turkey": "TUR", "Azerbaijan": "AZE", "Kazakhstan": "KAZ",
    "Uzbekistan": "UZB", "Turkmenistan": "TKM", "Kyrgyzstan": "KGZ",
    "Tajikistan": "TJK", "Mongolia": "MNG", "China": "CHN",
    "Hong Kong": "HKG", "Taiwan": "TWN", "Japan": "JPN", "India": "IND",
    "Pakistan": "PAK", "Bangladesh": "BGD", "Sri Lanka": "LKA", "Nepal": "NPL",
    "Bhutan": "BTN", "Myanmar": "MMR", "Thailand": "THA", "Malaysia": "MYS",
    "Singapore": "SGP", "Indonesia": "IDN", "Philippines": "PHL",
    "Australia": "AUS", "New Zealand": "NZL", "Papua New Guinea": "PNG",
    "Timor Leste": "TLS", "Timor-Leste": "TLS",
    "Cambodia": "KHM", "Laos": "LAO",
    "Honduras": "HND", "Guatemala": "GTM", "Suriname": "SUR",
    "Dominican Republic": "DOM", "Albania": "ALB", "Ukraine": "UKR",
    "Cameroon": "CMR", "Equatorial Guinea": "GNQ", "Ethiopia": "ETH",
    "Eswatini": "SWZ", "Lesotho": "LSO", "Malawi": "MWI",
    "Afghanistan": "AFG", "Armenia": "ARM", "Georgia": "GEO",
}


def _to_iso3(name: str) -> str | None:
    name = name.strip()
    if name in _NAME_TO_ISO3:
        return _NAME_TO_ISO3[name]
    try:
        c = pycountry.countries.search_fuzzy(name)[0]
        return c.alpha_3
    except Exception:
        return None


def _parse_amount(s: str) -> float | None:
    """Parse a payment-table amount (string like '1,234' or '(56)' or '-')."""
    s = s.strip().replace(" ", "").replace(" ", "")
    if not s or s in ("-", "—", "–", "‐"):
        return 0.0
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = s.replace(",", "")
    if s.endswith("."):
        s = s[:-1]   # strip stray trailing dot (e.g. "73.9.")
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


_NUM_RE = re.compile(r"^\(?[\d,]+(?:\.\d+)?\.?\)?$|^[-–—‐]$")


def _extract_coord_table(page, y_min, y_max, column_anchors,
                         x_country_max=200.0, y_tol=4.0):
    """Coordinate-based table extraction. Returns list of {country, cols} where
    cols is a dict {col_name: float}. For each row of text within [y_min, y_max]:
    text starting at x < x_country_max is part of the country name; numeric
    tokens are binned to the closest column anchor by right-edge x-position."""
    words = [w for w in page.get_text("words") if y_min < w[1] < y_max]
    if not words:
        return []
    words.sort(key=lambda w: (w[1], w[0]))
    rows: list[list] = []
    cur_y = None
    cur: list = []
    for w in words:
        y = w[1]
        if cur_y is None or abs(y - cur_y) <= y_tol:
            cur.append(w)
            cur_y = y if cur_y is None else (cur_y + y) / 2
        else:
            rows.append(cur); cur = [w]; cur_y = y
    if cur:
        rows.append(cur)

    out = []
    anchor_items = list(column_anchors.items())
    for r in rows:
        r.sort(key=lambda w: w[0])
        country_parts = []
        nums_with_x = []
        for w in r:
            x0, _, x1, _, text, *_ = w
            if x0 < x_country_max and not _NUM_RE.match(text):
                country_parts.append(text)
            elif _NUM_RE.match(text):
                v = _parse_amount(text)
                if v is not None:
                    nums_with_x.append((x1, v))   # right-edge
        if not country_parts or not nums_with_x:
            continue
        country = " ".join(country_parts).strip()
        col_vals = {name: 0.0 for name, _ in anchor_items}
        for x_ref, val in nums_with_x:
            best = min(anchor_items, key=lambda kv: abs(kv[1] - x_ref))
            if abs(best[1] - x_ref) < 60:
                col_vals[best[0]] += val
        out.append({"country": country, "cols": col_vals})
    return out


# ── Operator-specific parsers ───────────────────────────────────────────────
def parse_eni_p2g(path: Path, year: int) -> list[dict]:
    """Eni's P2G PDFs have a country-totals table. Currency: EUR thousands.
    Columns: Country, Production Entitlement, Taxes, Royalties, Bonuses, Fees,
    Infrastructure Improvements, Total."""
    EUR_TO_USD = 1.10
    doc = fitz.open(path)
    rows = []
    for i in range(doc.page_count):
        page = doc[i]
        t = page.get_text().replace("\xa0", " ")
        tl = t.lower()
        # Anchor: page has all header words AND at least 4 source-country names.
        header_present = all(h in tl for h in
                             ("production", "entitlement", "taxes", "royalties",
                              "fees", "bonuses", "infrastructure", "total"))
        if not header_present:
            continue
        country_hits = sum(1 for c in
                           ("Algeria", "Angola", "Egypt", "Iraq", "Libya",
                            "Nigeria", "Mexico", "Indonesia", "Kazakhstan",
                            "Tunisia", "Ghana")
                           if c in t)
        if country_hits < 4:
            continue
        # Detect column anchors from header word right-edges.
        anchors = {}
        header_y_max = None
        header_targets = {"entitlement", "taxes", "royalties", "fees",
                          "bonuses", "improvements", "total"}
        for w in page.get_text("words"):
            if w[1] > 280:
                continue
            lower = w[4].lower().strip(":,;.")
            if lower in header_targets and lower not in anchors:
                anchors[lower] = w[2]
                header_y_max = max(header_y_max or 0, w[3])
        if len(anchors) < 7:
            continue
        column_anchors = {
            "production": anchors["entitlement"],
            "taxes":      anchors["taxes"],
            "royalties":  anchors["royalties"],
            "bonuses":    anchors["bonuses"],
            "fees":       anchors["fees"],
            "infra":      anchors["improvements"],
            "total":      anchors["total"],
        }
        y_min = header_y_max + 2
        y_max = page.rect.height
        for w in page.get_text("words"):
            if w[4].lower() == "total" and w[0] < 80 and w[1] > y_min + 20:
                y_max = w[1] - 1; break
        table = _extract_coord_table(page, y_min, y_max, column_anchors,
                                     x_country_max=180.0, y_tol=5.0)
        for entry in table:
            iso = _to_iso3(entry["country"])
            if not iso:
                continue
            cv = entry["cols"]
            prod, taxes, roy, bonus, fees, infra, total = (
                cv["production"], cv["taxes"], cv["royalties"],
                cv["bonuses"], cv["fees"], cv["infra"], cv["total"],
            )
            comp = prod + taxes + roy + bonus + fees + infra
            if total > 0 and abs(comp - total) > 0.5 * max(total, 1):
                continue
            if total == 0 and comp == 0:
                continue
            rows.append({
                "hq_iso3": "ITA", "source_iso3": iso, "year": year,
                "value_usd": (total or comp) * 1000 * EUR_TO_USD,
                "operator_name": "Eni", "doc_source": path.name,
                "pre_profit": (prod + roy + bonus) * 1000 * EUR_TO_USD,
                "post_profit": taxes * 1000 * EUR_TO_USD,
                "equity": 0.0,
                "fee": (fees + infra) * 1000 * EUR_TO_USD,
            })
        break
    return rows


def parse_bp_p2g(path: Path, year: int) -> list[dict]:
    """BP's P2G report has a summary table on the 'Payments overview' page.
    Currency: USD millions. Columns (left → right): Country, Production
    entitlements, Taxes, Royalties, Fees, Bonuses, Infrastructure improvements,
    Total. PDF text extraction skips empty cells, so we use word coordinates
    to bin numbers into columns by their right-edge x-position relative to
    the header-detected anchors.
    """
    doc = fitz.open(path)
    rows = []
    for i in range(doc.page_count):
        page = doc[i]
        t = page.get_text()
        # Anchor on the Payments overview page (has the column header words).
        # Algeria is missing from BP 2024, so we don't require it.
        # 2016-2021 BP reports capitalise "Entitlements"/"Improvements";
        # 2022+ use lowercase. Search case-insensitively.
        tl = t.lower()
        header_present = all(h in tl for h in
                             ("production", "entitlements", "taxes", "royalties",
                              "fees", "bonuses", "infrastructure", "total"))
        if not header_present:
            continue
        # Need at least 3 of the recurring source countries to confirm
        # this is the summary table (vs. a per-country page).
        country_hits = sum(1 for c in
                           ("Angola", "Azerbaijan", "Iraq", "Indonesia",
                            "Oman", "Egypt", "Trinidad", "United Arab Emirates")
                           if c in t)
        if country_hits < 3:
            continue
        # Detect column anchors from header word positions on this page.
        # We use right-edge x (word[2]) so right-aligned numbers bin correctly.
        # 2016-2021 BP reports capitalise the header ("Entitlements",
        # "Improvements"); 2022+ use lowercase. Match case-insensitively.
        anchors = {}
        header_y_max = None
        header_targets = {"entitlements", "taxes", "royalties", "fees",
                          "bonuses", "improvements", "total"}
        for w in page.get_text("words"):
            if w[1] > 250:   # ignore body
                continue
            lower = w[4].lower()
            if lower in header_targets and lower not in anchors:
                anchors[lower] = w[2]
                header_y_max = max(header_y_max or 0, w[3])
        # Need all 7 to parse reliably.
        if len(anchors) < 7:
            continue
        column_anchors = {
            "production": anchors["entitlements"],
            "taxes":      anchors["taxes"],
            "royalties":  anchors["royalties"],
            "fees":       anchors["fees"],
            "bonuses":    anchors["bonuses"],
            "infra":      anchors["improvements"],
            "total":      anchors["total"],
        }
        # Y range: from just below header to before the "Total" row at bottom.
        y_min = header_y_max + 2
        # Find Y of the bottom "Total" word (in the leftmost column).
        y_max = page.rect.height
        for w in page.get_text("words"):
            if w[4] == "Total" and w[0] < 80 and w[1] > y_min + 20:
                y_max = w[1] - 1; break
        table = _extract_coord_table(page, y_min, y_max, column_anchors,
                                     x_country_max=200.0, y_tol=5.0)
        for entry in table:
            iso = _to_iso3(entry["country"])
            if not iso:
                continue
            cv = entry["cols"]
            prod, taxes, roy, fees, bonus = cv["production"], cv["taxes"], cv["royalties"], cv["fees"], cv["bonuses"]
            infra, total = cv["infra"], cv["total"]
            # Validate: total should approximately equal sum of components.
            comp_sum = prod + taxes + roy + fees + bonus + infra
            if total > 0 and abs(comp_sum - total) > 0.5 * max(total, 1):
                continue   # parse looks bad; skip row
            if total == 0 and comp_sum == 0:
                continue
            # BP USD millions
            rows.append({
                "hq_iso3": "GBR", "source_iso3": iso, "year": year,
                "value_usd": (total or comp_sum) * 1e6,
                "operator_name": "BP", "doc_source": path.name,
                "pre_profit": (prod + roy + bonus + fees) * 1e6,
                "post_profit": taxes * 1e6,
                "equity": 0.0,
                "fee": infra * 1e6,
            })
        break   # use first qualifying page
    return rows


def parse_total_urd(path: Path) -> list[dict]:
    """TotalEnergies URD has Ch. 9.3 'Report on payments made to governments'
    with a country × payment-type table. Currency: USD thousands.

    Layout differs across years:
      - 2016-2021 URDs: 8 columns
          Country, Taxes, Royalties, License fees, License bonuses, Dividends,
          Infrastructure improvements, Production entitlements, Total.
      - 2022+ URDs: 10 columns — "Taxes" is split into
          Income taxes, Other Taxes, Taxes (Total), Royalties, License fees,
          License bonuses, Dividends, Infrastructure improvements,
          Production entitlements, Total of Payments.

    We use coordinate-based extraction and detect column anchors from the
    header words, so both layouts parse correctly."""
    doc = fitz.open(path)
    rows = []
    # Find URD fiscal year from filename or first pages.
    yr_match = None
    for pn in range(min(5, doc.page_count)):
        t = doc[pn].get_text()
        m = re.search(r"\b(20\d{2})\b\s*(?:Registration|URD|Universal)", t, re.I)
        if m:
            yr_match = int(m.group(1)); break
        m2 = re.search(r"Universal Registration Document\s*(20\d{2})", t)
        if m2:
            yr_match = int(m2.group(1)); break
    if yr_match is None:
        m = re.search(r"(20\d{2})", path.name)
        yr_match = int(m.group(1)) if m else 0
    fiscal_year = yr_match

    # Find table pages.
    table_pages = []
    for i in range(doc.page_count):
        t = doc[i].get_text()
        tl = t.lower()
        # Anchor on Ch 9.3 or the body text "payments made to governments" +
        # multiple recurring source countries.
        looks_like_table = (
            "reporting by country" in tl
            or ("payments made to governments" in tl and "algeria" in tl)
            or ("9.3" in t and "payments" in tl and "royalt" in tl)
        )
        if not looks_like_table:
            continue
        n_countries = sum(1 for c in
                          ["Algeria","Angola","Mozambique","Iraq","Nigeria",
                           "Argentina","Russia","Iran","Bolivia","Brunei",
                           "Norway","Indonesia","Kazakhstan"] if c in t)
        if n_countries >= 4:
            table_pages.append(i)
    if not table_pages:
        return rows

    for page_idx in table_pages:
        page = doc[page_idx]
        # Detect column anchors from header word right-edges.
        # Header tokens to find — match case-insensitively. Some 2022+ headers
        # split multi-word columns onto separate lines so we look for the
        # rightmost word of each column label.
        anchors = {}
        header_y_max = None
        # Targets are the distinctive last-words of each column header.
        # 2016-2021: Taxes, Royalties, fees, bonuses, Dividends, improvements, entitlements, Total
        # 2022+:    taxes (Income), Taxes (Other), Total (Taxes), Royalties, fees, bonuses, Dividends, improvements, entitlements, Payments (Total of Payments)
        # We rely on the FIRST occurrence of each word from top of page.
        targets = ["royalties", "fees", "bonuses", "dividends",
                   "improvements", "entitlements", "total", "payments"]
        words = page.get_text("words")
        # Limit to top ~30% of page for header detection.
        top_y = page.rect.height * 0.45
        for w in words:
            if w[1] > top_y:
                continue
            wl = w[4].lower().strip(",;:.()")
            if wl in targets and wl not in anchors:
                anchors[wl] = w[2]
                header_y_max = max(header_y_max or 0, w[3])
        # Need at least the core columns (royalties + entitlements + total).
        if "royalties" not in anchors or "entitlements" not in anchors:
            continue
        if "payments" not in anchors and "total" not in anchors:
            continue
        # Also detect "Taxes" anchors. In 2022+ there are three: Income taxes,
        # Other Taxes, Taxes (Total). We use the LAST taxes word before
        # royalties (= Taxes Total column).
        tax_anchors = []
        for w in words:
            if w[1] > top_y:
                continue
            if w[4].lower().strip(",;:.()") == "taxes" and w[2] < anchors["royalties"]:
                tax_anchors.append(w[2])
        if not tax_anchors:
            continue
        tax_x = max(tax_anchors)   # rightmost taxes header = Taxes Total
        column_anchors = {
            "taxes":      tax_x,
            "royalties":  anchors["royalties"],
            "lic_fees":   anchors.get("fees", anchors["royalties"] + 35),
            "lic_bonus":  anchors.get("bonuses", anchors["royalties"] + 70),
            "dividends":  anchors.get("dividends", anchors["royalties"] + 105),
            "infra":      anchors.get("improvements", anchors["royalties"] + 140),
            "production": anchors["entitlements"],
            "total":      anchors.get("payments", anchors.get("total")),
        }
        # Y range: from below header to end of page (multi-page tables possible).
        y_min = header_y_max + 4
        y_max = page.rect.height
        table = _extract_coord_table(page, y_min, y_max, column_anchors,
                                     x_country_max=180.0, y_tol=5.0)
        for entry in table:
            iso = _to_iso3(entry["country"])
            if not iso:
                continue
            cv = entry["cols"]
            taxes, roy, lic_fee, lic_bonus, divs, infra, prod, total = (
                cv["taxes"], cv["royalties"], cv["lic_fees"], cv["lic_bonus"],
                cv["dividends"], cv["infra"], cv["production"], cv["total"],
            )
            comp = taxes + roy + lic_fee + lic_bonus + divs + infra + prod
            if total > 0 and abs(comp - total) > 0.5 * max(total, 1):
                continue
            if total == 0 and comp == 0:
                continue
            rows.append({
                "hq_iso3": "FRA", "source_iso3": iso, "year": fiscal_year,
                "value_usd": (total or comp) * 1000,
                "operator_name": "TotalEnergies", "doc_source": path.name,
                "pre_profit": (roy + lic_fee + lic_bonus + prod) * 1000,
                "post_profit": taxes * 1000,
                "equity": divs * 1000,
                "fee": infra * 1000,
            })
    return rows


def parse_shell_p2g(path: Path, year: int) -> list[dict]:
    """Shell P2G report. Column structure essentially identical to BP:
    Country, Production Entitlement, Taxes, Royalties, Bonuses, Fees,
    Infrastructure Improvements, Total. Currency is reported in raw USD
    (not thousands or millions) in the 2018+ reports. Earlier reports may
    use USD millions — we detect scale from a plausibility check."""
    doc = fitz.open(path)
    rows = []
    for i in range(doc.page_count):
        page = doc[i]
        t = page.get_text()
        tl = t.lower()
        header_present = all(h in tl for h in
                             ("production", "entitlement", "taxes", "royalties",
                              "fees", "bonuses", "infrastructure", "total"))
        if not header_present:
            continue
        country_hits = sum(1 for c in
                           ("Norway", "Brunei", "Iraq", "Kazakhstan", "Malaysia",
                            "Nigeria", "Oman", "Trinidad")
                           if c in t)
        if country_hits < 3:
            continue
        anchors = {}
        header_y_max = None
        header_targets = {"entitlement", "entitlements", "taxes", "royalties",
                          "fees", "bonuses", "improvements", "total"}
        for w in page.get_text("words"):
            if w[1] > 280:
                continue
            lower = w[4].lower().strip(",;:.()")
            if lower in header_targets and lower not in anchors:
                anchors[lower] = w[2]
                header_y_max = max(header_y_max or 0, w[3])
        prod_key = "entitlement" if "entitlement" in anchors else "entitlements"
        if prod_key not in anchors or "total" not in anchors:
            continue
        column_anchors = {
            "production": anchors[prod_key],
            "taxes":      anchors.get("taxes", anchors[prod_key] + 50),
            "royalties":  anchors.get("royalties", anchors[prod_key] + 100),
            "bonuses":    anchors.get("bonuses", anchors[prod_key] + 150),
            "fees":       anchors.get("fees", anchors[prod_key] + 200),
            "infra":      anchors.get("improvements", anchors[prod_key] + 250),
            "total":      anchors["total"],
        }
        y_min = header_y_max + 2
        y_max = page.rect.height
        table = _extract_coord_table(page, y_min, y_max, column_anchors,
                                     x_country_max=180.0, y_tol=5.0)
        for entry in table:
            iso = _to_iso3(entry["country"])
            if not iso:
                continue
            cv = entry["cols"]
            prod, taxes, roy, bonus, fees, infra, total = (
                cv["production"], cv["taxes"], cv["royalties"],
                cv["bonuses"], cv["fees"], cv["infra"], cv["total"],
            )
            comp = prod + taxes + roy + bonus + fees + infra
            if total > 0 and abs(comp - total) > 0.5 * max(total, 1):
                continue
            if total == 0 and comp == 0:
                continue
            # Shell reports in raw USD (e.g. 1,331,302,546 for Norway). Detect
            # scale: if max single-column value > 1e7, assume raw USD (no scale);
            # else assume USD thousands.
            scale = 1.0 if max(abs(prod), abs(taxes), abs(roy), abs(total)) > 1e7 else 1000.0
            rows.append({
                "hq_iso3": "NLD" if year <= 2021 else "GBR",   # Royal Dutch Shell → Shell plc 2022
                "source_iso3": iso, "year": year,
                "value_usd": (total or comp) * scale,
                "operator_name": "Shell", "doc_source": path.name,
                "pre_profit": (prod + roy + bonus + fees) * scale,
                "post_profit": taxes * scale,
                "equity": 0.0,
                "fee": infra * scale,
            })
        break
    return rows


def parse_equinor_p2g(path: Path, year: int) -> list[dict]:
    """Equinor (NOR HQ) — 'Payments to governments per country' table.
    Currency: USD million. Columns: Country, Taxes, Royalties, Fees, Bonuses,
    Host government entitlements (USD million), Host government entitlements
    (mmboe — volume, skipped), Total (value).
    Multiple Equinor PDFs ALSO have a contextual-info table (Investments /
    Revenues / Cost / Equity production volume) that we must NOT confuse with
    the payments table — anchor on the unique "host government entitlements"
    column header which only appears in the payments table."""
    doc = fitz.open(path)
    rows = []
    for i in range(doc.page_count):
        page = doc[i]
        t = page.get_text()
        tl = t.lower()
        # Anchor: needs "Host government" + "entitlement" (terms may be on
        # different lines in the PDF text) + multiple Equinor source countries.
        if "host government" not in tl or "entitlement" not in tl:
            continue
        country_hits = sum(1 for c in
                           ("Algeria", "Angola", "Argentina", "Azerbaijan", "Brazil",
                            "Canada", "Libya", "Nigeria", "Norway", "USA",
                            "United Kingdom")
                           if c in t)
        if country_hits < 3:
            continue
        # Text-based extraction: split into lines, scan each country line plus 7 following numeric lines.
        # Equinor's PDF text places one cell per line.
        lines = [ln.strip() for ln in t.split("\n") if ln.strip()]
        for j, line in enumerate(lines):
            iso = _to_iso3(line)
            if not iso:
                continue
            # Country must be the START of a data row (next lines should be numbers/dashes)
            nums = []
            for k in range(j + 1, min(j + 9, len(lines))):
                v = _parse_amount(lines[k])
                if v is None:
                    break
                nums.append(v)
            if len(nums) < 6:
                continue
            # Pick first 7 numbers — [taxes, royalties, fees, bonuses, entitlements_usd, entitlements_mmboe, total]
            taxes, roy, fees, bonus, entitle, mmboe, total = (
                nums + [0.0] * 7
            )[:7]
            # Validate: components (excluding mmboe) should sum to ≈ total
            comp = taxes + roy + fees + bonus + entitle
            if total > 0 and abs(comp - total) > 0.5 * max(total, 1):
                continue
            if total == 0 and comp == 0:
                continue
            scale = 1e6   # USD millions
            rows.append({
                "hq_iso3": "NOR", "source_iso3": iso, "year": year,
                "value_usd": (total or comp) * scale,
                "operator_name": "Equinor", "doc_source": path.name,
                "pre_profit": (roy + fees + bonus + entitle) * scale,
                "post_profit": taxes * scale,
                "equity": 0.0, "fee": 0.0,
            })
        if rows:
            break
    return rows


def parse_repsol_p2g(path: Path, year: int) -> list[dict]:
    """Repsol (ESP HQ) — Spanish-mandated P2G. Currency: EUR million.
    Columns: Country, Taxes, Production entitlement, License fees & rentals,
    Other, TOTAL. The data is organised by continent (Asia, Europe, Latin
    America, Africa, North America) with subtotal-style continent rows that
    we must NOT confuse with country rows."""
    doc = fitz.open(path)
    rows = []
    CONTINENTS = {"asia", "europe", "latin america", "africa", "north america",
                  "oceania", "north of africa", "rest of europe"}
    for i in range(doc.page_count):
        page = doc[i]
        t = page.get_text()
        tl = t.lower()
        # Need a payments-by-country table. "Production entitlement" can be
        # split across lines so we just need both words on the page.
        if "production" not in tl or "entitlement" not in tl or "total" not in tl:
            continue
        country_hits = sum(1 for c in
                           ("Bolivia", "Brazil", "Algeria", "Libya", "Indonesia",
                            "Norway", "Trinidad", "Peru", "Venezuela", "Spain", "USA")
                           if c in t)
        if country_hits < 3:
            continue
        lines = [ln.strip() for ln in t.split("\n") if ln.strip()]
        for j, line in enumerate(lines):
            # Skip continent group headers
            if line.lower() in CONTINENTS:
                continue
            iso = _to_iso3(line)
            if not iso:
                continue
            nums = []
            for k in range(j + 1, min(j + 7, len(lines))):
                v = _parse_amount(lines[k])
                if v is None:
                    break
                nums.append(v)
            if len(nums) < 4:
                continue
            taxes, prod, lic_fees, other, total = (nums + [0.0] * 5)[:5]
            comp = taxes + prod + lic_fees + other
            if total > 0 and abs(comp - total) > 0.5 * max(total, 1):
                continue
            if total == 0 and comp == 0:
                continue
            EUR_TO_USD = 1.10
            scale = 1e6 * EUR_TO_USD   # EUR millions → USD
            rows.append({
                "hq_iso3": "ESP", "source_iso3": iso, "year": year,
                "value_usd": (total or comp) * scale,
                "operator_name": "Repsol", "doc_source": path.name,
                "pre_profit": (prod + lic_fees + other) * scale,
                "post_profit": taxes * scale,
                "equity": 0.0, "fee": 0.0,
            })
        if rows:
            break
    return rows


def parse_antofagasta_p2g(path: Path, year: int) -> list[dict]:
    """Antofagasta (GBR HQ) — UK statutory P2G covering Chilean copper mining.
    Currency: raw USD (not millions or thousands). Only 1-2 source countries
    typically (Chile + USA). Layout is essentially identical to BP P2G but
    with raw USD values and very few countries — too few for the 3-country
    threshold in parse_bp_p2g."""
    doc = fitz.open(path)
    rows = []
    for i in range(doc.page_count):
        page = doc[i]
        t = page.get_text()
        tl = t.lower()
        if not all(h in tl for h in
                   ("production", "entitlement", "taxes", "royalties",
                    "fees", "bonuses", "total")):
            continue
        # Only Chile + maybe USA, accept 1+ country
        if "Chile" not in t:
            continue
        # Coord-based extraction with looser threshold
        anchors = {}
        header_y_max = None
        header_targets = {"entitlement", "entitlements", "taxes", "royalties",
                          "fees", "bonuses", "improvements", "total"}
        for w in page.get_text("words"):
            if w[1] > page.rect.height * 0.55:
                continue
            lower = w[4].lower().strip(",;:.()")
            if lower in header_targets and lower not in anchors:
                anchors[lower] = w[2]
                header_y_max = max(header_y_max or 0, w[3])
        prod_key = "entitlement" if "entitlement" in anchors else "entitlements"
        if prod_key not in anchors or "total" not in anchors:
            continue
        column_anchors = {
            "production": anchors[prod_key],
            "taxes":      anchors.get("taxes", anchors[prod_key] + 50),
            "royalties":  anchors.get("royalties", anchors[prod_key] + 100),
            "dividends":  anchors.get("dividends", anchors[prod_key] + 150),
            "bonuses":    anchors.get("bonuses", anchors[prod_key] + 200),
            "fees":       anchors.get("fees", anchors[prod_key] + 250),
            "infra":      anchors.get("improvements", anchors[prod_key] + 300),
            "total":      anchors["total"],
        }
        y_min = header_y_max + 2
        table = _extract_coord_table(page, y_min, page.rect.height, column_anchors,
                                     x_country_max=200.0, y_tol=5.0)
        for entry in table:
            iso = _to_iso3(entry["country"])
            if not iso:
                continue
            cv = entry["cols"]
            prod, taxes, roy, divs, bonus, fees, infra, total = (
                cv["production"], cv["taxes"], cv["royalties"], cv["dividends"],
                cv["bonuses"], cv["fees"], cv["infra"], cv["total"],
            )
            comp = prod + taxes + roy + divs + bonus + fees + infra
            if total > 0 and abs(comp - total) > 0.5 * max(total, 1):
                continue
            if total == 0 and comp == 0:
                continue
            # Antofagasta raw USD (no thousand/million scaling)
            rows.append({
                "hq_iso3": "GBR", "source_iso3": iso, "year": year,
                "value_usd": total or comp,
                "operator_name": "Antofagasta", "doc_source": path.name,
                "pre_profit": prod + roy + bonus + fees,
                "post_profit": taxes,
                "equity": divs,
                "fee": infra,
            })
        if rows:
            break
    return rows


def parse_eu_p2g(path: Path, year: int, hq_iso3: str, operator_name: str,
                 currency_factor: float = 1e6, fx_to_usd: float = 1.0,
                 country_hints: tuple = ("Angola", "Norway", "Brazil", "Nigeria",
                                          "Algeria", "Libya", "UK", "Indonesia",
                                          "Australia", "Chile", "Peru", "DRC")) -> list[dict]:
    """Generic parser for UK/EU statutory Payments-to-Governments reports.
    Same column structure as BP but with flexible column-anchor detection
    so it tolerates Equinor's "Host government entitlements", Repsol's
    "Production entitlements", Rio Tinto's "Taxes paid" headers, etc.

    Args:
        currency_factor: scale factor to convert from reported unit to USD.
            E.g. 1e6 for "USD million" (default), 1e3 for "USD thousands",
            1.0 for raw USD.
        fx_to_usd: secondary FX conversion (e.g. 1.10 for EUR→USD, 1/18 for ZAR→USD).
        country_hints: list of country names to anchor table detection — need
            ≥3 of these on a page for it to be considered a candidate.
    """
    doc = fitz.open(path)
    rows = []
    for i in range(doc.page_count):
        page = doc[i]
        t = page.get_text()
        tl = t.lower()
        # Need at least Taxes + Royalties + a third payment-type header AND multiple countries.
        if not ("royalt" in tl and "taxes" in tl):
            continue
        country_hits = sum(1 for c in country_hints if c in t)
        if country_hits < 3:
            continue
        # Detect column anchors. Targets are payment-type header words.
        anchors = {}
        header_y_max = None
        targets = {"entitlements", "entitlement", "taxes", "royalties", "fees",
                   "bonuses", "improvements", "dividends", "infrastructure",
                   "total", "value"}
        for w in page.get_text("words"):
            if w[1] > page.rect.height * 0.55:
                continue
            lower = w[4].lower().strip(",;:.()")
            if lower in targets and lower not in anchors:
                anchors[lower] = w[2]
                header_y_max = max(header_y_max or 0, w[3])
        if "royalties" not in anchors or "taxes" not in anchors:
            continue
        if "total" not in anchors and "value" not in anchors:
            continue
        # Production / host-government entitlements goes by either name
        prod_x = anchors.get("entitlements") or anchors.get("entitlement")
        total_x = anchors.get("total") or anchors.get("value")
        column_anchors = {
            "taxes":      anchors["taxes"],
            "royalties":  anchors["royalties"],
            "fees":       anchors.get("fees", anchors["royalties"] + 30),
            "bonuses":    anchors.get("bonuses", anchors["royalties"] + 60),
            "infra":      anchors.get("improvements", anchors["royalties"] + 90),
            "production": prod_x or (anchors["royalties"] + 120),
            "total":      total_x,
        }
        y_min = header_y_max + 4 if header_y_max else 0
        y_max = page.rect.height
        table = _extract_coord_table(page, y_min, y_max, column_anchors,
                                     x_country_max=170.0, y_tol=5.0)
        for entry in table:
            iso = _to_iso3(entry["country"])
            if not iso:
                continue
            cv = entry["cols"]
            taxes, roy, fees, bonus, infra, prod, total = (
                cv["taxes"], cv["royalties"], cv["fees"], cv["bonuses"],
                cv["infra"], cv["production"], cv["total"],
            )
            comp = taxes + roy + fees + bonus + infra + prod
            if total > 0 and abs(comp - total) > 0.5 * max(total, 1):
                continue
            if total == 0 and comp == 0:
                continue
            scale = currency_factor * fx_to_usd
            rows.append({
                "hq_iso3": hq_iso3, "source_iso3": iso, "year": year,
                "value_usd": (total or comp) * scale,
                "operator_name": operator_name, "doc_source": path.name,
                "pre_profit": (roy + fees + bonus + prod) * scale,
                "post_profit": taxes * scale,
                "equity": 0.0,
                "fee": infra * scale,
            })
        break
    return rows


def parse_glencore_p2g(path: Path, year: int) -> list[dict]:
    """Glencore P2G — 'Payments by countries' table on page 14-15 of recent
    reports. Columns: Country, Production Entitlements, Taxes on Income,
    Royalties, Fees, Infrastructure improvements, Total EU Transparency
    Directive, Customs/Import/..., Payroll taxes, Other taxes, Payments not in
    Sustainability, Total. Currency: US$ thousands. We extract the columns
    that align with the standard P2G categories."""
    doc = fitz.open(path)
    rows = []
    for i in range(doc.page_count):
        page = doc[i]
        t = page.get_text()
        tl = t.lower()
        # Anchor on the actual detail table: must have the column header words
        # AND multiple source countries on the same page. (Page 1 / contents page
        # often mentions "Payments by countries" but doesn't have the table.)
        # 2016-2020 reports have a simple table (no separate Total column).
        # 2021 reports add "Total EU Transparency Directive"; 2022+ use
        # "UK Transparency Requirements". We require the core data columns
        # and treat the optional total as a marker for the rightmost anchor.
        header_needed = ("entitlements" in tl and "royalties" in tl
                        and "infrastructure" in tl)
        if not header_needed:
            continue
        country_hits = sum(1 for c in
                           ("Australia", "Democratic Republic", "Kazakhstan",
                            "Peru", "Chile", "South Africa", "Colombia",
                            "Argentina", "Bolivia")
                           if c in t)
        if country_hits < 4:
            continue
        # Detect column anchors from header word right-edges (top portion of page).
        anchors = {}
        header_y_max = None
        words = page.get_text("words")
        targets = {"entitlements", "income", "royalties", "fees",
                   "improvements", "directive", "requirements", "total"}
        for w in words:
            if w[1] > page.rect.height * 0.55:
                continue
            wl = w[4].lower().strip(",;:.()")
            if wl in targets and wl not in anchors:
                anchors[wl] = w[2]
                header_y_max = max(header_y_max or 0, w[3])
        # Total anchor: prefer "Directive" (EU 2021) or "Requirements" (UK
        # 2022+); older reports have no separate Total column — set anchor
        # past "improvements" so any numbers there bin as "infra" (we'll
        # synthesise total from component sum).
        total_anchor = anchors.get("directive") or anchors.get("requirements")
        if total_anchor is None:
            if "improvements" not in anchors:
                continue
            total_anchor = anchors["improvements"] + 80   # virtual column
        column_anchors = {
            "production": anchors.get("entitlements", total_anchor - 200),
            "taxes":      anchors.get("income", total_anchor - 150),
            "royalties":  anchors.get("royalties", total_anchor - 100),
            "fees":       anchors.get("fees", total_anchor - 60),
            "infra":      anchors.get("improvements", total_anchor - 30),
            "total":      total_anchor,
        }
        y_min = header_y_max + 4 if header_y_max else 0
        y_max = page.rect.height
        table = _extract_coord_table(page, y_min, y_max, column_anchors,
                                     x_country_max=170.0, y_tol=5.0)
        for entry in table:
            iso = _to_iso3(entry["country"])
            if not iso:
                continue
            cv = entry["cols"]
            prod, taxes, roy, fees, infra, total = (
                cv["production"], cv["taxes"], cv["royalties"],
                cv["fees"], cv["infra"], cv["total"],
            )
            comp = prod + taxes + roy + fees + infra
            if total > 0 and abs(comp - total) > 0.5 * max(total, 1):
                continue
            if total == 0 and comp == 0:
                continue
            rows.append({
                "hq_iso3": "CHE", "source_iso3": iso, "year": year,
                "value_usd": (total or comp) * 1000,
                "operator_name": "Glencore", "doc_source": path.name,
                "pre_profit": (prod + roy + fees) * 1000,
                "post_profit": taxes * 1000,
                "equity": 0.0,
                "fee": infra * 1000,
            })
        break
    return rows


def parse_vale_ttr(path: Path, year_label: int) -> list[dict]:
    """Vale Tax Transparency Reports — multi-country tax-borne table.
    Columns: Corporate Income Tax, Tax on mining, Payroll taxes, Tax on products and services, Other taxes, Total.
    Currency: USD thousands."""
    doc = fitz.open(path)
    rows = []
    for i in range(doc.page_count):
        t = doc[i].get_text()
        if ("Brazil" in t and "Indonesia" in t and "Mozambique" in t
            and ("Tax borne" in t or "Corporate Income Tax" in t or "Corporate income tax" in t)):
            for cname, iso in _NAME_TO_ISO3.items():
                for m in re.finditer(rf"(?:^|\n){re.escape(cname)}\s*\n", t):
                    seg = t[m.end():m.end() + 400]
                    # 6 columns: CIT, Tax on mining, Payroll, Tax on products, Other, Total
                    nums = re.findall(r"\(\s*[\d,]+\s*\)|[\d,]+(?:\.\d+)?|‐|–|—|-", seg)[:6]
                    if len(nums) < 5:
                        continue
                    cols = [_parse_amount(n) for n in nums]
                    if any(c is None for c in cols[:5]):
                        continue
                    cit, mining, payroll, products, other = cols[:5]
                    total = cols[5] if len(cols) > 5 else (cit + mining + payroll + products + other)
                    if total == 0 and all(c == 0 for c in cols[:5]):
                        continue
                    rows.append({
                        "hq_iso3": "BRA", "source_iso3": iso, "year": year_label,
                        "value_usd": total * 1000,
                        "operator_name": "Vale", "doc_source": path.name,
                        "pre_profit": mining * 1000,   # mining royalty / production-based tax
                        "post_profit": cit * 1000,
                        "equity": 0.0,
                        "fee": (products + other) * 1000,
                    })
            break
    return rows


def parse_sasol_tax_report(path: Path, year: int) -> list[dict]:
    """Sasol Tax Reports — country-by-country tax & royalty payments.
    Sasol's primary operations are South Africa, Mozambique (Pande/Temane gas + ROMPCO pipeline)."""
    doc = fitz.open(path)
    rows = []
    for i in range(doc.page_count):
        t = doc[i].get_text()
        if "Mozambique" in t and ("South Africa" in t or "Republic of South Africa" in t):
            # Sasol Tax Reports typically have a table with countries and Tax/Royalty/PAYE columns
            for cname, iso in _NAME_TO_ISO3.items():
                for m in re.finditer(rf"(?:^|\n){re.escape(cname)}\s*\n", t):
                    seg = t[m.end():m.end() + 300]
                    nums = re.findall(r"\(\s*[\d,]+\s*\)|[\d,]+(?:\.\d+)?|–|—|-", seg)[:5]
                    if len(nums) < 2:
                        continue
                    cols = [_parse_amount(n) for n in nums]
                    if any(c is None for c in cols[:2]):
                        continue
                    # Best-effort attribution; column layout varies across years
                    total = sum(c for c in cols if c is not None)
                    if total <= 0:
                        continue
                    # ZAR millions → USD (~18 ZAR/USD avg 2016-22)
                    ZAR_TO_USD = 1/18
                    rows.append({
                        "hq_iso3": "ZAF", "source_iso3": iso, "year": year,
                        "value_usd": total * 1e6 * ZAR_TO_USD,
                        "operator_name": "Sasol", "doc_source": path.name,
                        "pre_profit": 0.5 * total * 1e6 * ZAR_TO_USD,   # estimate
                        "post_profit": 0.5 * total * 1e6 * ZAR_TO_USD,
                        "equity": 0.0, "fee": 0.0,
                    })
            break
    return rows


def parse_aramco_ar(path: Path, year: int) -> list[dict]:
    """Saudi Aramco AR has SAU as single source country (essentially all Aramco income is from SAU).
    Income statement shows Royalties + Income taxes; we have the SA-domestic flow."""
    doc = fitz.open(path)
    rows = []
    # Aramco operates almost exclusively in Saudi Arabia upstream — single source country
    # Extract from income statement (the page we already parsed in script 8 work)
    for i in range(doc.page_count):
        t = doc[i].get_text()
        if "Royalties and other taxes" in t and "Income taxes and zakat" in t and "USD" in t:
            # Extract USD column values (skip SAR columns)
            for m in re.finditer(r"Royalties and other taxes\s*\n([\d,()]+)\s*\n([\d,()]+)\s*\n([\d,()]+)\s*\n([\d,()]+)", t):
                # 4 numbers = SAR_cur, SAR_prior, USD_cur, USD_prior
                roy_usd = _parse_amount(m.group(3))
                roy_prior_usd = _parse_amount(m.group(4))
                if roy_usd is None: continue
                rows.append({
                    "hq_iso3": "SAU", "source_iso3": "SAU", "year": year,
                    "value_usd": roy_usd * 1e6,   # USD millions
                    "operator_name": "Saudi Aramco", "doc_source": path.name,
                    "pre_profit": roy_usd * 1e6,
                    "post_profit": 0.0, "equity": 0.0, "fee": 0.0,
                })
                break
            break
    return rows


# ── Main extraction loop ────────────────────────────────────────────────────
def main():
    """Iterate the flat operator-document folder using consistent
    `{HQISO3}_{Operator}_{DocType}_{year}.pdf` naming (set up 2026-07-21;
    replaces the 2026-05-17 `{operator_slug}_{report_type}_{year}` scheme).
    All operator P2G/tax/AR documents live directly under
    `data/raw/resources/resource_profits_manual_sources/company/`."""
    rows = []
    flat = SOURCES   # files live directly here now

    def each_year(prefix, suffix=".pdf", years=range(2016, 2026)):
        """Yield (year, path) for prefix_{year}.pdf files that exist."""
        for yr in years:
            p = flat / f"{prefix}{yr}{suffix}"
            if p.exists():
                yield yr, p

    # ── Eni P2G (eni_p2g_YYYY.pdf, 2016-2024 minus 2020) ──
    for yr, p in each_year("ITA_Eni_P2G_"):
        r = parse_eni_p2g(p, yr)
        rows.extend(r)
        print(f"  Eni {yr}: {len(r)} country rows from {p.name}")

    # ── BP P2G ──
    for yr, p in each_year("GBR_BP_P2G_"):
        r = parse_bp_p2g(p, yr)
        rows.extend(r)
        print(f"  BP {yr}: {len(r)} country rows from {p.name}")

    # ── Shell P2G (2016-2025 minus 2024) ──
    for yr, p in each_year("GBR_Shell_P2G_"):
        r = parse_shell_p2g(p, yr)
        rows.extend(r)
        print(f"  Shell {yr}: {len(r)} country rows from {p.name}")

    # ── TotalEnergies URD (Ch. 9.3 P2G inside the URD, 2016-2025) ──
    for yr, p in each_year("FRA_TotalEnergies_URD_"):
        r = parse_total_urd(p)
        rows.extend(r)
        yr_actual = r[0]["year"] if r else "?"
        print(f"  TotalEnergies URD {p.name}: {len(r)} country rows (fiscal year {yr_actual})")

    # ── Glencore P2G (2016-2025) ──
    for yr, p in each_year("CHE_Glencore_P2G_"):
        r = parse_glencore_p2g(p, yr)
        rows.extend(r)
        print(f"  Glencore {yr}: {len(r)} country rows from {p.name}")

    # ── Vale Tax Transparency Report (BRA HQ; 2019-2023 + PT 2024) ──
    for yr, p in each_year("BRA_Vale_TTR_", years=range(2019, 2025)):
        r = parse_vale_ttr(p, yr)
        rows.extend(r)
        print(f"  Vale TTR {yr}: {len(r)} country rows from {p.name}")

    # ── Vale Swiss-format P2G (2022-2024) ──
    for yr, p in each_year("BRA_Vale_P2G_", years=range(2022, 2025)):
        r = parse_vale_ttr(p, yr)   # same column structure as TTR
        rows.extend(r)
        print(f"  Vale P2G {yr}: {len(r)} country rows from {p.name}")

    # ── Sasol Tax Report (ZAF HQ) ──
    for yr, p in each_year("ZAF_Sasol_Tax_", years=range(2024, 2026)):
        r = parse_sasol_tax_report(p, yr)
        rows.extend(r)
        print(f"  Sasol {yr}: {len(r)} country rows from {p.name}")

    # ── Saudi Aramco AR (SAU domestic) ──
    for yr, p in each_year("SAU_Aramco_AR_", years=range(2019, 2026)):
        r = parse_aramco_ar(p, yr)
        rows.extend(r)
        print(f"  Aramco {yr}: {len(r)} rows from {p.name}")

    # ── New operators (2026-05-17): EU/UK statutory P2G reports — all share
    # the BP/Shell column structure (Taxes, Royalties, Fees, Bonuses, Production
    # entitlements, Infrastructure improvements, Total). The generic parser
    # auto-detects column anchors from header words so it tolerates minor
    # variations between operators.

    # ── Equinor (NOR) — 2022-2024 standalone P2G (2018-2020 are xlsx, not parsed)
    for yr, p in each_year("NOR_Equinor_P2G_", years=range(2022, 2025)):
        r = parse_equinor_p2g(p, yr)
        rows.extend(r)
        print(f"  Equinor {yr}: {len(r)} country rows from {p.name}")

    # ── Repsol (ESP) — 2016-2024, EUR millions
    for yr, p in each_year("ESP_Repsol_P2G_", years=range(2016, 2025)):
        r = parse_repsol_p2g(p, yr)
        rows.extend(r)
        print(f"  Repsol {yr}: {len(r)} country rows from {p.name}")

    # ── OMV (AUT) — 2018, 2021-2024
    for yr, p in each_year("AUT_OMV_P2G_", years=[2018, 2021, 2022, 2023, 2024]):
        r = parse_eu_p2g(p, yr, "AUT", "OMV",
                         country_hints=("Austria", "Norway", "New Zealand",
                                         "Kazakhstan", "Libya", "Malaysia", "Romania",
                                         "Tunisia", "Yemen", "Pakistan"))
        rows.extend(r)
        print(f"  OMV {yr}: {len(r)} country rows from {p.name}")

    # ── Antofagasta (GBR) — 2016-2024 (Chile mining, raw USD)
    for yr, p in each_year("GBR_Antofagasta_P2G_", years=range(2016, 2025)):
        r = parse_antofagasta_p2g(p, yr)
        rows.extend(r)
        print(f"  Antofagasta {yr}: {len(r)} country rows from {p.name}")

    # ── Rio Tinto (GBR/AUS) — 2016, 2018-2024 "Taxes paid" reports
    for yr, p in each_year("GBR_RioTinto_Tax_", years=[2016] + list(range(2018, 2025))):
        r = parse_eu_p2g(p, yr, "GBR", "Rio Tinto",
                         country_hints=("Australia", "Canada", "Mongolia", "South Africa",
                                         "Chile", "USA", "Madagascar", "France", "New Zealand"))
        rows.extend(r)
        print(f"  Rio Tinto {yr}: {len(r)} country rows from {p.name}")

    # ── Newmont (USA) — 2021-2024 Tax Contribution
    for yr, p in each_year("USA_Newmont_Tax_", years=range(2021, 2025)):
        r = parse_eu_p2g(p, yr, "USA", "Newmont",
                         country_hints=("USA", "Australia", "Ghana", "Peru",
                                         "Argentina", "Canada", "Mexico", "Suriname"))
        rows.extend(r)
        print(f"  Newmont {yr}: {len(r)} country rows from {p.name}")

    # ── First Quantum (CAN) — 2020-2024 ESTMA filings
    for yr, p in each_year("CAN_FirstQuantum_Tax_", years=range(2020, 2025)):
        r = parse_eu_p2g(p, yr, "CAN", "First Quantum",
                         country_hints=("Zambia", "Panama", "Mauritania", "Spain",
                                         "Turkey", "Australia", "Argentina", "Peru"))
        rows.extend(r)
        print(f"  First Quantum {yr}: {len(r)} country rows from {p.name}")

    # ── Write consolidated CSV ──
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["hq_iso3","source_iso3","year","value_usd",
                                          "pre_profit","post_profit","equity","fee",
                                          "operator_name","doc_source"])
        w.writeheader()
        for r in rows:
            # Skip rows where target is the operator's HQ itself (no foreign cross-border attribution)
            if r["source_iso3"] == r["hq_iso3"]:
                continue
            w.writerow(r)
    print(f"\nWrote {OUT}  ({len(rows):,} total rows)")
    # Summary per operator
    from collections import Counter
    by_op = Counter([r["operator_name"] for r in rows])
    print("\nRows per operator:")
    for op, n in by_op.most_common():
        print(f"  {op}: {n:,}")
    print(f"\nDistinct source countries covered: {len(set(r['source_iso3'] for r in rows if r['source_iso3']))}")


if __name__ == "__main__":
    main()
