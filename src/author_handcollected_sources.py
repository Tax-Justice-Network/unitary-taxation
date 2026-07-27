"""
9k — Appendix F: overview of hand-collected data sources (read-only).

Assembles a tidy "hand-collected data sources" table from the three manual files:
  data/raw/resources/manual_resource_revenue.csv   (resource govt revenue: confidence, source_note)
  data/raw/resources/resource_profit_tax_rate.csv  (curated profit-tax rates: rate, confidence, note)
  data/raw/macro_variables/manual_imputation_values.csv            (small-territory GDP/pop/CIT/wage: source_url, note)

Writes a combined CSV + markdown (and per-category CSVs) to
output/unitary_taxation/across_samples/paper_tables/.
Usage: python 9k_handcollected_sources_table.py
"""
import os
import sys
import pandas as pd

_SRC = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SRC)
sys.path.insert(0, _SRC)
import config  # noqa: E402

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_NAME_OVR = getattr(config, "COUNTRY_NAME_OVERRIDES", {})
try:
    import pycountry
    def _name(iso):
        if str(iso) in _NAME_OVR:
            return _NAME_OVR[str(iso)]
        try:
            c = pycountry.countries.get(alpha_3=str(iso))
            return c.name if c else str(iso)
        except Exception:
            return str(iso)
except Exception:
    def _name(iso):
        return _NAME_OVR.get(str(iso), str(iso))


def _read(rel):
    p = os.path.join(_ROOT, rel)
    # the resource CSVs carry leading '#'-comment header lines
    return pd.read_csv(p, low_memory=False, comment="#") if os.path.exists(p) else pd.DataFrame()


def _first(s):
    s = s.dropna()
    return s.iloc[0] if len(s) else ""


def main():
    tables_dir, _ = config.output_dirs("deliverables/paper_tables")
    rows = []

    # A. Resource government revenue (per source country × commodity)
    rev = _read("data/raw/resources/manual_resource_revenue.csv")
    if not rev.empty:
        g = (rev.groupby(["source_iso3", "commodity"], as_index=False)
                .agg(confidence=("confidence", _first),
                     source=("source_note", _first)))
        for _, r in g.iterrows():
            rows.append(dict(category="Resource government revenue",
                             country=_name(r["source_iso3"]), iso3=r["source_iso3"],
                             commodity_or_variable=r["commodity"],
                             confidence=r["confidence"], source=r["source"]))

    # B. Resource profit-tax rates (per source country × commodity)
    rate = _read("data/raw/resources/resource_profit_tax_rate.csv")
    if not rate.empty:
        rc = [c for c in rate.columns if "rate" in c.lower()]
        ratecol = rc[0] if rc else None
        for _, r in rate.iterrows():
            iso = r.get("source_iso3", r.get("iso3", ""))
            if str(iso) == "DEFAULT" or len(str(iso)) != 3:
                continue
            note = r.get("source_note", "")
            if ratecol:
                note = f"effective profit-tax rate = {r[ratecol]}. {note}"
            rows.append(dict(category="Resource profit-tax rate",
                             country=_name(iso), iso3=iso,
                             commodity_or_variable=r.get("commodity", ""),
                             confidence=r.get("confidence", ""), source=note))

    # C. Manual macro / CIT / wage values (per jurisdiction × variable)
    mac = _read("data/raw/macro_variables/manual_imputation_values.csv")
    if not mac.empty:
        gm = (mac.groupby(["iso_partner", "variable"], as_index=False)
                 .agg(source_url=("source_url", _first), note=("note", _first)))
        for _, r in gm.iterrows():
            src = " ".join(str(x) for x in [r["note"], r["source_url"]] if str(x) not in ("", "nan"))
            rows.append(dict(category="Macro / CIT / wage (small territories)",
                             country=_name(r["iso_partner"]), iso3=r["iso_partner"],
                             commodity_or_variable=r["variable"],
                             confidence="", source=src))

    out = pd.DataFrame(rows, columns=["category", "country", "iso3",
                                      "commodity_or_variable", "confidence", "source"])
    out = out.sort_values(["category", "country", "commodity_or_variable"])

    csv = os.path.join(tables_dir, "appendixF_handcollected_sources.csv")
    out.to_csv(csv, index=False)
    # markdown
    md = os.path.join(tables_dir, "appendixF_handcollected_sources.md")
    with open(md, "w", encoding="utf-8") as fh:
        cols = list(out.columns)
        fh.write("| " + " | ".join(cols) + " |\n")
        fh.write("| " + " | ".join("---" for _ in cols) + " |\n")
        for _, r in out.iterrows():
            cells = [str(r[c]).replace("\n", " ").replace("|", "/") for c in cols]
            fh.write("| " + " | ".join(cells) + " |\n")

    print(f"wrote {csv}  ({len(out)} rows)")
    print("by category:")
    print(out.groupby("category")["iso3"].nunique().to_string())


if __name__ == "__main__":
    main()
