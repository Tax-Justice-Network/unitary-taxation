"""Country-level resource info sheets.

For every jurisdiction that receives a resource correction, write a human-readable
`.txt` dossier — a country reference (for when people ask about a specific country)
and a QA audit of the correction in one. Each sheet carries:

  - CORRECTION SOURCE(S)            : cascade tier(s) (eiti / manual / grd / rent_proxy) + years
  - RESOURCES & RENT-CAPTURE REGIME : relevant commodities; statutory CIT baseline; effective
                                      resource rate r; how rent is captured (royalties = pre-profit,
                                      resource income tax / CIT = post-profit, state/NOC dividends =
                                      equity) with the split fractions and domestic_share; regime notes
  - RATES                           : c, r, per-commodity profit-tax rates
  - SOURCES                         : per-commodity rate source notes, combined-rate source, the
                                      manual revenue source note, + provenance doc pointers
  - REPORTED & CORRECTION BY YEAR   : profit / tax / observed ETR vs stripped vs residual, per year
  - DOMESTIC vs FOREIGN (pooled)    : foreign non-resource ETR after correction
  - FLAGS                           : plausibility flags (negative residual, over-strip, etc.)

Inputs : data/final/cbcr_main_excl_resource.csv          (the resource-corrected dataset, from script 4)
         data/raw/resources/resource_profit_tax_rate.csv
         data/final/effective_resource_cit_rates.csv
         data/raw/resources/manual_resource_revenue.csv
         data/intermediate/extractive/resource_payments_by_hq_source_yearly.csv
Output : data/raw/country_resource_info/<ISO3>.txt  + _SUMMARY.csv / _SUMMARY.txt

Re-run after script 4 to refresh. Read-only on all inputs.
"""
import os
import re
import sys

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

# config.py / extractive scripts put this dir on sys.path; _paths is the shared module.
from _paths import RAW, EXT_INT, FINAL  # noqa: E402

OUT = RAW / "country_resource_info"
B = 1e9
DOCS = RAW.parent.parent / "docs" / "extractive"   # provenance docs the sheets cite
_URL_RE = re.compile(r"https?://[^\s)\]`|]+")


def _collect_links(iso, data_md, overview_md, extra_texts):
    """Pull every reference URL relevant to this country out of the two provenance
    docs (manual_resource_data_sources.md table rows + manual_resource_sources_overview.md
    country sections) and the CSV source notes already shown, so each sheet stands alone."""
    urls = []
    for line in data_md.splitlines():
        if re.search(rf"\b{re.escape(iso)}\b", line):
            urls += _URL_RE.findall(line)
    for sec in ("\n" + overview_md).split("\n## "):
        head = sec.splitlines()[0] if sec.strip() else ""
        if f"({iso})" in head:
            urls += _URL_RE.findall(sec)
    for t in extra_texts:
        if isinstance(t, str):
            urls += _URL_RE.findall(t)
    out = []
    for u in urls:
        u = u.rstrip(".,);`")
        if u and u not in out:
            out.append(u)
    return out

PROF = "profit_loss_before_income_tax_corrected"
TAX = "income_tax_paid_on_cash_basis"

# How each cascade tier captures rent (for the regime description per country).
# Mirrors 1_8_resource_payments_by_hq_source.py DEFAULT_SPLIT / DEFAULT_DOMESTIC.
DEFAULT_SPLIT = {"oil_gas": (0.45, 0.30, 0.25), "coal": (0.55, 0.40, 0.05), "minerals": (0.50, 0.40, 0.10)}
DEFAULT_DOMESTIC = {"oil_gas": 0.55, "coal": 0.40, "minerals": 0.40}
RENT_CAPTURE_RATE = 0.35
# Plain-language name and full explanation of each data tier that can supply a
# country's resource estimate (the cascade in 1_8_resource_payments_by_hq_source.py).
SOURCE_NAME = {
    "eiti_bilateral": "the country's own EITI report",
    "manual_distributed": "hand-curated government figures",
    "grd_distributed": "the UNU-WIDER Government Revenue Dataset (GRD)",
    "rent_proxy": "a modelled rent proxy",
}
SOURCE_FULL = {
    "eiti_bilateral":
        "These are payments that extractive companies reported making to the government in the "
        "country's Extractive Industries Transparency Initiative (EITI) report, matched to each "
        "company's headquarters country. The EITI report is treated as a complete record of the "
        "country's extractive activity, so any company-pair not listed in it is taken to be zero.",
    "manual_distributed":
        "These are government resource-revenue figures hand-collected for this project (from national "
        "budgets, company reports and IMF documents) and then split into the payment types below.",
    "grd_distributed":
        "This is the country's total resource revenue from the UNU-WIDER Government Revenue Dataset, a "
        "single country-level figure with no company detail. It is spread across the headquarters "
        "countries of the companies operating there using Orbis ownership data.",
    "rent_proxy":
        f"There is no reported extractive-payment data for this country, so its resource figures are "
        f"modelled: World Bank natural-resource rents (the value of what is extracted minus the cost of "
        f"extracting it) multiplied by an assumed government-capture share of {RENT_CAPTURE_RATE:.0%}, "
        f"then split into payment types using default fractions. This is the lowest-confidence source.",
}
COMM_LABEL = {"oil_gas": "oil & gas", "coal": "coal", "minerals": "minerals (metals/other)"}


