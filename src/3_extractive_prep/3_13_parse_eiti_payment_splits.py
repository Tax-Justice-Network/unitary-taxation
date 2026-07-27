# %%
"""
3_13 — Parse EITI payment splits (pre/post-profit/equity).

Parse the standardised EITI Summary Data templates (sheet "Part 4 -
Government revenues": government receipts by revenue stream, GFS-classified)
into a per-(iso3, year) pre-profit / post-profit / equity split table. These
cover years the EITI *API* pull missed (the API predates several countries'
recent reports, e.g. Kazakhstan 2019/2020), so this fills those gaps.

Classification mirrors 3_31_pull_eiti_company_payments.py (`classify`):
royalty_like -> pre, cit -> post, equity -> equity, general/other -> dropped
(economy-wide, not extractive-specific profit sharing). Output fractions are
over pre+post+equity only.

Pipeline: Extractive prep, stage 3_13 — ingests the EITI payment-split product
(the third EITI ingest); feeds the 3_2x rent-combination stage.

Reads:
  data/raw/extractive/eiti_reports/<Country>/*Summary Data*.xlsx  — EITI Summary Data templates (Part 4)

Writes:
  data/intermediate/extractive/eiti_folder_summary_splits.csv     — iso3, year, total_usd,
      frac_pre_profit, frac_post_profit, frac_equity, n_streams, source_file

Usage:
  python 3_13_parse_eiti_payment_splits.py

Author: Alison Schultz.
Last updated: 2026-07-25.
"""
# %% MARK: 1. Setup
import os
import re
import sys
import unicodedata
import warnings

import pandas as pd

warnings.filterwarnings("ignore")
_SRC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SRC)
from _paths import RAW, EXT_INT  # noqa: E402

