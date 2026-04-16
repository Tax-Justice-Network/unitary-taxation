#!/usr/bin/env python
"""
Profit Shifting Estimates - Consolidated Script

Unified aggregate distribution approach:
- ALL reporters (good and bad) get their continent aggregates distributed
- _O codes (E_O, A_O, F_O, S_O) are distributed to unreported countries in that continent
- Single-letter codes (E, A, F, S) are also residuals in the OECD data (countries + single-letter = WXD)
- WXD is only used for reporters with no continent breakdown (domestic + WXD only)
- Distribution shares come from good reporters' granular foreign data

Formula: SOTJ (50% employees, 50% payroll), ETR < 15%
"""
import pandas as pd
import numpy as np
from pathlib import Path
from config import *

pd.set_option('display.max_columns', None)
pd.options.display.float_format = '{:,.2f}'.format

# Output directories
output_base = Path(output_tables)
(output_base / 'method_corrected').mkdir(parents=True, exist_ok=True)
(output_base / 'bilateral').mkdir(parents=True, exist_ok=True)

# Variables used in calculations
CBCR_VARS = ['n_employees', 'unrelated_party_revenues', 'tangible_assets_except_cash',
             'payroll', 'stated_capital', 'total_revenues', 'related_party_revenues',
             'holding_or_managing_ip', 'profit_loss_before_income_tax_corrected']

# Metadata columns that need to be filled in for distributed rows
METADATA_COLS = ['partner_jurisdiction', 'etr_average_corrected', 'cit',
                 'tax_revenue_current_usd', 'gvt_health_expenditure', 'region_tjn',
                 'ukt', 'oecd', 'oecd_oct', 'nld_oct']

# Partner info columns for output
partner_info_cols = ['iso_partner'] + METADATA_COLS

# Continent code mapping: OECD code -> continent name
# S (Asia) includes Oceania in OECD CbCR classification (verified: A+E+F+S = WXD)
CONTINENT_CODES = {
    'E_O': 'Europe', 'E': 'Europe',
    'A_O': 'Americas', 'A': 'Americas',
    'F_O': 'Africa', 'F': 'Africa',
    'S_O': 'Asia_Oceania', 'S': 'Asia_Oceania',
}


# ---------------------------------------------------------------------------
# Continent mapping
# ---------------------------------------------------------------------------

def build_continent_mapping():
    """
    Build mapping from continent names to sets of country ISO3 codes.
    Uses region_tjn from the unilateral cross data.
    """
    cross = pd.read_csv(unilateral_cross_data)
    mapping = {
        'Europe': set(cross.loc[cross['region_tjn'] == 'Europe', 'iso3']),
        'Americas': set(cross.loc[cross['region_tjn'].isin(
            ['Latin America', 'Northern America', 'Caribbean/American isl.']), 'iso3']),
        'Africa': set(cross.loc[cross['region_tjn'] == 'Africa', 'iso3']),
        'Asia_Oceania': set(cross.loc[cross['region_tjn'].isin(
            ['Asia', 'Oceania']), 'iso3']),
    }
    return mapping


# ---------------------------------------------------------------------------
# Distribution shares
# ---------------------------------------------------------------------------

