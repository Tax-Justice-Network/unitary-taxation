# %% [markdown]
# NOT PART OF THE REPLICATION PACKAGE. Since the 7-series became concept
# scripts (2026-07-25), each script produces its main-text AND appendix
# exhibits in one pass, so there is a single driver: _run_paper_main.py.
# This file is kept only so old command lines don't break.

import runpy

runpy.run_path(__file__.replace("_run_paper_appendix", "_run_paper_main"),
               run_name="__main__")
