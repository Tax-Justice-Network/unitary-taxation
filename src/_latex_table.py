r"""
Brand-coloured LaTeX (Overleaf) export for the paper tables.

Mirrors the Word table layout built by
`_build_paper_docx.add_table_from_csv_after` — a coloured bold header row, bold
shaded group-heading rows (uppercase first cell), right-aligned numeric cells,
one-decimal number formatting — but in TJN brand colours instead of Word greys:

  * header row  → earth-green fill, white bold text
  * group rows  → light-gold tint, bold
  * body        → white, right-aligned numbers (first column left)

Each `.tex` is a self-contained `table` float: it defines its own brand colours
with `\definecolor`, wraps the tabular in `\resizebox{\textwidth}` so wide
formula tables never overflow, and carries a `\caption`/`\label`. The only
Overleaf preamble requirement is:

    \usepackage[table]{xcolor}   % loads colortbl
    \usepackage{booktabs}
    \usepackage{graphicx}        % \resizebox

Drop into the document with `\input{tables/<name>.tex}`.

`csv_to_latex(csv_path, …)` writes `<csv_dir>/latex/<name>.tex` and returns the
path. Called from `_exhibit_helpers.write_table` (every income-group/region
table) and from `_build_paper_docx.add_table_from_csv_after` (every table that
goes into the Word documents), so all tables get an Overleaf twin.
"""
import os
import re

import pandas as pd

# TJN brand (hex without '#', for \definecolor). Header = earth green; group
# rows = a light gold tint over white (≈ _brand.tint(GOLD, 0.30)).
_C_HEADER = "50805E"      # earth green
_C_HEADER_TXT = "FFFFFF"  # white
_C_GROUP = "FBEFCB"       # light gold tint
_C_RULE = "50805E"        # rules in the brand green


def _esc(s):
    """Escape LaTeX specials in cell text."""
    s = str(s)
    out = []
    for ch in s:
        out.append({
            "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
            "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
            "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
        }.get(ch, ch))
    return "".join(out)


def _fmt(v):
    """One-decimal number formatting matching the Word builder (0 → '0.0', never
    '-0.0'); pass through non-numbers as text."""
    if isinstance(v, float):
        if pd.isna(v):
            return ""
        if round(v, 1) == 0:
            return "0.0"
        return f"{v:,.1f}"
    return "" if v is None else str(v)


def _is_group_row(first_cell):
    s = str(first_cell).strip()
    return s != "" and s == s.upper() and any(c.isalpha() for c in s)


def _slug(name):
    return re.sub(r"[^A-Za-z0-9]+", "_", os.path.splitext(os.path.basename(name))[0]).strip("_")


def header_spec_for(columns):
    """Auto-derive a 2-row grouped (super/sub) header from the flat column names,
    shared by the Word and LaTeX builders. Returns [super_row, sub_row] where each
    row is a list of (text, span); text=None in the sub row merges vertically with
    the super cell above. Returns None when no grouping applies (flat header).

    Two patterns:
      • 'PREFIX — SUFFIX' columns  → super = PREFIX, subs = the SUFFIXes
        (scenarios: 'Resources ignored — Δ taxable profit'; break-even:
        'Break-even ETR — sales & employees (%)').
      • '<name>' immediately followed by '<name> (%…)'  → super = <name>,
        subs = ['US$ m', the %-descriptor]  (the by-formula tables).
    """
    cols = [str(c) for c in columns]
    n = len(cols)

    # ---- pattern B: 'PREFIX — SUFFIX' groups ----
    if sum(1 for c in cols if " — " in c) >= 2:
        super_row, sub_row, i = [], [], 0
        while i < n:
            c = cols[i]
            if " — " in c:
                prefix = c.split(" — ", 1)[0]
                subs = []
                j = i
                while j < n and " — " in cols[j] and cols[j].split(" — ", 1)[0] == prefix:
                    subs.append(cols[j].split(" — ", 1)[1])
                    j += 1
                # tidy: if every sub is a '… (%)' rate, lift the % into the super
                # heading and title-case the sub labels (break-even table).
                if subs and all(s.rstrip().endswith("(%)") for s in subs):
                    subs = [s.rsplit("(%)", 1)[0].strip() for s in subs]
                    subs = [(s[:1].upper() + s[1:]) if s and s[0].islower() else s
                            for s in subs]
                    prefix = prefix + " (%)"
                super_row.append((prefix, len(subs)))
                sub_row.extend((s, 1) for s in subs)
                i = j
            else:
                super_row.append((c, 1)); sub_row.append((None, 1)); i += 1
        return [super_row, sub_row]

    # ---- pattern A: '<name>' + '<name> (%…)' pairs ----
    def _is_pct_partner(a, b):
        return b == a + " (%)" or b.startswith(a + " (% ")
    if any(i + 1 < n and _is_pct_partner(cols[i], cols[i + 1]) for i in range(n)):
        super_row, sub_row, i = [], [], 0
        while i < n:
            c = cols[i]
            if i + 1 < n and _is_pct_partner(c, cols[i + 1]):
                pctlab = cols[i + 1][len(c):].strip().strip("()").strip()
                pctlab = pctlab.replace("of positive reported profits", "of positive profits")
                pctlab = pctlab if pctlab.startswith("%") else "%"
                super_row.append((c, 2))
                sub_row.append(("US$ m", 1)); sub_row.append((pctlab, 1))
                i += 2
            else:
                super_row.append((c, 1)); sub_row.append((None, 1)); i += 1
        return [super_row, sub_row]

    return None