def compute_distribution_shares(cbcr_year, excluded_parents, continent_mapping):
    """
    Compute per-variable distribution shares from good reporters' foreign data.

    Returns:
        continent_shares: dict of continent_name -> DataFrame (iso_partner x CBCR_VARS)
        global_shares: DataFrame (iso_partner x CBCR_VARS)
    """
    # Good reporters' foreign country-level data
    good_foreign = cbcr_year[
        (~cbcr_year['iso_parent'].isin(excluded_parents)) &
        (~cbcr_year['iso_partner'].isin(non_countries)) &
        (cbcr_year['iso_partner'] != cbcr_year['iso_parent'])
    ]

    # Global shares (for WXD distribution)
    partner_totals = good_foreign.groupby('iso_partner')[CBCR_VARS].sum()
    global_shares = partner_totals  # raw totals; we renormalize when distributing

    # Per-continent shares
    all_continent_countries = set()
    for countries in continent_mapping.values():
        all_continent_countries |= countries

    continent_shares = {}
    for continent_name, countries in continent_mapping.items():
        cont_data = good_foreign[good_foreign['iso_partner'].isin(countries)]
        if cont_data.empty:
            continent_shares[continent_name] = pd.DataFrame(columns=CBCR_VARS)
        else:
            continent_shares[continent_name] = cont_data.groupby('iso_partner')[CBCR_VARS].sum()

    return continent_shares, global_shares


# ---------------------------------------------------------------------------
# Aggregate distribution for a single reporter
# ---------------------------------------------------------------------------

def distribute_aggregates_for_reporter(parent_data, iso_parent, continent_mapping,
                                       continent_shares, global_shares):
    """
    For a single reporter, keep country-level rows and distribute continent aggregates.

    Logic:
    1. Keep all individually reported country rows as-is
    2. For each continent:
       - If _O code exists: distribute to unreported countries in that continent
       - Elif single-letter code exists: compute residual (total - reported), distribute
    3. If ONLY WXD exists (no continent codes at all): distribute to all unreported countries
    """
    # Separate country rows from aggregate rows
    country_rows = parent_data[~parent_data['iso_partner'].isin(non_countries)].copy()
    reported_partners = set(country_rows['iso_partner'].unique())

    distributed_rows = []
    continents_processed = set()

    # --- Pass 1: _O codes (proper residuals) ---
    for code in ['E_O', 'A_O', 'F_O', 'S_O']:
        agg_row = parent_data[parent_data['iso_partner'] == code]
        if agg_row.empty:
            continue

        continent_name = CONTINENT_CODES[code]
        continents_processed.add(continent_name)

        # Unreported countries in this continent
        unreported = continent_mapping[continent_name] - reported_partners - {iso_parent}
        if not unreported:
            continue

        # Get shares for unreported countries from good reporters
        shares = continent_shares.get(continent_name, pd.DataFrame(columns=CBCR_VARS))
        relevant = shares[shares.index.isin(unreported)]
        if relevant.empty:
            continue

        totals = relevant.sum()
        for iso_partner in relevant.index:
            new_row = {'iso_parent': iso_parent, 'iso_partner': iso_partner}
            for var in CBCR_VARS:
                agg_val = agg_row[var].values[0]
                if pd.notna(agg_val) and totals[var] > 0:
                    new_row[var] = agg_val * relevant.loc[iso_partner, var] / totals[var]
                else:
                    new_row[var] = 0
            distributed_rows.append(new_row)

    # --- Pass 2: single-letter codes for unhandled continents ---
    # Single-letter codes (E, A, F, S) are RESIDUALS in the data (like _O),
    # NOT continent totals. Verified: countries + single-letter codes = WXD.
    for code in ['E', 'A', 'F', 'S']:
        continent_name = CONTINENT_CODES[code]
        if continent_name in continents_processed:
            continue

        agg_row = parent_data[parent_data['iso_partner'] == code]
        if agg_row.empty:
            continue

        continents_processed.add(continent_name)

        # Unreported countries in this continent
        unreported = continent_mapping[continent_name] - reported_partners - {iso_parent}
        if not unreported:
            continue

        # Distribute directly (value is already a residual, not a total)
        shares = continent_shares.get(continent_name, pd.DataFrame(columns=CBCR_VARS))
        relevant = shares[shares.index.isin(unreported)]
        if relevant.empty:
            continue

        totals = relevant.sum()
        for iso_partner in relevant.index:
            new_row = {'iso_parent': iso_parent, 'iso_partner': iso_partner}
            for var in CBCR_VARS:
                agg_val = agg_row[var].values[0]
                if pd.notna(agg_val) and totals[var] > 0:
                    new_row[var] = agg_val * relevant.loc[iso_partner, var] / totals[var]
                else:
                    new_row[var] = 0
            distributed_rows.append(new_row)

    # --- Pass 3: WXD only if NO continent aggregates were processed ---
    if not continents_processed:
        wxd_row = parent_data[parent_data['iso_partner'] == 'WXD']
        if not wxd_row.empty:
            all_foreign = set(global_shares.index) - {iso_parent} - reported_partners
            relevant = global_shares[global_shares.index.isin(all_foreign)]
            if not relevant.empty:
                totals = relevant.sum()
                for iso_partner in relevant.index:
                    new_row = {'iso_parent': iso_parent, 'iso_partner': iso_partner}
                    for var in CBCR_VARS:
                        wxd_val = wxd_row[var].values[0]
                        if pd.notna(wxd_val) and totals[var] > 0:
                            new_row[var] = wxd_val * relevant.loc[iso_partner, var] / totals[var]
                        else:
                            new_row[var] = 0
                    distributed_rows.append(new_row)

    # Combine original country rows + distributed rows
    if distributed_rows:
        dist_df = pd.DataFrame(distributed_rows)
        result = pd.concat([country_rows, dist_df], ignore_index=True)
    else:
        result = country_rows

    return result, len(distributed_rows), len(continents_processed)


