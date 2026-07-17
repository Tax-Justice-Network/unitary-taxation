# %% [markdown]
# Domestic-vs-foreign profit & profit-shifting, per partner jurisdiction × YEAR,
# with gravity-imputation bootstrap confidence intervals — for one or more UT
# samples (baseline "disaggregated" and/or resource-excluded "excl_resource").
#
# For each partner jurisdiction J we split its booked profit and its profit
# shifting into:
#   - DOMESTIC firms  = MNE groups headquartered in J   (iso_parent == iso_partner)
#   - FOREIGN  firms  = MNE groups headquartered elsewhere (iso_parent != iso_partner)
# aggregated from script 5's per-(parent, partner, year) `misalignment__<spec>.csv`.
#
# Spec: employees_payroll + sales_employees_destcfb (destination CFB-only sales),
# ETR definition = average corrected, MINIMUM ETR = 15% (etrmax_0_15), tax loss
# under BOTH rate modes (CIT-ETR & ETR-ETR), FULL (imputed) sample.
#
# Flow (datasets share the expensive per-seed steps):
#   1. POINT pass (deterministic) per dataset → point estimate.
#   2. N_BOOT seeds: impute_model (resample) → 2_disaggregate (seed) → [4_correcting
#      (seed) for excl_resource] → 5_estimate per dataset → breakdown. Per-seed
#      data files deleted after extraction.
#   3. Combine per dataset → point / mean / median / min / max / SE / 2.5–97.5% CI.
#
# NB: DOMESTIC cells are reported (is_distributed==0); they barely vary across draws
# (a domestic cell's misalignment depends on its parent group's total activity,
# which includes imputed foreign siblings), so domestic CIs are tight, foreign wider.
#
# Heavy: each seed ≈ several minutes (model refit + broad disaggregation + UT ×
# datasets). Sequential; per-seed disk kept bounded.

# %%
import os
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "src")
GR = os.path.join(SRC, "gravity")
DATA_FINAL = os.path.join(ROOT, "data", "final")
GRAV_INT = os.path.join(ROOT, "data", "intermediate", "gravity")
PY = sys.executable

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

if SRC not in sys.path:
    sys.path.insert(0, SRC)
from config import output_dirs  # noqa: E402

# ── Spec ----------------------------------------------------------------------
# employees_payroll (SOTJ headline; no sales term) + sales_employees_destcfb
# (sales attributed to the consumer market via CFB-only share, cfb_share — the
# "destination, CFB only" basis). Override with BOOT_FORMULAS if needed.
FORMULAS = [f.strip() for f in os.environ.get(
    "BOOT_FORMULAS", "employees_payroll,sales_employees_destcfb").split(",") if f.strip()]
ETR_NAME = os.environ.get("BOOT_ETR_NAME", "average")
THRESH = os.environ.get("BOOT_THRESHOLD", "0.15")            # 15% minimum ETR
THRESH_TOKEN = THRESH.replace(".", "_")                      # → "0_15" (matches script 5)
TOPIC = "unitary_taxation_gravity_boot"

N_BOOT = int(os.environ.get("N_BOOT", "5"))
SEED0 = int(os.environ.get("BOOT_SEED0", "1"))

# ── Samples to process. Each shares the per-seed impute_model + 2_disaggregate;
# excl_resource additionally runs 4_correcting on the seed file. The booked-profit
# raw column differs by sample; the misalignment / tax-loss columns are written by
# script 5 on each sample's own profit/tax/ETR family, so they carry over by name.
ALL_DATASETS = {
    "disaggregated": {
        "run_dataset": "disaggregated",
        "profit_col": "profit_loss_before_income_tax_corrected",
        "boot_input": "cbcr_main_disaggregated__boot{s}.csv",
        "needs_script4": False,
        "out_tag": "",
    },
    "excl_resource": {
        "run_dataset": "excl_resource",
        "profit_col": "profit_loss_excl_resource",
        "boot_input": "cbcr_main_excl_resource__boot{s}.csv",
        "needs_script4": True,
        "out_tag": "_excl_resource",
    },
}
_sel = [d.strip() for d in os.environ.get(
    "BOOT_DATASETS", "disaggregated,excl_resource").split(",") if d.strip()]
DATASETS = [ALL_DATASETS[k] for k in _sel if k in ALL_DATASETS]
ANY_SCRIPT4 = any(d["needs_script4"] for d in DATASETS)

# Per-seed data files to delete after extraction (keep disk bounded).
BOOT_CLEANUP = [
    "cbcr_main_disaggregated__boot{s}.csv",
    "cbcr_main_excl_resource__boot{s}.csv",
    "cbcr_main_incl_resource__boot{s}.csv",
    "cbcr_main_excl_resource_floored__boot{s}.csv",
]

