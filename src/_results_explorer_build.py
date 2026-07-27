"""
Build the interactive results explorer (single self-contained HTML).

Reads the reported-only estimation summaries for the three scenarios and
exports, per (scenario × formula family × sales measure × rate mode), the
per-country yearly-average revenue change (constant BASE_YEAR USD) — plus the
pure single-factor vectors (employees, payroll, sales, assets) recovered by
inverting the estimated formula grid, which power the app's build-your-own-
formula mode (exact for taxable profit, a close approximation for revenue
because the gain/loss valuation rate depends on the sign of the misalignment).

Embeds the data and the brand Work Sans fonts into
`_results_explorer_template.html` → `output/app/unitary_taxation_explorer.html`.

Refresh after a pipeline rerun: `python _results_explorer_build.py`.
Not part of the replication package (dissemination tool).
"""
import base64
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import _exhibit_helpers as _eh

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_SRC = Path(__file__).resolve().parent
_ROOT = _SRC.parent
OUT = _ROOT / "output" / "app" / "unitary_taxation_explorer.html"

SCENARIOS = {"ignore": "baseline", "excl": "excl_resource",
             "floor": "excl_resource_floored",
             # sensitivity: the IGF-ATAF minimum royalty enforced for EVERY
             # producing country (the headline floor binds only for low- and
             # lower-middle-income producers)
             "floor_all": "excl_resource_floored_allcountries"}
# rate modes: gains valued at statutory CIT, losses at the effective rate
# (headline); both legs at the effective rate (conservative); and the
# optimistic bound where profit reallocated AWAY is valued only at the
# bottom-10% effective rate observed in each jurisdiction (the rate of the
# most lightly taxed multinationals), gains still at CIT.
RATES = {"cit": "loss_cit_gain_etr", "etr": "loss_etr_gain_etr",
         "opt": "losers_p10_gainers_cit"}
# formula families: (key, label, weights [employees, payroll, sales, assets], uses_sales)
FAMILIES = [
    ("sales_employees", "Sales + employees", [0.5, 0.0, 0.5, 0.0], True),
    ("employees_payroll", "Employees + payroll", [0.5, 0.5, 0.0, 0.0], False),
    ("ccctb", "CCCTB", [1/6, 1/6, 1/3, 1/3], True),
    ("three_factors", "Three-factor", [1/3, 0.0, 1/3, 1/3], True),
    ("double_weighted_sales", "Double-weighted sales", [0.25, 0.0, 0.5, 0.25], True),
]
# sales measures: (key, suffix on the family name, label)
MEASURES = [
    ("origin", "", "Origin (where booked)"),
    ("dest", "_destmnedds", "Destination (complete measure)"),
    ("dest_pe", "_destmnedds_nexus", "Destination + physical establishment"),
    ("dest_nodigital", "_destmne", "Destination, without remote digital services"),
    ("dest_consumer", "_destcfb", "Destination, consumer-facing only"),
]
ETR = "domfor"
THRESHOLD = "inf"
# Public URLs for the paper and methodology note (leave empty until online).
PAPER_URL = ""
METHODOLOGY_URL = ""
YEARS = _eh.AVG_YEARS
NYRS = _eh.N_AVG_YEARS
DEFL = config.deflator_to_base()
EXCL = set(config.DATA_QUALITY_EXCLUSIONS)   # presentation exclusions


def _summary(scenario):
    p = os.path.join(str(config.estimates_dir("reported_only", scenario)),
                     "tables", "summary_country_year_long.csv")
    if not os.path.exists(p):
        print(f"  [missing] {p}")
        return None
    d = pd.read_csv(p, usecols=["iso_partner", "year", "formula_name", "etr_name",
                                "rate_mode", "etr_threshold", "revenue_gain_from_ut",
                                "current_tax_paid_cash_musd"],
                    low_memory=False)
    # 2020 stays IN the frame (the year view shows it); the per-country
    # averages filter it out downstream (YEARS excludes it).
    # The four DATA_QUALITY_EXCLUSIONS micro-states are KEPT here (with the thin-coverage
    # flag), to match the report tables and the overview Excel, which also keep them.
    d = d[(d["etr_name"].isin([ETR, "average"])) & (d["year"].isin(YEARS + [2020]))
          & (d["etr_threshold"].astype(str) == THRESHOLD)]
    d["_w"] = d["year"].map(DEFL)
    return d