# ---------------------------------------------------------------------------
# Misalignment calculation
# ---------------------------------------------------------------------------

def calculate_misalignment(cbcr_data,
                           formula_vars=['n_employees', 'unrelated_party_revenues',
                                         'tangible_assets_except_cash', 'payroll',
                                         'stated_capital', 'total_revenues',
                                         'related_party_revenues', 'holding_or_managing_ip'],
                           weights=[0.5, 0, 0, 0.5, 0, 0, 0, 0],
                           profit_var='profit_loss_before_income_tax_corrected',
                           etr_max=0.15):
    """
    Calculate profit misalignment using the specified formula weights.
    Default SOTJ formula: 50% employees, 50% payroll, ETR < 15%
    """
    df = cbcr_data.copy()

    # Positive profits only for share calculation
    df['profit_var_pos'] = df[profit_var].clip(lower=0)
    df['share_profit'] = df['profit_var_pos'] / df.groupby('iso_parent')['profit_var_pos'].transform('sum')

    # Calculate weighted shares of economic activity
    actual_weights = []
    actual_variables = []
    for i, var in enumerate(formula_vars):
        if var is not None and weights[i] > 0:
            actual_variables.append(f'share_{var}')
            actual_weights.append(weights[i])
            df.loc[df[var] < 0, var] = 0
            df[f'share_{var}'] = df[var] / df.groupby('iso_parent')[var].transform('sum')

    # Share of economic activity
    df['share_economy_partner_of_parent'] = (df.loc[:, actual_variables] * actual_weights).sum(axis=1, min_count=len(actual_weights))

    # Min 1% for jurisdictions with profits but no economic activity
    df.loc[(df['share_economy_partner_of_parent'] == 0) & (df[profit_var] > 0), 'share_economy_partner_of_parent'] = 0.01

    # Normalize to sum to 1
    df['share_economy_partner_of_parent'] = df['share_economy_partner_of_parent'] / df.groupby('iso_parent')['share_economy_partner_of_parent'].transform('sum')

    # Theoretical vs actual profit
    df['theoretical_profit'] = df['share_economy_partner_of_parent'] * df.groupby('iso_parent')[profit_var].transform('sum')
    df['misaligned_profit'] = df[profit_var] - df['theoretical_profit']

    # Zero out positive misalignment if ETR > threshold
    df.loc[(df['misaligned_profit'] > 0) & (df['etr_average_corrected'] > etr_max), 'misaligned_profit'] = 0

    # Adjust negative misalignments to balance positives within each parent
    def adjust_misalignment(group):
        total_neg = group.loc[group['misaligned_profit'] < 0, 'misaligned_profit'].sum()
        total_pos = group.loc[group['misaligned_profit'] > 0, 'misaligned_profit'].sum()
        if total_neg != 0:
            factor = -total_pos / total_neg
            group.loc[group['misaligned_profit'] < 0, 'misaligned_profit'] *= factor
        return group

    adjusted_parts = []
    for iso_parent, group in df.groupby('iso_parent'):
        adjusted_group = adjust_misalignment(group.copy())
        adjusted_parts.append(adjusted_group)
    df = pd.concat(adjusted_parts, ignore_index=True)

    return df


