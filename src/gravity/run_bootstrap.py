# %% [markdown]
# Bootstrap the gravity imputation to get standard errors on the UT misalignment
# estimates (García-Bernardo & Janský 2024 train 1000× on bootstrapped samples).
#
# For each seed s the full chain is re-run end to end, propagating imputation
# uncertainty into the country estimates:
#   1. impute_model.py  (GRAVITY_BOOT_SEED=s) — resample training cells, refit,
#      predict -> gravity_imputed_activity__boot{s}.csv
#   2. 2_disaggregate   (GRAVITY_BOOT_SEED=s)
#      -> cbcr_main_disaggregated__boot{s}.csv
#   3. 4_correcting     (DISAGG_BOOT_SUFFIX=__boot{s}) — apply the resource
#      correction to the seed's disaggregated file
#      -> cbcr_main_{DATASET}__boot{s}.csv  (DATASET defaults to excl_resource)
#   4. 5_estimate       (RUN_DATASET=DATASET, RUN_INPUT_FILE=that file,
#      RUN_OUTPUT_TOPIC=unitary_taxation_gravity_boot) -> country estimates
# The CI therefore sits on the SAME dataset + formula spec as the reported-only
# headline (excl_resource, sales_employees_destmnedds / domfor / loss_cit_gain_etr),
# in imputed mode (REPORTED_ONLY=0 — the only mode where imputation SE is non-zero).
# Then per (iso_partner, year) we record mean / SE / 2.5–97.5% CI across draws.
#
# Heavy: each draw ≈ a few minutes. Set N_BOOT modestly (env) and scale up for
# a production run. Defaults pick the headline spec + reporter-only mode.

# %%
import glob
import os
import subprocess
import sys

import numpy as np
import pandas as pd

try:  # the OneDrive path contains non-cp1252 chars; keep the final print from crashing
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "src")
GR = os.path.join(SRC, "gravity")
PY = sys.executable

N_BOOT = int(os.environ.get("N_BOOT", "100"))
SEED0 = int(os.environ.get("BOOT_SEED0", "1"))   # seed 0 reserved for point est.
# Default FULL mode: imputation uncertainty only enters when imputed rows are
# used. In reporter-only mode (REPORTED_ONLY=1) the disaggregated rows are
# dropped, so bootstrapping the imputation yields ~0 SE by construction.
REPORTED = os.environ.get("REPORTED_ONLY", "0")
# Match the reported-only HEADLINE specification: excl_resource dataset +
# sales_employees_destmnedds / domfor ETR / loss_cit_gain_etr formula spec.
DATASET = os.environ.get("BOOT_DATASET", "excl_resource")
SPEC = os.environ.get(
    "BOOT_SPEC",
    "sales_employees_destmnedds__etrdef_domfor__etrmax_inf__loss_cit_gain_etr",
)
TOPIC = "unitary_taxation_gravity_boot"
_sub = "_reported" if REPORTED not in ("0", "false", "False", "") else ""
# Resolve through config.output_dirs so the nested-layout remap applies
# (gravity_boot lives under output/checks/bootstrap_with_imputed_rows/ or
# output/checks/bootstrap_reported_only/; the SE table goes to
# output/checks/destination_sales/tables/).
if SRC not in sys.path:
    sys.path.insert(0, SRC)
from config import output_dirs  # noqa: E402
EST_GLOB = str(output_dirs(f"{TOPIC}{_sub}")[0]
               / "disaggregated" / f"country_estimates__{SPEC}.csv")
METRIC = os.environ.get("BOOT_METRIC", "revenue_gain_from_ut")


def run(script, cwd, extra_env):
    env = dict(os.environ)
    env.update(extra_env)
    subprocess.run([PY, script], cwd=cwd, env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# %%
draws = []
for s in range(SEED0, SEED0 + N_BOOT):
    run("impute_model.py", GR, {"GRAVITY_BOOT_SEED": str(s)})
    run("2_disaggregate_aggregated_values.py", SRC,
        {"GRAVITY_BOOT_SEED": str(s)})
    # Per-draw resource correction: cbcr_main_disaggregated__boot{s}.csv ->
    # cbcr_main_{DATASET}__boot{s}.csv, so the CI sits on the headline dataset.
    # (skipped when DATASET is the uncorrected disaggregated baseline.)
    if DATASET != "disaggregated":
        run("4_correcting_cbcr_for_resource_payments.py", SRC,
            {"DISAGG_BOOT_SUFFIX": f"__boot{s}"})
    run("5_estimate_profit_shifting.py", SRC, {
        "RUN_DATASET": DATASET,
        "RUN_INPUT_FILE": f"cbcr_main_{DATASET}__boot{s}.csv",
        "RUN_OUTPUT_TOPIC": TOPIC,
        "REPORTED_ONLY": REPORTED,
    })
    f = glob.glob(EST_GLOB)
    if not f:
        print(f"  seed {s}: estimate file not found, skipping")
        continue
    d = pd.read_csv(f[0])[["iso_partner", METRIC]]
    d = d.groupby("iso_partner", as_index=False)[METRIC].sum()
    d["seed"] = s
    draws.append(d)
    # Keep disk flat: the metric for this seed is now captured in `draws`, so drop
    # the seed's per-draw datasets. With the per-draw script-4 step each seed writes
    # several ~40MB files (disaggregated + excl_resource + floored + allrows + incl);
    # 100 draws would otherwise fill C:. (The gravity_boot estimate folder overwrites
    # per seed — same topic/spec — so it does not accumulate.)
    _final = os.path.join(ROOT, "data", "final")
    for _f in (f"cbcr_main_disaggregated__boot{s}.csv",
               f"cbcr_main_excl_resource__boot{s}.csv",
               f"cbcr_main_excl_resource_floored__boot{s}.csv",
               f"cbcr_main_excl_resource_floored_allrows__boot{s}.csv",
               f"cbcr_main_incl_resource__boot{s}.csv"):
        try:
            os.remove(os.path.join(_final, _f))
        except OSError:
            pass
    try:
        os.remove(os.path.join(GR, f"gravity_imputed_activity__boot{s}.csv"))
    except OSError:
        pass
    print(f"  seed {s} done ({len(draws)}/{N_BOOT})", flush=True)

# %%
alld = pd.concat(draws, ignore_index=True)
g = alld.groupby("iso_partner")[METRIC]
out = pd.DataFrame({
    "boot_mean": g.mean(),
    "boot_se": g.std(ddof=1),
    "ci_lo_2.5": g.quantile(0.025),
    "ci_hi_97.5": g.quantile(0.975),
    "n_draws": g.count(),
}).reset_index()
dest = output_dirs("destination_sales")[0] / f"gravity_bootstrap_SEs__{SPEC}.csv"
out.to_csv(dest, index=False)
print(f"\nBootstrap SEs: {len(out)} jurisdictions, {N_BOOT} draws, "
      f"dataset={DATASET}, {'reporter-only' if _sub else 'full/imputed'} mode -> {dest}")
print(out.sort_values("boot_mean").head(8).to_string(index=False))