# %% MARK: 2. Classification config
# classification copied from 3_31_pull_eiti_company_payments.py (kept in sync); royalty_like->pre, cit->post,
# equity->equity, general->drop.
GFS_LABEL_TO_BUCKET = {
    "Ordinary taxes on income, profits and capital gains": "cit",
    "Extraordinary taxes on income, profits and capital gains": "cit",
    "From government participation (equity)": "equity",
    "Dividends": "equity",
    "From state-owned enterprises": "equity",
    "Delivered/paid to state-owned enterprise(s)": "equity",
    "Withdrawals from income of quasi-corporations": "equity",
    "Profits of natural resource export monopolies": "equity",
    "Sales of state's share of production or other revenue collected in kind": "equity",
    "Royalties": "royalty_like", "Bonuses": "royalty_like", "Licence fees": "royalty_like",
    "Other taxes payable by natural resource companies": "royalty_like",
    "Other rent payments": "royalty_like",
    "Compulsory transfers to government (infrastructure and other)": "royalty_like",
    "Production entitlements (in-kind or cash)": "royalty_like",
    "Production entitlement": "royalty_like",
    "Delivered/paid directly to government": "royalty_like",
    "Rent": "royalty_like", "Administrative fees for government services": "royalty_like",
    "Mandatory social expenditures": "royalty_like",
    "Infrastructure provisions and barter arrangements": "royalty_like",
}
_KW = [
    ("general", ("value added tax", "vat", "(tva)", "gst", "customs", "import dut", "douane", "excise",
                 "accise", "payroll", "social security", "social contribution", "personal income tax",
                 "pay as you earn", "(paye)", "property tax", "motor vehicle", "stamp dut", "fines", "penalt",
                 "amende", "co2 tax", "carbon tax", "emission tax", "pollution tax", "salaire", "sales tax",
                 "turnover tax", "registration fee", "trade tax",
                 # French: personal income tax & social contributions (excluded, not CIT)
                 "personnes physiques", "revenu des personnes", "irpp", "(its)", "assurance",
                 "cotisation", "timbre", "enregistrement")),
    ("cit", ("income, profits and capital", "income tax", "corporate tax", "corporation tax", "company tax",
             "profits tax", "profit tax", "petroleum profits tax", "supplemental petroleum tax", "windfall",
             "additional profit", "solidarity contribution", "impuesto a las ganancias",
             # French income/profit-tax GFS labels & stream names. "benefice" is the
             # distinctive token in every income/profit-tax GFS label ("Impôts …sur le
             # revenu, le bénéfice…"); "societe" catches "Impôt(s) sur les sociétés"
             # (robust to singular/plural and intervening words like "ordinaires").
             "benefice", "impot sur les societe", "impots sur les societe", "sur les societe",
             "bic", "impot sur le revenu des societe")),
    ("equity", ("dividend", "government participation", "state participation", "state-owned enterprise",
                "produced petroleum sold", "crude oil export sales", "profit oil", "share of profit",
                "production entitlement", "carried interest", "winstaandeel", "sdfi", "concessionary sale",
                "concession fee", "state's share",
                # French: participation de l'État / part de production / vente de la part de l'État
                "participation de l", "part de production", "part de l'etat", "part de l’etat",
                "part de l'état", "part de l’état", "vente de la part", "revenus de la propriete",
                "revenus de la propriété",
                # State production-share sold by the NOC (empty GFS label, spelled-out
                # English names): Nigeria federation crude, Norway SDFI, Indonesia PSC
                # lifting, Iraq state oil export -> all state's share of production.
                "direct financial interest", "federation crude", "sales of federation",
                "government lifting", "oil products export")),
    ("royalty_like", ("royalt", "redevance", "regalia", "bonus", "licence", "license", "permis", "permit",
                      "surface", "superficiaire", "rent", "loyers", "infrastructure", "training fund",
                      "redevance miniere", "ad valorem", "extraction tax", "severance", "exploration",
                      "exploitation", "administrative fee", "data fee", "mining fee",
                      # French: droits fixes / taxe d'extraction / patente miniere
                      "droits fixes", "droit fixe", "taxe d'extraction", "patente")),
]
BUCKET = {"royalty_like": "pre", "cit": "post", "equity": "equity"}
_ISO = {"Cote d_Ivoire": "CIV", "Democratic Republic of the Congo": "COD",
        "Republic of Congo": "COG", "Sao Tome and Principe": "STP",
        "United States of America": "USA", "United Kingdom": "GBR",
        "Central African Republic": "CAF", "Timor-Leste": "TLS"}


# %% MARK: 3. Classify and parse files
def _strip_accents(s):
    """Fold accents so unaccented keywords match accented French labels
    ('Impôt sur les sociétés' -> 'impot sur les societes')."""
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def classify(gfs_label, fallback_text=""):
    b = GFS_LABEL_TO_BUCKET.get((gfs_label or "").strip())
    if b:
        return b
    t = " " + _strip_accents((str(gfs_label or "") + " " + str(fallback_text or ""))) + " "
    for bucket, kws in _KW:
        if any(_strip_accents(k) in t for k in kws):
            return bucket
    # generic top-level "Taxes (11E)" with no finer match (e.g. a stream just
    # labelled "Taxes") — for extractives the dominant tax is income/profit tax,
    # so treat it as post rather than dropping it.
    if "taxes (11" in t or " 11e " in t:
        return "cit"
    return "other"


def _iso3(folder):
    if folder in _ISO:
        return _ISO[folder]
    try:
        import pycountry
        return pycountry.countries.lookup(folder).alpha_3
    except Exception:
        return None


def _pick_sheet(xl):
    """The 'Part 4 - Government revenues' sheet, in English or French templates."""
    for s in xl.sheet_names:
        low = s.lower()
        if "part 4" in low or "partie 4" in low:
            return s
    for s in xl.sheet_names:
        low = s.lower()
        if "government revenue" in low or "recettes de" in low:
            return s
    return None