# ---------------------------------------------------------------------------
# Bilateral estimation
# ---------------------------------------------------------------------------

def calculate_bilateral_by_parent(misalignment_df, year):
    """
    Calculate bilateral profit shifting estimates.
    For each iso_parent, distributes harm from tax havens to sufferers proportionally.
    """
    df = misalignment_df.copy()
    bilateral_rows = []

    for iso_parent in df['iso_parent'].unique():
        parent_data = df[df['iso_parent'] == iso_parent].copy()

        havens = parent_data[parent_data['misaligned_profit'] > 0][['iso_partner', 'misaligned_profit', 'etr_average_corrected']].copy()
        total_shifted = havens['misaligned_profit'].sum()
        if total_shifted <= 0:
            continue
        havens['share_of_shifted'] = havens['misaligned_profit'] / total_shifted
        havens = havens.rename(columns={'iso_partner': 'iso_responsible'})

        sufferers = parent_data[parent_data['misaligned_profit'] < 0][['iso_partner', 'misaligned_profit', 'cit']].copy()
        total_lost = abs(sufferers['misaligned_profit'].sum())
        if total_lost <= 0:
            continue
        sufferers['share_of_loss'] = abs(sufferers['misaligned_profit']) / total_lost
        sufferers = sufferers.rename(columns={'iso_partner': 'iso_affected'})

        parent_tax_loss = (abs(sufferers['misaligned_profit']) * sufferers['cit']).sum()

        for _, haven in havens.iterrows():
            for _, sufferer in sufferers.iterrows():
                bilateral_shifted = haven['share_of_shifted'] * sufferer['share_of_loss'] * total_shifted
                bilateral_tax_loss = haven['share_of_shifted'] * sufferer['share_of_loss'] * parent_tax_loss
                bilateral_rows.append({
                    'year': year,
                    'iso_parent': iso_parent,
                    'iso_responsible': haven['iso_responsible'],
                    'iso_affected': sufferer['iso_affected'],
                    'shifted_profit_musd': bilateral_shifted / 1e6,
                    'tax_loss_musd': bilateral_tax_loss / 1e6,
                })

    return pd.DataFrame(bilateral_rows)


def aggregate_country_results(misalignment_df, unique_partners, year):
    """Aggregate misalignment results by iso_partner."""
    country_results = misalignment_df.groupby('iso_partner').agg(
        negative_misalignment=('misaligned_profit', lambda x: x[x < 0].sum()),
        positive_misalignment=('misaligned_profit', lambda x: x[x > 0].sum()),
        theoretical_profit=('theoretical_profit', 'sum'),
        reported_profit=('profit_loss_before_income_tax_corrected', 'sum')
    ).reset_index()

    country_results['negative_misalignment'] = -country_results['negative_misalignment'] / 1e6
    country_results['positive_misalignment'] = country_results['positive_misalignment'] / 1e6
    country_results['theoretical_profit'] = country_results['theoretical_profit'] / 1e6
    country_results['reported_profit'] = country_results['reported_profit'] / 1e6

    country_results = country_results.merge(unique_partners, on='iso_partner', how='left')

    country_results['tax_revenue_loss'] = country_results['negative_misalignment'] * country_results['cit']
    country_results['tax_revenue_gain'] = country_results['positive_misalignment'] * country_results['etr_average_corrected']

    total_pos = country_results['positive_misalignment'].sum()
    total_loss = country_results['tax_revenue_loss'].sum()

    country_results['tax_revenue_loss_caused_pct_of_total'] = country_results['positive_misalignment'] / total_pos if total_pos > 0 else 0
    country_results['tax_revenue_loss_caused_usd'] = country_results['tax_revenue_loss_caused_pct_of_total'] * total_loss
    country_results['tax_revenue_loss_suffered_pct_of_total'] = country_results['tax_revenue_loss'] / total_loss if total_loss > 0 else 0

    country_results['year'] = year
    return country_results


