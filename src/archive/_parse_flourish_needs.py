import re, json

html = open('../data/raw/context/climate_finance/_flourish_map_embed.html',
            encoding='utf-8', errors='replace').read()
print('bytes', len(html))


def grab(varname, idx=0):
    """Balanced-bracket capture of the idx-th `varname = {...}`/`[...]` blob."""
    matches = list(re.finditer(re.escape(varname) + r'\s*=\s*', html))
    m = matches[idx]
    s = m.end()
    opench = html[s]
    closech = {'{': '}', '[': ']'}[opench]
    depth = 0
    i = s
    instr = False
    esc = False
    while i < len(html):
        c = html[i]
        if instr:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                instr = False
        else:
            if c == '"':
                instr = True
            elif c == opench:
                depth += 1
            elif c == closech:
                depth -= 1
                if depth == 0:
                    break
        i += 1
    return json.loads(html[s:i + 1])


# Column-name bindings (tells us what each metadata slot means)
try:
    cn = grab('_Flourish_data_column_names')
    print('COLUMN NAMES:')
    print(json.dumps(cn, indent=1)[:2000])
except Exception as e:
    print('no column names:', e)

data = grab('_Flourish_data')
print('top type', type(data).__name__)
if isinstance(data, dict):
    for k, v in data.items():
        n = len(v) if hasattr(v, '__len__') else ''
        print('KEY', repr(k), '->', type(v).__name__, n)
        if isinstance(v, list) and v:
            print('   sample[0]:', json.dumps(v[0])[:300])

json.dump(data, open('../data/raw/context/climate_finance/_flourish_map_data.json', 'w',
                     encoding='utf-8'))
print('saved json')

import pandas as pd
cols = ["Country", "Region", "Total 2021", "Total 2022", "Needs",
        "Annual average", "Pct need met", "ID", "Missing data"]
rows = [r["metadata"] for r in data["regions"]]
df = pd.DataFrame(rows, columns=cols)
for c in ["Total 2021", "Total 2022", "Needs", "Annual average", "Pct need met"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")
df = df[df["Needs"].notna() | df["Annual average"].notna()].copy()
df.to_csv('../data/raw/context/climate_finance/cpi_africa_needs_map.csv', index=False)
pd.options.display.float_format = '{:,.2f}'.format
print('\nrows with data:', len(df))
print(df[["Country", "Total 2021", "Total 2022", "Needs", "Annual average",
          "Pct need met"]].head(20).to_string(index=False))

# Diagnose whether Needs is annual or cumulative:
sub = df.dropna(subset=["Needs", "Annual average", "Pct need met"])
sub = sub[(sub["Needs"] > 0) & (sub["Pct need met"] > 0)]
sub = sub.assign(
    implied_annual=lambda x: x["Annual average"] / (x["Pct need met"] / 100),
    ratio_need_to_implied=lambda x: x["Needs"] / (x["Annual average"] / (x["Pct need met"] / 100)),
)
print('\nDiagnosis: Needs / (AnnualAvg / PctNeedMet) ~ #years if Needs is cumulative:')
print(sub[["Country", "Needs", "Annual average", "Pct need met",
           "implied_annual", "ratio_need_to_implied"]].head(15).to_string(index=False))
print('\nmedian ratio (≈ years in needs horizon):', round(sub["ratio_need_to_implied"].median(), 3))
