"""
Canonical column ordering for the cbcr_main_* datasets.

The ordering is intuitive for human inspection:
  1. Identifiers (parent / partner ISO codes, country names, year)
  2. Time-invariant country characteristics (region, income group, OECD, ...)
  3. Country macro (CIT rate, GDP, population, wages, health, tax revenue)
  4. CbCR primary variables (profit, taxes, revenues, employees, assets)
  5. Derived ETRs
  6. Logged variables (analytical helpers; only in script 1's wider output)
  7. Disaggregation metadata (is_distributed, distribution_source, ...)
  8. (extractives-only) Resource rents -- partner-year layered best estimate
     (EITI > BGS > EIA > WB; provenance in `rent_source`)
  9. (extractives-only) Captured government revenue -- partner-year actuals
 10. (extractives-only) HQ shares
 11. (extractives-only) Per-row extraction value and profit correction
 12. (extractives-only) Resource diagnostics / source info / flags
 13. (carveout-only) Carve-out (rate, USD)
 14. (carveout-only) Carve-out alternative-treatment variants

Each list below corresponds to one stage's output. `apply_canonical_order(df, cols)`
puts the listed columns first (in the order given) and appends any extra
columns at the end alphabetically -- so unexpected fields are kept, not lost.
"""

# %%

# Stage 1: cbcr_main.csv / cbcr_main_allsubgroupsonly.csv
# Output of src/1_clean.py
COLUMNS_STAGE_1 = [
    # Identifiers
    "year",
    "iso_parent",
    "parent_jurisdiction",
    "iso_partner",
    "partner_jurisdiction",
    "grouping",
    # Country characteristics (time-invariant)
    "region_tjn",
    "wb_income_group",
    "wb_income_group_3",
    "wb_income_group_official",
    "wb_income_group_id",
    "wb_income_group_id_official",
    "ukt",
    "oecd",
    "oecd_oct",
    "gbr_oct",
    "nld_oct",
    "eu",
    # Country macro (varying)
    "cit",
    "gdp_current_usd",
    "population",
    "wage_monthly",
    "payroll",
    "gvt_health_expenditure",
    "tax_revenue_pct_gdp",
    "tax_revenue_current_usd",
    # CbCR primary (analytics-relevant ones first)
    "profit_loss_before_income_tax_corrected",
    "profit_loss_before_income_tax",
    "adjusted_profit_loss_before_income_tax",
    "income_tax_paid_on_cash_basis",
    "income_tax_accrued_current_year",
    "unrelated_party_revenues",
    "n_employees",
    "tangible_assets_except_cash",
    "total_revenues",
    "related_party_revenues",
    "stated_capital",
    "n_entities",
    "holding_or_managing_ip",
    # CbCR-derived ETRs
    "etr_domestic",
    "etr_domestic_corrected",
    "etr_foreign",
    "etr_foreign_corrected",
    "etr_average",
    "etr_average_corrected",
    "etr_partner_median_corrected",
    "etr_partner_p25_corrected",
    "etr_partner_min_corrected",
    "etr_parent_partner_corrected",
    # Logged variables (analytical helpers)
    "ln_profit_loss_before_income_tax_corrected",
    "ln_unrelated_party_revenues",
    "ln_n_employees",
    "ln_tangible_assets_except_cash",
    "ln_total_revenues",
    "ln_related_party_revenues",
    "ln_stated_capital",
    "ln_holding_or_managing_ip",
    "ln_wage_monthly",
    "ln_gdp_current_usd",
    "ln_population",
    "ln_gvt_health_expenditure",
    # Counts (metadata-ish)
    "n_cbcr",
    "n_cbcr_groups",
]


# Stage 2: cbcr_main_disaggregated.csv
# Output of src/2_disaggregate_aggregated_values.py
COLUMNS_STAGE_2 = [
    # Identifiers
    "year",
    "iso_parent",
    "iso_partner",
    "partner_jurisdiction",
    # Country characteristics (time-invariant)
    "region_tjn",
    "wb_income_group",
    "ukt",
    "oecd",
    "oecd_oct",
    "nld_oct",
    # Country macro
    "cit",
    "wage_monthly",
    "payroll",
    "gvt_health_expenditure",
    "tax_revenue_current_usd",
    # Destination-based sales (market-jurisdiction allocation key; OECD 2020)
    "cfb_sales",
    "cfb_is_imputed",
    "cfb_share",
    "ads_sales",
    "ads_is_imputed",
    "ads_share",
    "digital_imports_usd",
    "cfb_plus_digital_share",
    # CbCR primary
    "profit_loss_before_income_tax_corrected",
    "profit_loss_before_income_tax",
    "income_tax_paid_on_cash_basis",
    "income_tax_accrued_current_year",
    "unrelated_party_revenues",
    "n_employees",
    "tangible_assets_except_cash",
    "total_revenues",
    "related_party_revenues",
    "stated_capital",
    "n_entities",
    "holding_or_managing_ip",
    # CbCR ETRs
    "etr_domestic_corrected",
    "etr_foreign_corrected",
    "etr_average_corrected",
    "etr_partner_median_corrected",
    "etr_partner_p25_corrected",
    "etr_partner_min_corrected",
    "etr_parent_partner_corrected",
    # CbCR group count (pair-year metadata; NaN on distributed rows, like the
    # pair ETR). Denominator for the destination-sales nexus coverage in script 5.
    "n_cbcr",
    # Disaggregation metadata (last in CbCR-only datasets)
    "is_distributed",
    "distribution_source",
    "source_aggregate_code",
    "n_reporters_for_partner_weight",
    "weight_source_for_partner",
]