# Rate modes for the TAX-LOSS metric. Profit & profit-shifting are rate-mode
# INDEPENDENT (read once from the primary rate file); tax loss is reported under both:
#   cit_etr = loss_cit_gain_etr (loss rate = statutory CIT)
#   etr_etr = loss_etr_gain_etr (loss rate = effective ETR)
RATE_MODES = {"cit_etr": "loss_cit_gain_etr", "etr_etr": "loss_etr_gain_etr"}
PRIMARY_RATE_KEY = "cit_etr"

# Dataset-invariant misalignment columns → output metric (musd). The *_musd_row
# columns are already millions; misaligned_profit is raw USD (/1e6).
INDEP_FIXED = {
    "misaligned_profit": ("profit_shifted_net_musd", 1e6),
    "positive_misalignment_musd_row": ("profit_shifted_into_musd", 1.0),
    "negative_misalignment_musd_row": ("profit_shifted_out_musd", 1.0),
}
TAX_METRICS = {
    "tax_revenue_loss_suffered_musd_row": "tax_loss_suffered",
    "tax_revenue_loss_caused_musd_row": "tax_loss_caused",
}
METRIC_ORDER = (
    ["profit_musd"] + [o for o, _ in INDEP_FIXED.values()]
    + [f"{base}_{rk}_musd" for base in TAX_METRICS.values() for rk in RATE_MODES]
)

# Human-readable metric labels. The active apportionment formula is appended per
# row in the output (metric_description), so every value remains self-describing
# even when sliced away from the `formula` column. "net" = into − out.
METRIC_LABELS = {
    "profit_musd": "Booked profit (US$m)",
    "profit_shifted_net_musd": "Net profit shifted, into - out (US$m)",
    "profit_shifted_into_musd": "Profit shifted in (US$m)",
    "profit_shifted_out_musd": "Profit shifted out (US$m)",
    "tax_loss_suffered_cit_etr_musd": "Tax revenue loss suffered, gains calculated with ETR, losses with CIT (US$m)",
    "tax_loss_suffered_etr_etr_musd": "Tax revenue loss suffered, both gains and losses calculated with ETR (US$m)",
    "tax_loss_caused_cit_etr_musd": "Tax revenue loss caused, gains calculated with ETR, losses with CIT (US$m)",
    "tax_loss_caused_etr_etr_musd": "Tax revenue loss caused, both gains and losses calculated with ETR (US$m)",
}


def rate_indep_metrics(profit_col):
    """Booked profit (sample-specific column → profit_musd) + the fixed set."""
    return {profit_col: ("profit_musd", 1e6), **INDEP_FIXED}


OUT_DIR = output_dirs(TOPIC)[0]
GROUP_KEYS = ["iso_partner", "year", "firm_origin"]

# Partner-level attributes: region + WB income group WITHOUT the tax-haven
# (investment_hub) overwrite (`wb_income_group_official`).
ATTR_COLS = ["region_tjn", "wb_income_group_official"]


def _load_partner_attrs():
    src = pd.read_csv(os.path.join(DATA_FINAL, "cbcr_main_allsubgroupsonly.csv"),
                      usecols=["iso_partner"] + ATTR_COLS, low_memory=False)
    src = src[src["iso_partner"].notna()]

    def first_valid(s):
        v = s.dropna()
        return v.iloc[0] if len(v) else np.nan
    return src.groupby("iso_partner", as_index=False).agg(
        {c: first_valid for c in ATTR_COLS})


PARTNER_ATTRS = _load_partner_attrs()