# ---------------------------------------------------------------------------
# Exclusion list (for share computation only - these reporters lack granular data)
# ---------------------------------------------------------------------------

# 2022 bad reporters from data/raw/CbcR_reporters_over_time.xlsx (sheet "2022"):
#   Only domestic plus continents: AUT, BHR, FIN, GBR, IRL, KOR, MUS, SWE
#   Only domestic vs rest-of-the-world: CZE, HUN, MAR, NZL, UKR
#   Partial reporters (heavily aggregated): CAN*, COL**, NLD*
EXCLUSION_CONDITIONS = [
    ('AUT', 2016, 2022),  # Austria: only continents
    ('BHR', 2022, 2022),  # Bahrain: continents only (new in 2022)
    ('CAN', 2022, 2022),  # Canada: few granular partners, heavily aggregated
    ('COL', 2022, 2022),  # Colombia: too few granular partners
    ('CZE', 2019, 2022),  # Czechia: only domestic vs ROW
    ('FIN', 2016, 2022),  # Finland: only continents
    ('GRC', 2017, 2019),  # Greece
    ('GBR', 2017, 2022),  # UK: only continents
    ('HUN', 2018, 2022),  # Hungary: only domestic vs ROW
    ('IMN', 2017, 2020),  # Isle of Man
    ('IRL', 2016, 2022),  # Ireland: only continents
    ('KOR', 2016, 2022),  # Korea: only continents
    ('MAC', 2019, 2021),  # Macau (improved in 2022)
    ('MAR', 2021, 2022),  # Morocco: only domestic vs ROW
    ('MUS', 2019, 2022),  # Mauritius: continents only
    ('NLD', 2016, 2017),  # Netherlands (2016-2017 only)
    ('NLD', 2022, 2022),  # Netherlands: few granular partners in 2022
    ('NOR', 2016, 2017),  # Norway
    ('NZL', 2018, 2022),  # New Zealand: only domestic vs ROW
    ('POL', 2019, 2021),  # Poland (improved in 2022)
    ('SWE', 2016, 2022),  # Sweden: only continents
    ('UKR', 2022, 2022),  # Ukraine: only WXD (new in 2022)
]

def get_excluded_parents_for_year(year):
    return {iso for iso, start, end in EXCLUSION_CONDITIONS if start <= year <= end}


# ---------------------------------------------------------------------------
# Main estimation
# ---------------------------------------------------------------------------