# Stage 3: cbcr_main_with_extractives.csv
# Output of src/3_resource_contribution.py
COLUMNS_STAGE_3 = COLUMNS_STAGE_2 + [
    # Resource rents — partner-year layered best estimate (EITI > BGS > EIA > WB)
    "rent_total_usd",
    "rent_oil_gas_usd",
    "rent_coal_usd",
    "rent_minerals_usd",
    # Per-category extractive volumes — auditable price/volume/gross_revenue
    # at the partner-year level. Inputs to the variable-royalty carve-out.
    "price_oil_gas",
    "volume_oil_gas",
    "gross_revenue_oil_gas_usd",
    "price_coal",
    "volume_coal",
    "gross_revenue_coal_usd",
    "price_minerals",
    "volume_minerals",
    "gross_revenue_minerals_usd",
    # Captured government revenue — partner-year actual values
    "captured_total_usd",
    "captured_deductible_usd",
    "captured_cit_usd",
    "captured_equity_usd",
    # HQ shares — parent-year-commodity
    "hq_share_oil_gas",
    "hq_share_coal",
    "hq_share_minerals",
    # Per-row extraction value and profit correction
    "state_share",
    "alloc_weight_ioc_usd",
    "alloc_weight_state_self_usd",
    "alloc_weight_usd",
    "captured_deductible_allocated_usd",
    "captured_equity_for_add_back_usd",
    "captured_equity_allocated_usd",
    "profit_extractive_corrected",
    # Resource diagnostics / source info / flags
    "rent_source",
    "rent_carry_forwarded",
    "rent_scaled_to_capture",
    "captured_total_source",
    "captured_deductible_source",
    "captured_cit_source",
    "captured_equity_source",
    "captured_carry_forwarded",
    "equity_add_back_active",
]


# Stage 4: cbcr_main_with_carveout.csv
# Output of src/4_carveout.py (variable royalty — three categories)
# Note: per-category price/volume/gross_revenue are now built in script 3
# and live in STAGE_3 above (auditable carve-out inputs at partner-year level).
COLUMNS_STAGE_4 = COLUMNS_STAGE_3 + [
    # Operating margin (drives Cat 2 and Cat 3 rates)
    "extractive_operating_margin",
    # Per-category rates: cat1 varies by commodity; cat2/cat3 are uniform
    # within a (parent, partner, year) row since they depend on margin.
    "cat1_rate_oil_gas",
    "cat1_rate_coal",
    "cat1_rate_minerals",
    "cat2_rate",
    "cat3_rate",
    # Per-category per-row royalty USD for each variant
    "expected_royalty_cat1_oil_gas_usd",
    "expected_royalty_cat1_coal_usd",
    "expected_royalty_cat1_minerals_usd",
    "expected_royalty_cat2_oil_gas_usd",
    "expected_royalty_cat2_coal_usd",
    "expected_royalty_cat2_minerals_usd",
    "expected_royalty_cat3_oil_gas_usd",
    "expected_royalty_cat3_coal_usd",
    "expected_royalty_cat3_minerals_usd",
    # Variant totals + blended effective rates
    "expected_royalty_cat1_usd",
    "expected_royalty_cat1_rate",
    "expected_royalty_cat2_usd",
    "expected_royalty_cat2_rate",
    "expected_royalty_cat3_usd",
    "expected_royalty_cat3_rate",
    # Primary aliases (set by PRIMARY_CATEGORY in 4_carveout.py)
    "expected_royalty_usd",
    "expected_royalty_rate",
]


def apply_canonical_order(df, canonical):
    """Return df with columns reordered to follow `canonical`. Columns not in
    `canonical` are appended at the end alphabetically -- so any unexpected
    field is preserved rather than silently dropped.
    """
    known = [c for c in canonical if c in df.columns]
    extra = sorted(set(df.columns) - set(known))
    return df[known + extra]