def run_script5(run_dataset, input_file=None):
    """Run script 5 for the configured formulas at the 15% / average-ETR spec (all
    rate modes), into the TOPIC/<run_dataset> tables dir. input_file=None uses the
    canonical input for that dataset (DATASET_CONFIGS); else a per-seed boot file."""
    env = dict(os.environ)
    env.update({
        "RUN_DATASET": run_dataset,
        "REPORTED_ONLY": "0",
        "ETR_THRESHOLDS": THRESH,
        "RUN_FORMULAS": ",".join(FORMULAS),
        "RUN_OUTPUT_TOPIC": TOPIC,
        "SKIP_SELECTED_SUMMARY": "1",   # we read the misalignment files directly
    })
    if input_file is not None:
        env["RUN_INPUT_FILE"] = input_file
    subprocess.run([PY, "5_estimate_profit_shifting.py"], cwd=SRC, env=env,
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_script4(boot_suffix=""):
    """Resource-correct cbcr_main_disaggregated{suffix}.csv → cbcr_main_excl_resource
    {suffix}.csv (+ incl / floored) via the DISAGG_BOOT_SUFFIX hook."""
    env = dict(os.environ)
    env["DISAGG_BOOT_SUFFIX"] = boot_suffix
    subprocess.run([PY, "4_correcting_cbcr_for_resource_payments.py"], cwd=SRC,
                   env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _read_misalignment(ds, formula, rate_mode):
    est_dir = OUT_DIR / ds["run_dataset"]
    stub = f"misalignment__{formula}__etrdef_{ETR_NAME}__etrmax_{THRESH_TOKEN}__{rate_mode}.csv"
    path = est_dir / stub
    if not path.exists():
        print(f"    [warn] missing {path}")
        return None
    keep = (["iso_parent", "iso_partner", "partner_jurisdiction", "year",
             ds["profit_col"]] + list(INDEP_FIXED) + list(TAX_METRICS))
    df = pd.read_csv(path, usecols=lambda c: c in keep, low_memory=False)
    df = df[~df["iso_partner"].isna()].copy()
    df["firm_origin"] = np.where(df["iso_parent"] == df["iso_partner"],
                                 "domestic", "foreign")
    return df


def _agg(df, cols):
    for c in cols:
        if c not in df.columns:
            df[c] = np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.groupby(GROUP_KEYS, as_index=False)[cols].sum(min_count=1)


def breakdown_one(ds, formula):
    """Per (iso_partner, YEAR, firm_origin): booked profit + profit-shifting (from
    the primary rate file) + tax loss under each rate mode. Returns long."""
    rim = rate_indep_metrics(ds["profit_col"])
    base = _read_misalignment(ds, formula, RATE_MODES[PRIMARY_RATE_KEY])
    if base is None:
        return None
    g = _agg(base, list(rim))
    for raw, (out, div) in rim.items():
        g[out] = g[raw] / div
    g = g[GROUP_KEYS + [o for o, _ in rim.values()]]
    for rk, rate_mode in RATE_MODES.items():
        d = base if rk == PRIMARY_RATE_KEY else _read_misalignment(ds, formula, rate_mode)
        if d is None:
            continue
        gt = _agg(d, list(TAX_METRICS)).rename(
            columns={raw: f"{TAX_METRICS[raw]}_{rk}_musd" for raw in TAX_METRICS})
        g = g.merge(gt, on=GROUP_KEYS, how="outer")
    names = (base.dropna(subset=["partner_jurisdiction"])
             .drop_duplicates("iso_partner")
             .set_index("iso_partner")["partner_jurisdiction"])
    g["partner_jurisdiction"] = g["iso_partner"].map(names)
    g["formula"] = formula
    return g.melt(
        id_vars=["iso_partner", "partner_jurisdiction", "year", "formula", "firm_origin"],
        value_vars=[m for m in METRIC_ORDER if m in g.columns],
        var_name="metric", value_name="value")


def breakdown_all(ds):
    frames = [breakdown_one(ds, f) for f in FORMULAS]
    frames = [x for x in frames if x is not None]
    return pd.concat(frames, ignore_index=True) if frames else None


def write_outputs(ds, point, draws):
    """Combine point + draws → stats, write the tidy long + wide-per-metric files
    with the dataset's out_tag suffix."""
    keys = ["iso_partner", "partner_jurisdiction", "year", "formula", "firm_origin", "metric"]
    stat_cols = ["boot_mean", "boot_median", "boot_min", "boot_max",
                 "boot_se", "ci_lower", "ci_upper", "n_draws"]
    if draws:
        alld = pd.concat(draws, ignore_index=True)
        g = alld.groupby(keys)["value"]
        stats = pd.DataFrame({
            "boot_mean": g.mean(), "boot_median": g.median(),
            "boot_min": g.min(), "boot_max": g.max(), "boot_se": g.std(ddof=1),
            "ci_lower": g.quantile(0.025), "ci_upper": g.quantile(0.975),
            "n_draws": g.count(),
        }).reset_index()
    else:
        stats = point[keys].copy()
        for c in stat_cols:
            stats[c] = np.nan

    out = point.merge(stats, on=keys, how="left").merge(PARTNER_ATTRS, on="iso_partner", how="left")
    for c in ATTR_COLS:
        out[c] = out[c].fillna("unknown")
    out["ci_excludes_zero"] = (out["ci_lower"] > 0) | (out["ci_upper"] < 0)
    out["metric_description"] = (
        out["metric"].map(METRIC_LABELS).fillna(out["metric"])
        + " - formula: " + out["formula"].astype(str)
    )
    rank = {m: i for i, m in enumerate(METRIC_ORDER)}
    out = out.sort_values(["formula", "iso_partner", "year", "firm_origin", "metric"],
                          key=lambda c: c.map(rank) if c.name == "metric" else c).reset_index(drop=True)
    lead = ["iso_partner", "partner_jurisdiction", "region_tjn",
            "wb_income_group_official", "year", "formula", "firm_origin",
            "metric", "metric_description"]
    out = out[lead + [c for c in out.columns if c not in lead]]

    tag = ds["out_tag"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lp = OUT_DIR / f"domestic_foreign_profit_shifting__ci{tag}.csv"
    out.to_csv(lp, index=False)
    print(f"  wrote {lp.name}  ({len(out)} rows)")
    for metric in METRIC_ORDER:
        sub = out[out["metric"] == metric]
        if sub.empty:
            continue
        wide = sub.pivot_table(
            index=["iso_partner", "partner_jurisdiction", "region_tjn",
                   "wb_income_group_official", "year"],
            columns=["formula", "firm_origin"],
            values=["point", "boot_mean", "boot_median", "boot_min", "boot_max",
                    "ci_lower", "ci_upper"], aggfunc="first")
        wide.columns = ["__".join((f, o, st)) for (st, f, o) in wide.columns]
        wide = wide.reindex(sorted(wide.columns), axis=1).reset_index()
        wide.to_csv(OUT_DIR / f"domestic_foreign_by_country_year__{metric}{tag}.csv", index=False)
    return out


# %%
# Run UT + breakdown for every dataset, ordered so each sample uses the ETR that
# FITS it. Non-resource datasets run FIRST, reading the clean (un-stitched)
# disaggregated file → script 5's 15% haven test falls back to etr_average_corrected.
# Then 4_correcting runs (it stitches etr_average_excl_resource / resource_factor_usd
# onto that file); then excl_resource runs, reading the resource-corrected file →
# etr_average_excl_resource. seed=None → point pass (canonical inputs).
DATASETS_SORTED = sorted(DATASETS, key=lambda d: d["needs_script4"])


def run_all_datasets(seed):
    res = {}
    s4_done = False
    for ds in DATASETS_SORTED:
        if ds["needs_script4"] and not s4_done:
            run_script4("" if seed is None else f"__boot{seed}")
            s4_done = True
        inp = None if seed is None else ds["boot_input"].format(s=seed)
        run_script5(ds["run_dataset"], inp)
        res[ds["run_dataset"]] = breakdown_all(ds)
    return res


# %%
# 1) POINT pass. Regenerate a clean canonical disaggregated first, so the baseline
# UT reads an un-stitched file (and 4_correcting never reads a polluted one — which
# also keeps re-runs idempotent).
print(f"Datasets: {[d['run_dataset'] for d in DATASETS]} | formulas={FORMULAS} | "
      f"etrmax={THRESH} | N_BOOT={N_BOOT}", flush=True)
print("POINT pass — regenerating clean canonical disaggregated …", flush=True)
subprocess.run([PY, "2_disaggregate_aggregated_values.py"], cwd=SRC,
               env=dict(os.environ), check=True,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
points = {}
for rd, p in run_all_datasets(None).items():
    if p is None:
        raise SystemExit(f"No misalignment files for point pass ({rd}) — check spec.")
    points[rd] = p.rename(columns={"value": "point"})

# %%
# 2) Bootstrap seeds — shared impute_model + 2_disaggregate; per-dataset UT via
# run_all_datasets (baseline reads the clean boot file, excl_resource the corrected).
draws = {ds["run_dataset"]: [] for ds in DATASETS}
for s in range(SEED0, SEED0 + N_BOOT):
    print(f"  seed {s}/{SEED0 + N_BOOT - 1} …", flush=True)
    subprocess.run([PY, "impute_model.py"], cwd=GR,
                   env={**os.environ, "GRAVITY_BOOT_SEED": str(s)},
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([PY, "2_disaggregate_aggregated_values.py"], cwd=SRC,
                   env={**os.environ, "GRAVITY_BOOT_SEED": str(s)},
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for rd, d in run_all_datasets(s).items():
        if d is not None:
            d["seed"] = s
            draws[rd].append(d)
    # cleanup per-seed data files
    for tmpl in BOOT_CLEANUP:
        f = os.path.join(DATA_FINAL, tmpl.format(s=s))
        if os.path.exists(f):
            os.remove(f)
    ga = os.path.join(GRAV_INT, f"gravity_imputed_activity__boot{s}.csv")
    if os.path.exists(ga):
        os.remove(ga)
    print(f"    seed {s} done", flush=True)

# %%
# 3) Combine + write per dataset.
for ds in DATASETS:
    rd = ds["run_dataset"]
    print(f"\n=== {rd} ===")
    out = write_outputs(ds, points[rd], draws[rd])
    tot = (out[out["metric"] == "profit_shifted_musd"]
           .groupby(["formula", "firm_origin"])["point"].sum().reset_index())
    print("  profit shifted (point, sum partners&years), musd:")
    print(tot.to_string(index=False))
print("\nDone.")