def parse_file(path):
    """-> (total_usd, {pre,post,equity: value in file currency}, n_streams) or None.

    Handles both the English and the French EITI Summary Data templates. The
    French (and some 'EN') templates use 'Partie 4 - Recettes de l'État' /
    'GFS Niveau 1' / 'Nom du flux de revenus' / 'Valeur des revenus' instead of
    the English 'Part 4 - Government revenues' / 'GFS Level 1' / 'Revenue stream
    name' / 'Revenue value', so column/sheet/header detection is language-agnostic.
    """
    try:
        xl = pd.ExcelFile(path)
    except Exception:
        return None
    sheet = _pick_sheet(xl)
    if sheet is None:
        return None
    try:
        raw = pd.read_excel(path, sheet_name=sheet, header=None)
    except Exception:
        return None

    def _is_hdr(r):
        j = " ".join(str(x) for x in r).lower()
        return (("gfs level 1" in j or "gfs niveau 1" in j)
                and ("revenue stream" in j or "flux de revenu" in j))

    hdr = next((i for i, r in raw.iterrows() if _is_hdr(r)), None)
    if hdr is None:
        return None
    df = pd.read_excel(path, sheet_name=sheet, header=hdr)
    df.columns = [str(c).strip() for c in df.columns]

    def _find(cands):
        for c in df.columns:
            cl = c.lower()
            if any(k in cl for k in cands):
                return c
        return None

    vcol = _find(["revenue value", "valeur des revenus", "valeur des recettes"])
    scol = _find(["revenue stream name", "nom du flux de revenus"])
    gcols = [c for c in df.columns
             if c.startswith("GFS Level") or c.startswith("GFS Niveau")
             or "gfs classification" in c.lower() or "classification sfp" in c.lower()]
    if not vcol or not scol:
        return None
    df[vcol] = pd.to_numeric(df[vcol], errors="coerce")
    streams = df[df[vcol].notna() & (df[vcol] > 0)]
    buckets = {"pre": 0.0, "post": 0.0, "equity": 0.0}
    n = 0
    for _, r in streams.iterrows():
        gfs_txt = " ".join(str(r[c]) for c in gcols if pd.notna(r[c]))
        b = classify(gfs_txt, str(r[scol]))
        if b in BUCKET:
            buckets[BUCKET[b]] += float(r[vcol]); n += 1
    # Total in USD row (for magnitude)
    total_usd = None
    for _, r in raw.iterrows():
        cells = [str(x) for x in r]
        if any(("Total in USD" in c) or ("Total en USD" in c) for c in cells):
            nums = pd.to_numeric(pd.Series(r), errors="coerce").dropna()
            if len(nums):
                total_usd = float(nums.iloc[-1])
            break
    return total_usd, buckets, n


# %% MARK: 4. Run and write output
def main():
    base = RAW / "extractive/eiti_reports"
    rows = []
    for folder in sorted(os.listdir(base)):
        p = base / folder
        if not p.is_dir():
            continue
        iso = _iso3(folder)
        if not iso:
            continue
        for fn in os.listdir(p):
            if "summary data" not in fn.lower() or not fn.lower().endswith((".xlsx", ".xls")):
                continue
            m = re.search(r"\b(20[0-2]\d)\b", fn)
            if not m:
                continue
            year = int(m.group(1))
            res = parse_file(p / fn)
            if not res:
                continue
            total_usd, b, n = res
            tot = b["pre"] + b["post"] + b["equity"]
            if tot <= 0:
                continue
            rows.append(dict(iso3=iso, year=year, total_usd=round(total_usd or 0, 0),
                             frac_pre_profit=round(b["pre"] / tot, 4),
                             frac_post_profit=round(b["post"] / tot, 4),
                             frac_equity=round(b["equity"] / tot, 4),
                             n_streams=n, source_file=fn))
    out = pd.DataFrame(rows).sort_values(["iso3", "year"]).drop_duplicates(["iso3", "year"], keep="last")
    dest = EXT_INT / "eiti_folder_summary_splits.csv"
    out.to_csv(dest, index=False)
    print(f"wrote {dest}: {len(out)} (iso, year) splits, {out.iso3.nunique()} countries")
    print(out[out.year.between(2016, 2022)].to_string(index=False))


if __name__ == "__main__":
    main()