def csv_to_latex(csv_path, tex_path=None, caption=None, label=None, title_super=None):
    """Write a brand-coloured, portrait, page-breaking **longtable** (no landscape).

    The table carries NO caption/label — the consuming document supplies them via
    `\\captionof{table}{…}\\label{…}` so notes can sit between the caption and the
    table. `title_super`, when given, adds a top-level heading spanning the grouped
    (e.g. per-formula) value columns, with the leading (Country) and trailing
    (reference) single columns getting their own full-height super-headers.
    tex_path defaults to `<csv_dir>/latex/<name>.tex`. Returns the written path
    (or None if the CSV is unreadable)."""
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"  [latex skip] {csv_path}: {e}")
        return None
    name = _slug(csv_path)
    if tex_path is None:
        tex_dir = os.path.join(os.path.dirname(csv_path), "latex")
        os.makedirs(tex_dir, exist_ok=True)
        tex_path = os.path.join(tex_dir, name + ".tex")
    caption = caption or name.replace("_", " ")
    label = label or ("tab:" + name)

    headers = [str(c) for c in df.columns]
    ncol = len(headers)
    colspec = "@{}p{2.4cm}" + "r" * (ncol - 1) + "@{}"   # portrait, page-breaking

    lines = []
    lines.append("% Auto-generated brand-coloured table — mirrors the Word layout.")
    lines.append("% Requires: \\usepackage[table]{xcolor}  \\usepackage{booktabs}  \\usepackage{graphicx}  \\usepackage{multirow}")
    lines.append(f"\\definecolor{{tjnHeader}}{{HTML}}{{{_C_HEADER}}}")
    lines.append(f"\\definecolor{{tjnHeaderText}}{{HTML}}{{{_C_HEADER_TXT}}}")
    lines.append(f"\\definecolor{{tjnGroup}}{{HTML}}{{{_C_GROUP}}}")
    lines.append(f"\\definecolor{{tjnRule}}{{HTML}}{{{_C_RULE}}}")
    def _fr(first):
        return "\\firstrowcolor{}\\firstrowfont{}" if first else "\\firstrowfont{}"
    def _wrap(t):
        # break a long spanning header onto two centred lines at the middle space
        # (threshold keeps the four formula names on one line now the table is widened;
        # only genuinely long group labels, e.g. the scenario headings, still wrap)
        if len(t) <= 22 or " " not in t:
            return _esc(t)
        spaces = [i for i, ch in enumerate(t) if ch == " "]
        b = min(spaces, key=lambda i: abs(i - len(t) // 2))
        return "\\makecell{%s\\\\%s}" % (_esc(t[:b]), _esc(t[b + 1:]))

    # ---- header rows in the SOTJ xltabular layout (\firstrowcolor/\firstrowfont, \hline) ----
    hdr = ["\\hline"]
    spec = header_spec_for(headers)
    if spec and title_super:
        # 3 bands: [title_super over the formula block, Country + reference alongside],
        # [formula names, each spanning its two value columns], [US$ m / %].
        super_row, sub_row = spec
        lead, groups, trail, seen = [], [], [], False
        for text, span in super_row:
            if span >= 2:
                groups.append((text, span)); seen = True
            elif not seen:
                lead.append(text)
            else:
                trail.append(text)
        gspan = sum(s for _, s in groups)
        # Vertically-spanning labels (Country + the trailing reference column)
        # are drawn with \multirow{-3} FROM THE LAST header row — the
        # colortbl-safe pattern: a top-anchored \multirow gets painted over by
        # the row colours of the following header rows and can appear to float
        # above the band on longtable continuation pages.
        row = [_fr(True)]
        row.append("\\multicolumn{%d}{c|}{\\firstrowfont{}%s}" % (gspan, _esc(title_super)))
        row += ["" for _ in trail]
        hdr.append(" & ".join(row) + " \\\\")
        hdr.append("\\cline{2-%d}" % (1 + gspan))
        row = [_fr(True)]
        for t, s in groups:
            row.append("\\multicolumn{%d}{c|}{\\firstrowfont{}%s}" % (s, _wrap(t)))
        row += ["" for _ in trail]
        hdr.append(" & ".join(row) + " \\\\")
        hdr.append("\\cline{2-%d}" % ncol)
        row = [_fr(True) + "\\multirow{-3}{*}{\\firstrowfont{}%s}"
               % (_esc(lead[0]) if lead else "")]
        for text, span in sub_row[len(lead):len(lead) + gspan]:
            row.append("\\firstrowfont{}" + ("" if text is None else _esc(text)))
        def _trail_cell(t):
            # ≤3 lines (middle-split label + unit): a taller makecell than the
            # three header rows overflows upward past the table edge.
            if " " in t:
                sp = [i for i, ch in enumerate(t) if ch == " "]
                b = min(sp, key=lambda i: abs(i - len(t) // 2))
                lab = _esc(t[:b]) + "\\\\" + _esc(t[b + 1:])
            else:
                lab = _esc(t)
            return ("\\multirow{-3}{*}{\\firstrowfont{}\\makecell{%s\\\\(US\\$ m)}}"
                    % lab)
        row += [_trail_cell(t) for t in trail]               # label + unit, bottom-anchored
        hdr.append(" & ".join(row) + " \\\\")
        hdr.append("\\hline")
    elif spec:
        super_row, sub_row = spec
        top, first = [], True
        for text, span in super_row:
            body = _esc(text) if text else ""
            if span > 1:
                top.append("\\multicolumn{%d}{c|}{\\firstrowfont{}%s}" % (span, _wrap(text)))
            else:
                top.append(_fr(first) + body)
            first = False
        hdr.append(" & ".join(top) + " \\\\")
        hdr.append("\\hline")
        subs, first = [], True
        for text, span in sub_row:
            subs.append(_fr(first) + ("" if text is None else _esc(text)))
            first = False
        hdr.append(" & ".join(subs) + " \\\\")
        hdr.append("\\hline")
    else:
        cells, first = [], True
        for h in headers:
            cells.append(_fr(first) + _esc(h))
            first = False
        hdr.append(" & ".join(cells) + " \\\\")
        hdr.append("\\hline")

    # ---- SOTJ xltabular: |L|Y…|, page-breaking; caption + notes supplied by caller.
    # Bleed 3.2cm into the left margin (matching the figures) so wide tables get room. ----
    if title_super and spec:                       # last column holds the long reference label
        colspec = "|L{2.4cm}|" + "Y|" * (ncol - 2) + "R{2.5cm}|"
    else:
        colspec = "|L{2.4cm}|" + "Y|" * (ncol - 1)
    lines.append("\\setlength{\\LTleft}{-3.2cm}\\setlength{\\LTright}{0pt}")
    lines.append("\\begin{xltabular}{\\dimexpr\\textwidth+3.2cm\\relax}{%s}" % colspec)
    lines.extend(hdr)
    lines.append("\\endfirsthead")
    lines.append("\\multicolumn{%d}{@{}l}{\\emph{\\footnotesize (continued)}}\\\\" % ncol)
    lines.extend(hdr)
    lines.append("\\endhead")
    lines.append("\\multicolumn{%d}{r@{}}{\\emph{\\footnotesize Continued on next page}}\\\\" % ncol)
    lines.append("\\endfoot")
    lines.append("\\endlastfoot")
    for _, row in df.iterrows():
        is_grp = _is_group_row(row.iloc[0])
        cells = []
        for v in row:
            txt = _esc(_fmt(v))
            # [1]/[2]/[3] flags → hyperlinks to the shared notes block
            # (regular weight/shape — not italic). The tie (~) keeps the flag
            # on the same line as its number instead of wrapping beneath it.
            txt = re.sub(r"\s*\[([123])\]",
                         r"~\\hyperref[tab:tablenotes]{[\1]}", txt)
            if is_grp and txt:
                txt = f"\\textbf{{{txt}}}"
            cells.append(txt)
        line = " & ".join(cells) + " \\\\"
        if is_grp:
            line = "\\rowcolor{tjnGroup} " + line
        lines.append(line)
    lines.append("\\hline")
    lines.append("\\end{xltabular}")
    lines.append("")
    with open(tex_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return tex_path