def run_estimation(cbcr_full, year, continent_mapping):
    """
    Run profit shifting estimation for a given year.
    Distributes continent aggregates for ALL reporters, then runs misalignment.
    """
    print(f"\n{'='*60}\nYear {year}\n{'='*60}")

    cbcr_year = cbcr_full[cbcr_full['year'] == year].copy()
    excluded_parents = get_excluded_parents_for_year(year)

    # Step 1: Compute distribution shares from good reporters
    continent_shares, global_shares = compute_distribution_shares(
        cbcr_year, excluded_parents, continent_mapping
    )

    n_good = cbcr_year[~cbcr_year['iso_parent'].isin(excluded_parents)]['iso_parent'].nunique()
    n_bad = cbcr_year[cbcr_year['iso_parent'].isin(excluded_parents)]['iso_parent'].nunique()
    print(f"  Reporters: {n_good} good + {n_bad} excluded from share computation")

    # Step 2: Build partner metadata lookup (for filling in distributed rows)
    partner_lookup = (
        cbcr_year[~cbcr_year['iso_partner'].isin(non_countries)]
        .drop_duplicates(subset=['iso_partner'])
        .set_index('iso_partner')[METADATA_COLS]
    )

    # Step 3: Process ALL reporters - distribute continent aggregates
    all_processed = []
    total_distributed = 0
    reporters_with_distribution = 0

    for iso_parent in cbcr_year['iso_parent'].unique():
        parent_data = cbcr_year[cbcr_year['iso_parent'] == iso_parent]
        processed, n_dist, n_cont = distribute_aggregates_for_reporter(
            parent_data, iso_parent, continent_mapping,
            continent_shares, global_shares
        )
        all_processed.append(processed)
        total_distributed += n_dist
        if n_dist > 0:
            reporters_with_distribution += 1

    print(f"  Distributed {total_distributed} rows across {reporters_with_distribution} reporters")

    # Step 4: Combine all processed data
    combined = pd.concat(all_processed, ignore_index=True)

    # Fill in missing metadata for distributed rows
    for col in METADATA_COLS:
        if col in combined.columns:
            mask = combined[col].isna()
            if mask.any():
                combined.loc[mask, col] = combined.loc[mask, 'iso_partner'].map(
                    partner_lookup[col]
                )
        else:
            combined[col] = combined['iso_partner'].map(partner_lookup[col])

    # Step 5: Run misalignment (SOTJ: 50% employees, 50% payroll, ETR < 15%)
    final_misalignment = calculate_misalignment(combined)
    final_misalignment['year'] = year

    # Get unique partner info
    available_cols = [c for c in partner_info_cols if c in final_misalignment.columns]
    unique_partners = final_misalignment.drop_duplicates(subset=['iso_partner'])[available_cols]

    # Aggregate results
    country_results = aggregate_country_results(final_misalignment, unique_partners, year)

    # Calculate bilateral
    bilateral = calculate_bilateral_by_parent(final_misalignment, year)

    # Print summary
    total_pos = country_results['positive_misalignment'].sum()
    total_loss = country_results['tax_revenue_loss'].sum()
    print(f"  Shifted: {total_pos:,.0f}M USD, Tax Loss: {total_loss:,.0f}M USD")

    return final_misalignment, country_results, bilateral


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print("Loading data...")
    cbcr_full = pd.read_csv(f'{data_final}/cbcr_main_no_imputation_allsubgroupsonly.csv')
    print(f"Loaded {len(cbcr_full)} rows")
    print(f"Years: {sorted(cbcr_full['year'].unique())}")

    print("\nBuilding continent mapping from unilateral cross data...")
    continent_mapping = build_continent_mapping()
    for name, countries in continent_mapping.items():
        print(f"  {name}: {len(countries)} countries")

    print("\nExcluded from share computation per year:")
    for year in range(first_year, first_year + n_years):
        excluded = get_excluded_parents_for_year(year)
        print(f"  {year}: {len(excluded)} countries - {sorted(excluded)}")

    # Store results
    results = {'country': [], 'bilateral': [], 'aggregate': []}

    for year in range(first_year, first_year + n_years):
        mis, country, bilateral = run_estimation(cbcr_full, year, continent_mapping)
        if country is not None:
            results['country'].append(country)
            results['bilateral'].append(bilateral)
            total_pos = country['positive_misalignment'].sum()
            total_loss = country['tax_revenue_loss'].sum()
            results['aggregate'].append({
                'year': year,
                'total_shifted_musd': total_pos,
                'total_tax_loss_musd': total_loss
            })
            country.to_csv(output_base / 'method_corrected' / f'country_results_{year}.csv', index=False)
            bilateral.to_csv(output_base / 'method_corrected' / f'bilateral_{year}.csv', index=False)

    # Combine all years
    if results['country']:
        pd.concat(results['country']).to_csv(output_base / 'method_corrected' / 'country_results_all_years.csv', index=False)
        pd.concat(results['bilateral']).to_csv(output_base / 'method_corrected' / 'bilateral_all_years.csv', index=False)

    # Show aggregate summary
    agg = pd.DataFrame(results['aggregate'])
    print("\nAggregate Results (in million USD):")
    print(agg.to_string(index=False))

    # Aggregate bilateral across all reporters
    if results['bilateral']:
        bilateral_all = pd.concat(results['bilateral'])

        bilateral_agg = bilateral_all.groupby(['year', 'iso_responsible', 'iso_affected']).agg(
            shifted_profit_musd=('shifted_profit_musd', 'sum'),
            tax_loss_musd=('tax_loss_musd', 'sum'),
            n_reporters=('iso_parent', 'nunique')
        ).reset_index()

        bilateral_agg.to_csv(output_base / 'bilateral' / 'bilateral_aggregated_corrected.csv', index=False)

        # Also save to TJN shared folder for IFF portal
        tjn_bilateral_path = Path(tjn_shared_bilateral)
        if tjn_bilateral_path.exists():
            bilateral_agg.to_csv(tjn_bilateral_path / 'corporate_taxabuse_iffportal.csv', index=False)
            print(f"Saved: {tjn_bilateral_path / 'corporate_taxabuse_iffportal.csv'}")

        # Top pairs for latest year
        latest_year = bilateral_agg['year'].max()
        latest = bilateral_agg[bilateral_agg['year'] == latest_year]
        print(f"\nTop 15 bilateral pairs by tax loss ({latest_year}):")
        print(latest.nlargest(15, 'tax_loss_musd')[['iso_responsible', 'iso_affected', 'tax_loss_musd']].to_string(index=False))

        # Summary by tax haven (responsible)
        by_responsible = bilateral_agg.groupby(['year', 'iso_responsible']).agg(
            tax_loss_caused_musd=('tax_loss_musd', 'sum'),
            n_affected=('iso_affected', 'nunique')
        ).reset_index().sort_values(['year', 'tax_loss_caused_musd'], ascending=[True, False])

        by_responsible.to_csv(output_base / 'bilateral' / 'summary_by_responsible_corrected.csv', index=False)

        print(f"\nTop 15 tax havens by harm caused ({latest_year}):")
        print(by_responsible[by_responsible['year'] == latest_year].head(15).to_string(index=False))

        # Summary by affected country
        by_affected = bilateral_agg.groupby(['year', 'iso_affected']).agg(
            tax_loss_suffered_musd=('tax_loss_musd', 'sum'),
            n_responsible=('iso_responsible', 'nunique')
        ).reset_index().sort_values(['year', 'tax_loss_suffered_musd'], ascending=[True, False])

        by_affected.to_csv(output_base / 'bilateral' / 'summary_by_affected_corrected.csv', index=False)

        print(f"\nTop 15 countries by harm suffered ({latest_year}):")
        print(by_affected[by_affected['year'] == latest_year].head(15).to_string(index=False))

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print("\nFormula: SOTJ (50% employees, 50% payroll)")
    print("ETR threshold: 15%")
    print("Method: Unified aggregate distribution (all reporters)")
    print("  - _O codes distributed to unreported countries per continent")
    print("  - Single-letter continent codes: also residuals, distributed directly")
    print("  - WXD distributed globally (only for reporters with no continent breakdown)")
    print(f"\nFiles saved:")
    print(f"  - Country results: {output_base / 'method_corrected'}")
    print(f"  - Bilateral results: {output_base / 'bilateral'}")