def main():
    print("Building results-explorer data …")
    frames = {k: _summary(s) for k, s in SCENARIOS.items()}
    frames = {k: v for k, v in frames.items() if v is not None}
    if "excl" not in frames:
        raise SystemExit("excl_resource summary missing — run the pipeline first")

    isos = sorted(set().union(*[set(v["iso_partner"]) for v in frames.values()]))
    grp = _eh.income_group("reported_only").to_dict()
    reg = _eh.region("reported_only").to_dict()
    # Continent view: fold the Caribbean/American-islands region into Latin
    # America (the UN "Latin America and the Caribbean" grouping) and Oceania
    # into Asia ("Asia & Oceania", the OECD's own CbCR continent grouping) —
    # app display only; the paper tables keep the finer split.
    REGION_MERGE = {"Caribbean/American isl.": "Latin America & Caribbean",
                    "Latin America": "Latin America & Caribbean",
                    "Asia": "Asia & Oceania",
                    "Oceania": "Asia & Oceania"}
    def _region(i):
        r = reg.get(i) or ""
        return REGION_MERGE.get(r, r)
    # few-observations flag (the paper's coverage flag [2]: an estimate resting on
    # very few reported cells / parents / years).
    thin = _eh.thin_isos()
    countries = [[i, _eh.cname(i), grp.get(i, "high_income"), _region(i),
                  1 if i in thin else 0] for i in isos]
    idx = {i: n for n, i in enumerate(isos)}

    ALL_YEARS = sorted(YEARS + [2020])   # the year view shows 2020 too

    def _spec_rows(d, formula, rate):
        # prefer the headline ETR family (domfor); fall back to the average
        # family for rate modes only computed there (the p10 optimistic bound).
        for en in (ETR, "average"):
            cand = d[(d["formula_name"] == formula) & (d["rate_mode"] == rate)
                     & (d["etr_name"] == en)]
            if not cand.empty:
                return cand
        return None

    def per_country(d, formula, rate):
        s = _spec_rows(d, formula, rate)
        if s is None:
            return None
        s = s[s["year"].isin(YEARS)]        # paper window: 2020 excluded
        v = ((s["revenue_gain_from_ut"] * s["_w"]).groupby(s["iso_partner"]).sum()
             / NYRS)
        out = [None] * len(isos)
        for i, val in v.items():
            out[idx[i]] = round(float(val), 2)
        return out

    def per_year_world(d, formula, rate):
        """World net revenue gain per year ($bn, deflated) — the year view."""
        s = _spec_rows(d, formula, rate)
        if s is None:
            return None
        v = (s["revenue_gain_from_ut"] * s["_w"]).groupby(s["year"]).sum() / 1e3
        return [round(float(v.get(y, 0.0)), 1) for y in ALL_YEARS]

    # preset series: scenario | family | measure | rate  → per-country musd/yr
    # (+ the same key in `yearly`: world net gain per year, $bn, for the year view)
    series = {}
    yearly = {}
    for sk, d in frames.items():
        for fk, _lab, _w, uses_sales in FAMILIES:
            for mk, suffix, _mlab in MEASURES:
                fname = fk + (suffix if uses_sales else "")
                for rk, rmode in RATES.items():
                    key = f"{sk}|{fk}|{mk}|{rk}"
                    if not uses_sales and mk != "origin":
                        continue   # measure-invariant; the app falls back to origin
                    arr = per_country(d, fname, rmode)
                    if arr is not None:
                        series[key] = arr
                        yw = per_year_world(d, fname, rmode)
                        if yw is not None:
                            yearly[key] = yw

    # Single-factor vectors [E, P, S, A] per (scenario, rate, MEASURE), by
    # least-squares inversion of that measure's own five-family grid (the
    # employees_payroll family is measure-invariant and anchors P). Fitting
    # each measure separately absorbs most of the sign-dependent valuation
    # nonlinearity, so custom formulas stay a close approximation.
    W = np.array([f[2] for f in FAMILIES], dtype=float)       # 5 x 4 [E,P,S,A]
    factors = {}
    for sk in frames:
        for rk in RATES:
            for mk, _suffix, _mlab in MEASURES:
                fam_arrs = []
                ok = True
                for fk, _lab, _w, uses_sales in FAMILIES:
                    a = series.get(f"{sk}|{fk}|{mk if uses_sales else 'origin'}|{rk}")
                    if a is None:
                        ok = False
                        break
                    fam_arrs.append([np.nan if v is None else v for v in a])
                if not ok:
                    continue
                Y = np.array(fam_arrs, dtype=float)           # 5 x n
                sol, *_ = np.linalg.lstsq(W, np.nan_to_num(Y), rcond=None)
                nanmask = np.isnan(Y).any(axis=0)
                packed = {}
                for name, vec in zip(["E", "P", "S", "A"], sol):
                    packed[name] = [None if nanmask[j] else round(float(vec[j]), 2)
                                    for j in range(len(isos))]
                factors[f"{sk}|{rk}|{mk}"] = packed

    # current MNE cash tax (excl basis — the % denominator). NB the frames carry
    # BOTH the domfor and average ETR families, so the ETR filter is essential:
    # without it every country-year is summed twice and all percentages halve.
    d = frames["excl"]
    sall = d[(d["formula_name"] == _eh.HEADLINE_FORMULA) & (d["rate_mode"] == RATES["cit"])
             & (d["etr_name"] == ETR)]
    s = sall[sall["year"].isin(YEARS)]          # per-country average: 2020 excluded
    cash = ((pd.to_numeric(s["current_tax_paid_cash_musd"], errors="coerce") * s["_w"])
            .groupby(s["iso_partner"]).sum() / NYRS)
    cashtax = [round(float(cash.get(i, 0.0)), 2) for i in isos]
    # world cash per year incl. 2020 ($bn) — the year view's % denominator
    _cy = ((pd.to_numeric(sall["current_tax_paid_cash_musd"], errors="coerce") * sall["_w"])
           .groupby(sall["year"]).sum() / 1e3)
    cashyear = [round(float(_cy.get(y, 0.0)), 1) for y in ALL_YEARS]

    # minimum-royalty floor add-on per country (post-gate; reported rows, cat1)
    roy = _eh.floor_royalty_musd("reported_only")
    royalty = [round(float(roy.get(i, 0.0)), 2) for i in isos]
    # all-countries floor sensitivity (no income-group gate)
    try:
        roy_all = _eh.floor_royalty_musd(
            "reported_only", fname="cbcr_main_excl_resource_floored_allcountries.csv")
        royalty_all = [round(float(roy_all.get(i, 0.0)), 2) for i in isos]
    except FileNotFoundError:
        royalty_all = None
        print("  [floor_all] all-countries floored dataset missing — royalty_all skipped")

    data = {
        "meta": {
            "window": "yearly average 2016–2022 (2020 excluded), constant 2025 USD",
            "units": "million USD per year",
            "etr_family": ETR,
            "headline": {"formula": "sales_employees", "measure": "dest",
                         "scen": "excl", "rate": "cit"},
            # employees_payroll stays in the factor grid (it identifies the
            # payroll factor for custom formulas) but is not offered as a preset.
            "families": [[k, lab, w] for k, lab, w, _us in FAMILIES
                         if k != "employees_payroll"],
            "measures": [[k, lab] for k, _sfx, lab in MEASURES],
            "rates": [[k] for k in RATES],   # display order = insertion order
            # Public links (fill in when the paper / methodology note are online;
            # empty strings render as plain text instead of a link).
            "links": {"paper": PAPER_URL, "methodology": METHODOLOGY_URL},
            "generated": pd.Timestamp.today().strftime("%Y-%m-%d"),
        },
        "countries": countries,
        "cashtax": cashtax,
        "cashyear": cashyear,
        "royalty": royalty,
        "royalty_all": royalty_all,   # None until the all-countries dataset exists
        "series": series,
        "yearly": yearly,
        "factors": factors,
    }
    data["meta"]["years"] = ALL_YEARS

    # World scale-up factor (reported sample → all multinationals worldwide),
    # from 7a's coverage table: ratio of the scaled-up net world revenue gain
    # to the sample net gain, averaged over the paper years. The paper scales
    # the WORLD aggregate only (not countries or income groups), so this factor
    # is applied to the live world counter alone.
    scale = None
    timeline = []
    sf_p = os.path.join(_eh.tabledir("reported_only"), "scaleup_yearly.csv")
    if os.path.exists(sf_p):
        sf = pd.read_csv(sf_p)
        sfa = sf[sf["year"].isin(YEARS)]
        num = sfa["scaled_up_net_bn"].mean()
        den = sfa["revenue_gain_net_bn"].mean()
        if den and den > 0:
            scale = round(float(num / den), 4)
        # Per-year world NET revenue gain (headline spec) — the Figure-1 series
        # for the app's global timeline: [year, sample bn, scaled-to-all-MNEs bn,
        # world current MNE tax bn]. ALL years incl. 2020 (matching Figure 1),
        # constant BASE_YEAR USD. Kept as the fallback series (custom formulas /
        # stale data); the year view otherwise uses `yearly` + `cashyear`.
        for _, r in sf.sort_values("year").iterrows():
            yr = int(r["year"])
            cash_y = cashyear[ALL_YEARS.index(yr)] if yr in ALL_YEARS else 0.0
            timeline.append([yr,
                             round(float(r["revenue_gain_net_bn"]), 1),
                             round(float(r["scaled_up_net_bn"]), 1),
                             float(cash_y)])
        # per-year coverage scale factors (sample → all MNEs), for scaling any
        # spec's year series in the app
        _sfy = {int(r["year"]): round(float(r["scale_factor"]), 4)
                for _, r in sf.iterrows()}
        data["meta"]["sfyear"] = [_sfy.get(y) for y in ALL_YEARS]
    data["meta"]["scale"] = scale   # None → counter falls back to sample
    data["meta"]["timeline"] = timeline   # [] → app hides the timeline
    data["meta"].setdefault("sfyear", [])
    print(f"  world scale-up factor (sample → all MNEs): {scale}")

    for sk in SCENARIOS:
        key = f"{sk}|sales_employees|dest|cit"
        if key in series:
            tot = sum(v for v in series[key] if v) / 1000
            if sk == "floor":
                tot += sum(royalty) / 1000
            elif sk == "floor_all" and royalty_all:
                tot += sum(royalty_all) / 1000
            sc = (" | scaled ≈ %.0f" % (tot * scale)) if scale else ""
            print(f"  world Δrevenue [{sk}] headline: {tot:+.1f} bn/yr{sc}")

    css = []
    for w in (400, 600, 700):
        p = _ROOT / "assets" / "fonts" / f"WorkSans-{w}.ttf"
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        css.append(
            "@font-face { font-family: 'Work Sans'; font-style: normal; "
            f"font-weight: {w}; font-display: swap; "
            f"src: url(data:font/ttf;base64,{b64}) format('truetype'); }}"
        )
    fonts_css = "\n  ".join(css)

    template = (_SRC / "_results_explorer_template.html").read_text(encoding="utf-8")
    html = template.replace("/*__FONTS__*/", fonts_css)
    html = html.replace("/*__DATA__*/", json.dumps(data, separators=(",", ":")))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}  ({OUT.stat().st_size/1e6:.1f} MB, {len(isos)} countries, "
          f"{len(series)} series, {len(factors)} factor sets)")

    # ── web export ───────────────────────────────────────────────────────
    # Publish-ready copy at the repo root: unitary_taxation_explorer/index.html.
    # This folder is what gets served (GitHub Pages via Actions, or handed as a
    # single static file to the organisation's web team) — see its README.md.
    web = _ROOT / "unitary_taxation_explorer"
    web.mkdir(exist_ok=True)
    (web / "index.html").write_text(html, encoding="utf-8")
    xlsx = OUT.parent / "unitary_taxation_baseline_results.xlsx"
    if xlsx.exists():
        import shutil
        shutil.copy2(xlsx, web / xlsx.name)
    print(f"web export -> {web / 'index.html'}")


if __name__ == "__main__":
    main()
