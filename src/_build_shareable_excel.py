"""
Build a plain-language Excel of the baseline unitary-taxation results for
sharing (the numbers behind the paper's Table 2 — change in taxable profits by
formula — and Table 3 — change in tax revenue by formula, reported sample).

Reads the two table CSVs written by 7b_formula_results.py and writes a
formatted workbook with a Read-me sheet, one sheet per table, income-group
subtotal rows in bold, and a country-name index. TJN brand colours; numbers as
US$ million per year (yearly average 2016–2022 excl. 2020, constant 2025 USD).

Output: output/app/unitary_taxation_baseline_results.xlsx
Refresh after a pipeline rerun: `python _build_shareable_excel.py`.
Not part of the replication package (dissemination deliverable).
"""
import os
import sys
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_ROOT = Path(__file__).resolve().parent.parent
TABLES = _ROOT / "output" / "paper" / "main_text" / "tables"
OUT = _ROOT / "output" / "app" / "unitary_taxation_baseline_results.xlsx"

# TJN brand
GOLD = "FFD371"
TEAL = "45636C"
GREEN = "50805E"
INK = "26312F"
BAND = "F3F0E6"
WHITE = "FFFFFF"

SHEETS = [
    ("Taxable profits", "table2_taxable_profits_by_formula__reported_only.csv",
     "Change in taxable profits by apportionment formula",
     "How much taxable profit each country would gain (+) or lose (−) if "
     "multinationals' profits were reallocated to where their real activity is."),
    ("Tax revenue", "table3_tax_revenue_by_formula__reported_only.csv",
     "Change in tax revenue by apportionment formula",
     "The resulting change in each country's corporate tax revenue, valuing "
     "reallocated profit at statutory rates for gains and effective rates for losses."),
]

_thin = Side(style="thin", color="D9D5C8")
BORDER = Border(bottom=_thin)


def _is_heading(name):
    s = str(name).strip()
    return s == s.upper() and len(s) > 3 and any(ch.isalpha() for ch in s)


def _write_sheet(wb, title, csv_name, heading, blurb):
    p = TABLES / csv_name
    if not p.exists():
        print(f"  [skip] {csv_name} not found — run 7b_formula_results.py first")
        return False
    df = pd.read_csv(p)
    ws = wb.create_sheet(title)

    # title rows
    ws["A1"] = heading
    ws["A1"].font = Font(name="Calibri", size=14, bold=True, color=INK)
    ws["A2"] = blurb
    ws["A2"].font = Font(name="Calibri", size=10, italic=True, color="5B6B67")
    ws["A3"] = ("US$ million per year · yearly average 2016–2022 (2020 excluded) · "
                "constant 2025 USD · directly reported OECD country-by-country data")
    ws["A3"].font = Font(name="Calibri", size=9, color="93A19C")
    hdr_row = 5

    # header
    for j, col in enumerate(df.columns, start=1):
        c = ws.cell(row=hdr_row, column=j, value=str(col))
        c.font = Font(name="Calibri", size=10, bold=True, color=INK)
        c.fill = PatternFill("solid", fgColor=GOLD)
        c.alignment = Alignment(horizontal="left" if j == 1 else "right",
                                vertical="center", wrap_text=(j > 1))
        c.border = BORDER

    # body
    for i, (_, row) in enumerate(df.iterrows(), start=hdr_row + 1):
        heading_row = _is_heading(row.iloc[0])
        for j, val in enumerate(row, start=1):
            c = ws.cell(row=i, column=j)
            if isinstance(val, float) and pd.notna(val):
                c.value = round(val, 1)
                c.number_format = '#,##0.0'
            else:
                c.value = "" if (isinstance(val, float) and pd.isna(val)) else val
            c.alignment = Alignment(horizontal="left" if j == 1 else "right")
            if heading_row:
                c.font = Font(name="Calibri", size=10, bold=True, color=INK)
                c.fill = PatternFill("solid", fgColor=BAND)
            else:
                c.font = Font(name="Calibri", size=10, color=INK)

    # widths + freeze
    ws.column_dimensions["A"].width = 30
    for j in range(2, len(df.columns) + 1):
        ws.column_dimensions[get_column_letter(j)].width = 16
    ws.freeze_panes = f"B{hdr_row + 1}"
    ws.sheet_view.showGridLines = False
    print(f"  wrote sheet '{title}' ({len(df)} rows)")
    return True


def _readme(wb):
    ws = wb.create_sheet("Read me", 0)
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 100
    lines = [
        ("Unitary taxation — baseline results", 16, True, INK),
        ("Tax Justice Network", 11, False, TEAL),
        ("", 10, False, INK),
        ("What this shows", 12, True, INK),
        ("If multinational groups were taxed as single firms — their global profit shared "
         "out among countries in proportion to where their real activity (employees, sales, "
         "assets) actually is — how would each country's taxable profits and corporate tax "
         "revenue change? These are the paper's headline results.", 10, False, INK),
        ("", 10, False, INK),
        ("The two sheets", 12, True, INK),
        ("• Taxable profits — the change in each country's taxable profit base, by formula.", 10, False, INK),
        ("• Tax revenue — the resulting change in corporate tax revenue, by formula.", 10, False, INK),
        ("Each is shown for four apportionment formulas; 'Sales & employees' is the headline. "
         "The '(%)' columns express the change relative to the country's own current figures "
         "in the same data (see below).", 10, False, INK),
        ("", 10, False, INK),
        ("How to read the numbers", 12, True, INK),
        ("• Units: US$ million per year, averaged over 2016–2022 with 2020 excluded, in "
         "constant 2025 US dollars.", 10, False, INK),
        ("• A positive number means the country gains taxable profit / tax revenue; negative "
         "means it loses.", 10, False, INK),
        ("• Percentages compare with the country's OWN reported figures in the same OECD "
         "country-by-country data — the taxable-profit change against current positive "
         "reported profits, the tax-revenue change against the corporate income tax the "
         "sampled multinationals report paying there. They are NOT relative to a country's "
         "official total corporate tax revenue.", 10, False, INK),
        ("• UPPER-CASE rows are income-group subtotals; the countries below each belong to it.", 10, False, INK),
        ("", 10, False, INK),
        ("Coverage", 12, True, INK),
        ("Multinational groups with over €750 million in annual revenue that report country "
         "by country to tax authorities — roughly three-quarters of global multinational "
         "profit. Figures are NOT scaled up to the full population (the paper reports that "
         "scale-up separately). Directly reported data only, no imputation.", 10, False, INK),
        ("", 10, False, INK),
        ("Full method: the methodology note accompanying the paper. "
         "Estimates are research results, not forecasts.", 9, False, "93A19C"),
    ]
    for i, (text, size, bold, color) in enumerate(lines, start=1):
        c = ws.cell(row=i, column=1, value=text)
        c.font = Font(name="Calibri", size=size, bold=bold, color=color)
        c.alignment = Alignment(wrap_text=True, vertical="top")


def main():
    wb = Workbook()
    wb.remove(wb.active)   # drop default sheet
    any_written = False
    for title, csv_name, heading, blurb in SHEETS:
        any_written |= _write_sheet(wb, title, csv_name, heading, blurb)
    if not any_written:
        raise SystemExit("No source tables found — run 7b_formula_results.py first.")
    _readme(wb)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
