"""Tax Justice Network brand styling for matplotlib figures.

Applies the TJN brand guide + fonts guide (2020):
  * Typeface: **Work Sans** (the publication sans — headings/titles/body).
    Montserrat Black is reserved for slogans and Catamaran Black for the logo,
    so neither is used in charts.
  * Colour palette: the brand primary + support colours.

The Work Sans static TTFs ship in `assets/fonts/` (SIL OFL) and are registered
with matplotlib here, so the brand font renders even though it is not installed
system-wide. Call `apply_tjn_style()` once at import in any figure script:

    from _brand import apply_tjn_style, PALETTE, POSITIVE, NEGATIVE, ORIGIN_DEST_NEXUS
    apply_tjn_style()
"""
from pathlib import Path

import matplotlib as mpl
import matplotlib.font_manager as fm

_ROOT = Path(__file__).resolve().parent.parent
_FONT_DIR = _ROOT / "assets" / "fonts"

# ── Brand colours (TJN brand guide 2020) ─────────────────────────────────────
GOLD = "#FFD371"          # primary
EARTH_GREEN = "#50805E"   # primary
WHITE = "#FFFFFF"         # primary
RED = "#AD756C"           # support
TEAL = "#45636C"          # support
BROWN = "#AE8D6C"         # support
BLUE = "#586AAD"          # support
INK = "#1A1A1A"           # near-black for text / axes (brand text is black)

# General categorical cycle (primary first, then supports). Earth green leads
# because it is the dominant brand colour.
PALETTE = [EARTH_GREEN, BLUE, GOLD, RED, TEAL, BROWN]

# Semantic helpers, used consistently across the deliverables:
POSITIVE = EARTH_GREEN          # winners / gains
NEGATIVE = RED                  # losers / losses
ORIGIN_DEST_NEXUS = [BLUE, GOLD, EARTH_GREEN]   # origin / destination / dest+nexus

# Colour-blind redundancy: a hatch (texture) per categorical series, applied ON TOP
# of the brand colour so grouped bars stay distinguishable for viewers who cannot
# separate the hues (and in greyscale / print). First series is solid; the rest carry
# a distinct texture. '///' is reserved for the minimum-royalty floor add-on, so it is
# NOT in this cycle. Use `HATCH_CYCLE[i % len(HATCH_CYCLE)]`.
HATCH_CYCLE = ["", "\\\\", "..", "xx", "++", "oo"]


def tint(hex_color: str, frac: float = 0.2) -> str:
    """20%-style tint of a brand colour over white (brand tinted backgrounds)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    mix = lambda c: round(c * frac + 255 * (1 - frac))
    return f"#{mix(r):02X}{mix(g):02X}{mix(b):02X}"


def shade(hex_color: str, frac: float = 0.35) -> str:
    """Darken a brand colour toward black by `frac` (deep ramp endpoints)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    mix = lambda c: round(c * (1 - frac))
    return f"#{mix(r):02X}{mix(g):02X}{mix(b):02X}"


# Diverging anchors for signed heatmaps: losses on the brand-RED pole, gains on
# the brand-BLUE pole (NOT earth green — red–green diverging is the classic
# deuteranopia failure pair), with a neutral warm gray at the midpoint (never a
# hue). Endpoints are darkened brand anchors so the ramp has enough range.
DIVERGING_ANCHORS = [shade(RED), RED, "#F1EFEA", BLUE, shade(BLUE)]
# Green/red gain–loss variant (matches the POSITIVE/NEGATIVE semantics). The two
# hues are NOT separable under deuteranopia on their own — use only where every
# cell also carries a signed annotation (+/−), so the sign, not the hue, is the
# polarity carrier.
DIVERGING_GAIN_LOSS = [shade(RED), RED, "#F1EFEA", EARTH_GREEN, shade(EARTH_GREEN)]


def _install_pdf_sidecar():
    """Make every figure ALSO save a vector PDF next to its PNG, for Overleaf.

    Patches Figure.savefig (which plt.savefig routes through) so a save to
    `<name>.png` transparently writes `<name>.pdf` too — no figure script needs
    to change. Idempotent; skips non-path targets (buffers) and never recurses
    (calls the captured original)."""
    from matplotlib.figure import Figure
    if getattr(Figure, "_tjn_pdf_patched", False):
        return
    _orig = Figure.savefig

    def savefig(self, fname, *args, **kwargs):
        result = _orig(self, fname, *args, **kwargs)
        try:
            p = Path(fname)
        except TypeError:
            return result                      # file-like / buffer target
        if p.suffix.lower() == ".png":
            try:
                _orig(self, str(p.with_suffix(".pdf")), *args, **kwargs)
            except Exception:
                pass                            # never let the PDF break the PNG
        return result

    Figure.savefig = savefig
    Figure._tjn_pdf_patched = True


_applied = False


def apply_tjn_style():
    """Register Work Sans and set brand rcParams. Idempotent."""
    global _applied
    if _applied:
        return
    _install_pdf_sidecar()
    for f in sorted(_FONT_DIR.glob("WorkSans-*.ttf")):
        try:
            fm.fontManager.addfont(str(f))
        except Exception:
            pass
    mpl.rcParams.update({
        "font.family": "Work Sans",
        "font.sans-serif": ["Work Sans", "DejaVu Sans", "Arial"],
        "axes.prop_cycle": mpl.cycler(color=PALETTE),
        # near-black ink for text + axes
        "text.color": INK, "axes.labelcolor": INK, "axes.titlecolor": INK,
        "axes.edgecolor": INK, "xtick.color": INK, "ytick.color": INK,
        "axes.titleweight": "bold",
        # clean spines + light horizontal grid
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y",
        "grid.color": "#E8E8E8", "grid.linewidth": 0.8, "axes.axisbelow": True,
        # white backgrounds (brand primary background)
        "figure.facecolor": "white", "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "legend.frameon": True, "legend.framealpha": 0.9,
        "legend.edgecolor": "#DDDDDD",
        "font.size": 11, "figure.dpi": 130, "savefig.dpi": 130,
    })
    _applied = True