def etr(P, T):
    return T / P if P > 0 else np.nan


def main():
    os.makedirs(OUT, exist_ok=True)
    for fn in os.listdir(OUT):                       # clear stale sheets
        if fn.endswith(".txt"):
            os.remove(os.path.join(OUT, fn))

    rt = pd.read_csv(RAW / "resources" / "resource_profit_tax_rate.csv", comment="#")
    ecr = pd.read_csv(FINAL / "effective_resource_cit_rates.csv", comment="#").dropna(subset=["iso3"])
    ecr = ecr[ecr.iso3.str.len() == 3].set_index("iso3")
    mrr = pd.read_csv(RAW / "resources" / "manual_resource_revenue.csv", comment="#")
    pan = pd.read_csv(EXT_INT / "resource_payments_by_hq_source_yearly.csv")
    # Control table — used to mirror script 4's correction-method gating (the ETR-gap
    # fires for included, NON-EITI countries that carry a curated resource rate).
    _par = pd.read_csv(RAW / "resources" / "resource_country_parameters.csv")
    eiti_flag = {r.iso3: str(r.eiti).strip().lower() in ("true", "yes", "1")
                 for r in _par.itertuples()}
    curated_present = {r.iso3 for r in _par.itertuples()
                      if str(getattr(r, "resource_rate", "")).strip() not in ("", "nan")}
    # Provenance docs whose links we inline into each sheet so it stands alone.
    def _read_doc(fn):
        p = DOCS / fn
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            return ""
    data_md = _read_doc("manual_resource_data_sources.md")
    overview_md = _read_doc("manual_resource_sources_overview.md")

    df = pd.read_csv(FINAL / "cbcr_main_excl_resource.csv")
    for c in [PROF, TAX, "cit", "resource_profit_base_usd", "resource_tax_deduction_usd"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["_corr"] = (df["resource_profit_base_usd"].fillna(0).abs()
                   + df["resource_tax_deduction_usd"].fillna(0).abs())
    corr_iso = sorted(df[df["_corr"] > 0]["iso_partner"].dropna().unique())

    src_methods = pan.groupby("source_iso3")["data_source"].agg(lambda s: dict(s.value_counts()))
    src_years = pan.groupby("source_iso3")["year"].agg(lambda s: sorted(set(int(y) for y in s)))
    src_commodities = pan.groupby("source_iso3")["commodity"].agg(lambda s: sorted(set(s)))

    summary = []
    for iso in corr_iso:
        g = df[df.iso_partner == iso].copy()
        f = g[g.iso_parent != iso]
        d = g[g.iso_parent == iso]
        fP = f[PROF].clip(lower=0).sum(); fT = f[TAX].sum()
        dP = d[PROF].clip(lower=0).sum(); dT = d[TAX].sum()
        c = g["cit"].dropna().mean()
        rrows = rt[rt.source_iso3 == iso]
        r_og = rrows[rrows.commodity == "oil_gas"]["effective_resource_profit_tax_rate"]
        r_og = float(r_og.iloc[0]) if len(r_og) else np.nan
        comb = ecr["combined_effective_rate"].get(iso, np.nan)
        head = ecr["headline_cit_rate"].get(iso, np.nan)
        methods = src_methods.get(iso, {})
        method_str = ", ".join(f"{k}({v})" for k, v in methods.items()) if isinstance(methods, dict) else str(methods)
        is_rentproxy = "rent_proxy" in (methods if isinstance(methods, dict) else {})

        yr_rows = []
        flags = set()
        prev_strip = None
        for y, gy in g.groupby("year"):
            P = gy[PROF].clip(lower=0).sum(); T = gy[TAX].sum()
            rp = gy["resource_profit_base_usd"].sum(); rt_ = gy["resource_tax_deduction_usd"].sum()
            res_prof_left = P - rp; res_tax_left = T - rt_
            e_obs = etr(P, T); e_left = etr(res_prof_left, res_tax_left) if res_prof_left > 0 else np.nan
            yr_rows.append((int(y), P / B, T / B, e_obs, rp / B, rt_ / B,
                            res_prof_left / B, res_tax_left / B, e_left))
            if res_tax_left < -0.05 * B:
                flags.add("Over-strip: in at least one year the correction removed more resource tax "
                          "than this country actually reported, leaving a negative non-resource tax.")
            if T > 0 and rt_ > T * 1.02:
                flags.add("Over-strip: in at least one year the resource tax removed is larger than the "
                          "total tax this country reported that year.")
            if prev_strip is not None and prev_strip > 0.5 * B and rt_ > 0 and (rt_ / prev_strip > 5 or prev_strip / max(rt_, 1) > 5):
                flags.add("Discontinuity: the amount of resource tax removed changes more than five-fold "
                          "between two consecutive years, which can indicate a break in the underlying data.")
            prev_strip = rt_

        f_rt = f["resource_tax_deduction_usd"].sum()
        f_rp = f["resource_profit_base_usd"].sum()
        e_for_left = etr(fP - f_rp, fT - f_rt)   # on the excl_resource pair
        # Flag a genuine under-strip: residual non-resource ETR sits meaningfully
        # ABOVE the statutory CIT (resource tax not fully removed). A residual at
        # or below statutory is expected — high-CIT economies should keep ~their
        # statutory rate — and is NOT flagged.
        if (pd.notna(e_for_left) and pd.notna(c) and e_for_left > c + 0.10
                and e_for_left > 0.15 and (fT - f_rt) > 0.5 * B):
            flags.add(f"Possible under-strip: after the correction the non-resource effective tax rate "
                      f"({e_for_left:.2f}) is still well above this country's statutory corporate tax rate "
                      f"({c:.2f}), so some resource tax may not have been removed.")
        if pd.notna(r_og) and pd.notna(c) and r_og <= c:
            flags.add("The resource tax rate is not higher than the ordinary corporate tax rate, so the "
                      "ETR-gap method cannot identify any resource tax to remove for this country.")
        if pd.isna(r_og) and not is_rentproxy:
            flags.add("No oil & gas resource tax rate is recorded for this country, so the correction uses "
                      "a fallback rate (see the resource profit-tax rate line above).")
        if pd.notna(comb) and pd.notna(r_og) and abs(comb - r_og) > 0.1:
            flags.add(f"The two resource-rate sources disagree for this country: the per-commodity rate is "
                      f"{r_og}, but the combined effective rate is {comb}.")
        if is_rentproxy:
            flags.add("Part of this country's resource estimate comes from the modelled rent proxy "
                      "(World Bank resource rents times an assumed government-capture share), which is the "
                      "lowest-confidence source.")

        mrows = mrr[mrr.source_iso3 == iso]
        commodities = sorted(set(rrows.commodity.unique())
                             | set(mrows.commodity.unique())
                             | set(src_commodities.get(iso, [])))
        dom_method = max(methods, key=methods.get) if isinstance(methods, dict) and methods else None
        dom_comm = commodities[0] if commodities else "oil_gas"
        # Capture split: show the ACTUAL realized composition from the payment
        # panel (EITI / GRD / manual / rent_proxy streams) so EITI countries
        # display their reported royalty / CIT / dividend mix, not a default.
        psrc = pan[pan.source_iso3 == iso]
        ppe = psrc[["pre_profit_payments_usd", "post_profit_payments_usd", "equity_income_usd"]].sum()
        ppe_tot = ppe.sum()
        if ppe_tot > 0:
            frac_pre = round(ppe.iloc[0] / ppe_tot, 3)
            frac_post = round(ppe.iloc[1] / ppe_tot, 3)
            frac_eq = round(ppe.iloc[2] / ppe_tot, 3)
            dom = psrc.loc[psrc.hq_iso3 == iso,
                           ["pre_profit_payments_usd", "post_profit_payments_usd",
                            "equity_income_usd"]].sum().sum()
            dshare = round(dom / ppe_tot, 3)
            frac_src = f"actual realized split from {dom_method or 'panel'} payment streams"
        elif len(mrows):
            mr = mrows.iloc[0]
            frac_pre, frac_post, frac_eq, dshare = (mr.frac_pre_profit, mr.frac_post_profit,
                                                    mr.frac_equity, mr.domestic_share)
            frac_src = "manual table"
        else:
            frac_pre, frac_post, frac_eq = DEFAULT_SPLIT.get(dom_comm, (0.45, 0.30, 0.25))
            dshare = DEFAULT_DOMESTIC.get(dom_comm, 0.5)
            frac_src = f"default split for {dom_comm}"

        # Resource rate actually used by the correction (mirrors script 4's
        # fallback chain): combined effective rate -> max per-commodity rate -> 0.30.
        name = ecr["country_name"].get(iso, "") if "country_name" in ecr.columns else ""
        regime = ecr["regime_type"].get(iso, "-")
        surtax = ecr["resource_surtax_rate"].get(iso, np.nan)
        rcomm_max = rrows["effective_resource_profit_tax_rate"].max() if len(rrows) else np.nan
        # r is the income-tax-based resource profit-tax rate (matches the CbCR
        # income-tax line): prefer the per-commodity rate, fall back to the
        # broader combined effective rate, then the 0.30 default.
        if pd.notna(rcomm_max):
            r_used, r_src = rcomm_max, "resource_profit_tax_rate.csv (income-tax-based, per commodity)"
        elif pd.notna(comb):
            r_used, r_src = comb, "effective_resource_cit_rates.csv (combined effective rate)"
        else:
            r_used, r_src = 0.30, "DEFAULT 0.30 (country not listed in any rate table)"
        # Which correction method applies (mirrors script 4): the ETR-gap fires for
        # included, NON-EITI countries that carry a curated rate; everyone else (EITI,
        # or no curated rate) uses the external payment-based estimate.
        is_eiti = eiti_flag.get(iso, "eiti" in str(dom_method))
        gap_country = (not is_eiti) and (iso in curated_present)

        title = f"COUNTRY RESOURCE INFO  —  {iso}" + (f"  ({name})" if isinstance(name, str) and name else "")
        L = ["=" * 78, title, "=" * 78, ""]
        L.append("This sheet details how the profit and tax reported for this country in country-by-country reports (CbCR)")
        L.append("are adjusted to take out resource-sector (oil, gas and mining) activity, before the")
        L.append("remaining profit is reallocated between countries in the unitary-taxation analysis.")
        L.append("Resource-related profits that are currently taxed as part of the source country's")
        L.append("resource-rent capture strategy are removed from the profit pool to be distributed under")
        L.append("unitary taxation. Resource-related taxes are also removed from the paid taxes.")
        L.append("Otherwise, countries would lose the revenues they legitimately receive")
        L.append("from multinationals' extraction of their resources.")
        L.append("")
        L.append("All monetary values are in billion US dollars.")
        L.append("")
        L.append("RESOURCES")
        L.append(f"Relevant resources: {', '.join(COMM_LABEL.get(x, x) for x in commodities) or 'unknown'}.")
        L.append("")
        L.append("RESOURCE RENT CAPTURE REGIME")
        _cap = max(comb, r_used) if pd.notna(comb) else r_used
        _capsrc = (ecr["source"].get(iso, "") if "source" in ecr.columns else "") or r_src
        L.append(f"Overall, resource PROFIT in this country faces a combined effective tax rate of about {_cap*100:.0f}%")
        L.append("(corporate income tax plus any resource surtax / petroleum tax — a rate on profit, NOT on the")
        L.append(f"economic rent or on gross revenue; source: {_capsrc}).")
        L.append(f"The government's take arrives in three forms (split source: {frac_src}), which affect the reported")
        L.append("profit and tax differently, so the correction tracks them separately:")
        L.append(f"  - Royalties / production entitlements, paid before profit is taxed: {frac_pre} of the take.")
        L.append("    These are a cost that already lowered the reported profit, so they are not deducted again")
        L.append("    from reported profit (the 'resources included' view instead adds them back).")
        L.append(f"  - Resource income tax / corporate tax, paid on profit: {frac_post} of the take.")
        L.append("    This is the part that is removed from the reported tax line when resources are excluded.")
        L.append(f"  - State or national-oil-company dividends from government equity stakes: {frac_eq} of the take.")
        L.append("    This is a return on ownership rather than a tax.")
        L.append("")
        L.append("HOW THE RESOURCE PROFIT IS REMOVED FOR THIS COUNTRY")
        if gap_country:
            L.append(f"This country is corrected by the ETR-gap method: the profit removed is inferred from the CbCR")
            L.append(f"tax itself — the tax paid above what the {c*100:.0f}% statutory rate would imply, converted to profit")
            L.append(f"at the {r_used*100:.0f}% resource rate. The royalty / income-tax / dividend split above feeds the")
            L.append("'resources included' and minimum-royalty views, and is the fallback in any year where the gap")
            L.append("is inert (observed ETR at or below the statutory rate).")
        else:
            L.append("The profit removed is read from the resource payments above: it is the LARGER of the income-")
            L.append("tax-implied profit (income tax / resource rate) and the state-dividend (equity) amount. So for a")
            L.append("state whose take is mostly dividends, the equity bucket is what determines the profit removed,")
            L.append("with the matching tax removed at the resource rate.")
        L.append("")
        L.append("TAX RATES")
        L.append(f"General statutory corporate income tax rate: {c:.3f}. This is the rate applied to ordinary")
        L.append("(non-resource) company profit, and it is the baseline the correction compares against.")
        L.append("Source: the project's statutory CIT-rate dataset (OECD Corporate Tax Statistics and the Tax Foundation).")
        L.append(f"Resource profit-tax rate: {round(r_used, 3)}. This is the rate at which resource-sector profit is")
        L.append("taxed, and it converts a known resource tax payment into the profit behind it (profit = tax / rate).")
        L.append(f"Source: {r_src}.")
        if pd.notna(comb) and comb > r_used + 1e-3:
            L.append(f"This country's TOTAL government take from the resource sector is about {comb} of profit, but")
            L.append("that figure bundles three flows together: royalties, income tax, and state dividends.")
            L.append(f"Only the income-tax part ({round(r_used, 3)}) is used to convert the CbCR income-tax line back")
            L.append("into profit; the royalties and dividends are removed separately (as pre-profit royalties and")
            L.append(f"state-equity income), so using the full {comb} here would double-count them and understate")
            L.append("the resource profit.")
        ecr_notes = ecr["notes"].get(iso, "") if "notes" in ecr.columns else ""
        if isinstance(ecr_notes, str) and ecr_notes.strip():
            L.append(f"Notes on the tax regime: {ecr_notes}")
        L.append("")
        L.append("ALLOCATION OF RESOURCE-RELATED PROFITS TO DIFFERENT HEADQUARTERS")
        L.append("The resource profit removed above is attributed to the home (headquarter) countries of the")
        L.append("multinationals that earned it, so that under unitary taxation it is taken out of the correct")
        L.append("parents' worldwide profit pools instead of being reallocated like ordinary profit.")
        _dm = str(dom_method or "")
        _nm = name if isinstance(name, str) and name else iso
        if "eiti" in _dm:
            L.append(f"For {_nm}, the figures come from EITI reports, so the attribution is bilateral: each")
            L.append("company's payment is matched to its ultimate owner (through Orbis), so the headquarter split")
            if "extrapolated" in _dm:
                L.append("reflects which companies actually paid (carried forward and scaled by reported CbCR profit")
                L.append("in years the EITI reports do not yet cover).")
            else:
                L.append("reflects which companies actually made the payments.")
        else:
            L.append(f"For {_nm}, only a national resource-revenue total is known, so it is split across headquarter")
            if "manual" in _dm:
                L.append("countries using Orbis ownership shares for each commodity, anchored on operator-level")
                L.append("payment-to-government data where it exists.")
            else:
                L.append("countries using Orbis ownership shares for each commodity.")
        _hq = psrc.groupby("hq_iso3")[["pre_profit_payments_usd", "post_profit_payments_usd",
                                       "equity_income_usd"]].sum().sum(axis=1)
        _hqtot = _hq.sum()
        if _hqtot > 0:
            _hq = (_hq / _hqtot).sort_values(ascending=False)
            _domsh = float(_hq.get(iso, 0.0))
            L.append(f"About {_domsh*100:.1f}% of the take is kept by this country's own state and domestic firms")
            L.append("(the domestic share); the take is attributed across headquarters as follows:")
            _shown = 0
            for _h, _sh in _hq.items():
                if _sh < 0.005 or _shown >= 8:
                    break
                L.append(f"    {_h}{' (domestic)' if _h == iso else ''}: {_sh*100:.1f}%")
                _shown += 1
            _rest = float(_hq.iloc[_shown:].sum())
            if _shown < len(_hq) and _rest > 0.005:
                L.append(f"    other ({len(_hq) - _shown} more headquarters): {_rest*100:.1f}%")
        L.append("")
        L.append("SAMPLE COVERAGE")
        L.append(f"Years for which an estimate exists: {src_years.get(iso, [])}.")
        L.append("")
        L.append("RESOURCE CORRECTION, YEAR BY YEAR (US$ billion)")
        L.append("Each row shows, for one year: what this country reported in CbCR (added up over all the parent")
        L.append("companies that reported it), how much of that was removed as resource, and what is left after")
        L.append("the correction and carried into the unitary-taxation analysis. The reported figures are from the")
        L.append("OECD Country-by-Country Report Database; the removed amounts are from this resource correction.")
        L.append("'corrected' columns = reported minus removed; ETR = tax / profit; amounts capped at the reported")
        L.append("cell value.")
        L.append(f"  {'yr':>4} {'profit_reported':>15} {'tax_reported':>13} {'ETR_reported':>13} | "
                 f"{'resource_profit_removed':>23} {'resource_tax_removed':>20} | "
                 f"{'profit_corrected':>16} {'tax_corrected':>13} {'ETR_corrected':>13}")
        for (y, P, T, eo, rp, rtv, prl, tl, el) in yr_rows:
            eo_s = f"{eo:.3f}" if pd.notna(eo) else "    -"
            el_s = f"{el:.3f}" if pd.notna(el) else "    -"
            L.append(f"  {y:>4} {P:>15.2f} {T:>13.2f} {eo_s:>13} | {rp:>23.2f} {rtv:>20.2f} | "
                     f"{prl:>16.2f} {tl:>13.2f} {el_s:>13}")
        L.append("")
        L.append("SOURCES AND CITATIONS")
        for _, rr in rrows.iterrows():
            L.append(f"  - Resource tax rate for {COMM_LABEL.get(rr.commodity, rr.commodity)} "
                     f"({rr.effective_resource_profit_tax_rate}, confidence {rr.confidence}): {str(rr.source_note)}")
        ecr_src = ecr["source"].get(iso, "") if "source" in ecr.columns else ""
        if isinstance(ecr_src, str) and ecr_src.strip():
            L.append(f"  - Source for the combined resource rate: {ecr_src}")
        if len(mrows):
            mr0 = mrows.iloc[0]
            L.append(f"  - Source for the resource-revenue figure (confidence {mr0.confidence}): {str(mr0.source_note)}")
        L.append("  - Detailed, figure-by-figure sources are documented in the files")
        L.append("    docs/extractive/manual_resource_data_sources.md and")
        L.append("    docs/extractive/manual_resource_sources_overview.md.")
        _extra = [str(x) for x in rrows.get("source_note", [])] + [str(ecr_src)]
        if len(mrows):
            _extra += [str(x) for x in mrows.get("source_note", [])]
        _links = _collect_links(iso, data_md, overview_md, _extra)
        if _links:
            L.append("  Reference links for this country (pulled from the files above so this sheet stands alone):")
            for _u in _links:
                L.append(f"    {_u}")
        (OUT / f"{iso}.txt").write_text("\n".join(L), encoding="utf-8")

        severity = len([x for x in flags if x.startswith("Over-strip") or "under-strip" in x])
        summary.append(dict(iso=iso, sources=method_str, cit_c=round(c, 3) if pd.notna(c) else None,
                            r_oilgas=r_og, foreign_etr=round(etr(fP, fT), 3) if pd.notna(etr(fP, fT)) else None,
                            nonres_etr=round(e_for_left, 3) if pd.notna(e_for_left) else None,
                            n_flags=len(flags), severity=severity,
                            flags="; ".join(sorted(flags)) if flags else "ok"))

    s = pd.DataFrame(summary).sort_values(["severity", "n_flags"], ascending=False)
    s.to_csv(OUT / "_SUMMARY.csv", index=False)
    (OUT / "_SUMMARY.txt").write_text(s.to_string(index=False), encoding="utf-8")
    print(f"wrote {len(summary)} country sheets + _SUMMARY to {OUT}")
    print(f"by severity: {dict(s.severity.value_counts().sort_index(ascending=False))}")


if __name__ == "__main__":
    main()
