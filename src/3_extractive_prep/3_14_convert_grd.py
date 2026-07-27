# %%
"""
3_14 — Convert GRD (Government Revenue Dataset).

Convert the UNU-WIDER Government Revenue Dataset 2025 Excel (Merged sheet) to
a CSV with clean, explicit column names (total/resource/non-resource revenue
and tax lines by country x year).

Pipeline: Extractive prep, stage 3_14 — ingests the UNU-WIDER GRD; feeds the
3_2x rent-combination stage.

Reads:
  data/raw/resources/UNUWIDERGRD_2025.xlsx (sheet 'Merged')  — UNU-WIDER GRD 2025

Writes:
  data/intermediate/extractive/grd_resource_revenue.csv      — cleaned GRD panel

Usage:
  python 3_14_convert_grd.py

Author: Alison Schultz.
Last updated: 2026-07-25.
"""
# %% MARK: 1. Setup
import openpyxl, csv, os

from _paths import RAW, EXT_INT  # noqa: E402

# %% MARK: 2. Column names
col_names = [
    'identifier',                          # 0
    'general_govt_flag',                   # 1
    'source',                              # 2
    'country',                             # 3
    'region',                              # 4
    'income_group',                        # 5
    'gdp_lcu_mn',                          # 6
    'year',                                # 7
    'iso',                                 # 8
    'general_notes',                       # 9
    'caution1_accuracy',                   # 10
    'caution1_notes',                      # 11
    'caution2_resource_rev_significant',   # 12
    'caution3_resource_rev_marginal',      # 13
    'resource_revenue_notes',              # 14
    'caution4_social_contributions',       # 15
    'social_contributions_notes',          # 16
    'total_rev_incgrants_incsc',           # 17
    'total_rev_incgrants_exsc',            # 18
    'total_rev_exgrants_incsc',            # 19
    'total_rev_exgrants_exsc',             # 20
    'total_resource_rev',                  # 21
    'total_nonresource_rev_incsc',         # 22
    'taxes_incsc',                         # 23
    'taxes_exsc',                          # 24
    'resource_taxes',                      # 25
    'nonresource_tax_incsc',               # 26
    'nonresource_tax_exsc',                # 27
    'direct_taxes_incsc_incres',           # 28
    'direct_taxes_incsc_exres',            # 29
    'direct_taxes_exsc_incres',            # 30
    'direct_taxes_exsc_exres',             # 31
    'tax_income_profits_capgains_total',   # 32
    'tax_income_profits_capgains_resource',# 33
    'tax_income_profits_capgains_nonres',  # 34
    'pit',                                 # 35
    'cit_total',                           # 36
    'cit_resource',                        # 37
    'cit_nonresource',                     # 38
    'tax_payroll_workforce',               # 39
    'property_taxes',                      # 40
    'indirect_taxes_total',                # 41
    'indirect_taxes_resource',             # 42
    'indirect_taxes_nonresource',          # 43
    'tax_goods_services_total',            # 44
    'tax_goods_services_general_sales_vat',# 45
    'vat',                                 # 46
    'excises',                             # 47
    'tax_intl_trade_total',                # 48
    'tax_intl_trade_import',               # 49
    'tax_intl_trade_export',               # 50
    'other_taxes',                         # 51
    'nontax_rev_total',                    # 52
    'nontax_rev_resource',                 # 53
    'nontax_rev_nonresource',              # 54
    'social_contributions',                # 55
    'grants',                              # 56
]

# %% MARK: 3. Convert and write
wb = openpyxl.load_workbook(RAW / 'resources' / 'UNUWIDERGRD_2025.xlsx', read_only=True)
ws = wb['Merged']

outpath = EXT_INT / 'grd_resource_revenue.csv'   # processed from the GRD xlsx → intermediate
with open(outpath, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(col_names)
    for i, row in enumerate(ws.iter_rows(min_row=4, values_only=True)):
        vals = list(row)
        # Pad or trim to 57 columns
        while len(vals) < 57:
            vals.append('')
        writer.writerow(vals[:57])

print(f"Written to {outpath}")

# %% MARK: 4. Coverage stats
# Quick stats
import csv as csv2
with open(outpath, encoding='utf-8') as f:
    reader = csv2.DictReader(f)
    countries = set()
    years = set()
    res_count = 0
    for row in reader:
        countries.add(row['iso'])
        if row['year']:
            try:
                years.add(int(float(row['year'])))
            except:
                pass
        if row['total_resource_rev']:
            res_count += 1
    print(f"Countries: {len(countries)}")
    print(f"Year range: {min(years)}-{max(years)}")
    print(f"Rows with resource revenue: {res_count}")
