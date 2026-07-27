# Destination-based sales measures

Built by `src/1b_destination_based_sales.py` → `data/intermediate/destination_based_sales.csv`
(+ optional `destination_based_sales_bilateral.csv`), merged in script 2, consumed by the
`DEST_MEASURES` formula variants in script 5.

## Measure family

| Key column | Formula tag | Construction |
|---|---|---|
| `cfb_share` | `destcfb` | AAMNE MNE turnover − exports, **17 consumer-facing ISIC sections** (OECD 2020 ch.2) |
| `cfb_plus_digital_share` | `destcombined` | CFB + WTO digitally-delivered-services imports |
| `cfb_plus_digital_plus_ads_share` | `destcombinedads` | + ad-funded ADS slice (×0.20) |
| `ads_share` | `destads` | ITU internet penetration × household consumption (OECD ADS proxy) |
| `mne_share` | `destmne` | **Broadened (2026-07-12)**: AAMNE MNE turnover − exports, **all 41 ISIC sections incl. finance** |
| `mne_plus_dds_share` | **`destmnedds` (HEADLINE)** | + the **MNE share** of digitally-**deliverable**-services imports **EXCLUDING SH / charges for IP** (BaTIS; WTO fallback). MNE share = AAMNE (F + D_MNE) fraction of EXGR in the deliverable-producing ISIC sectors, per year ≈ 53–58%, last AAMNE year rolled forward. Ex-IP promoted from sensitivity to HEADLINE 2026-07-12 (SH ≈ 15% of the aggregate, largely intra-group royalties). NB: the ex-IP aggregate is above the WTO digitally-delivered series 2016–2019 but slightly below it 2020–2022 (the full Handbook aggregate is above in every year) |
| `mne_plus_dds_inclip_share` | `destmneddsinclip` | **IP-inclusive sensitivity**: the full Handbook aggregate (SH kept), same MNE-share scaling |
| `mne_bilat_factor` | `destmnebilat` | **Bilateral**: market `mne_sales` × parent's AAMNE ownership fraction |

**Retired (2026-07-12): `destmneddsads`** — the third leg (0.20 × the ITU-internet ×
household-consumption ADS proxy) was removed from the broadened family. Every *paid*
automated digital service is already inside the BaTIS deliverable imports (ADS ⊂ the
Handbook categories), so a separate leg double-counted concept-wise; and the proxy's
consumption scale (~US$29–45tn) gave the leg ~14% of the global key when the true
ad-funded free slice is bounded by global digital-ad revenue (~US$0.6tn, <1%). The
ad-funded free slice (no trade counterpart) is therefore *excluded* rather than proxied.

Each market-level key also has a `_nexus` variant (share × Orbis coverage fraction);
the bilateral factor has none — ownership presence already encodes nexus.

## Decisions behind the broadened measure

- **All sectors incl. finance** (user, 2026-07-12): the destination key substitutes for the
  CbCR `unrelated_party_revenues` factor, which includes financial firms' revenues; in
  formulary-apportionment practice financial-services sales are sourced to the customer's
  location like any other sales. Caveat: AAMNE gross output for finance embeds FISIM-type
  measurement quirks. Globally the all-sector measure ≈ 2.4× the CFB measure.
- **Digitally DELIVERABLE, not "delivered"** (user / G24 paper): conceptual hierarchy
  ADS ⊂ "digitally delivered" (WTO series; definition unclear) ⊂ "digitally deliverable"
  (Handbook: deliverable using ICT). We build the *deliverable* aggregate transparently
  from raw BaTIS EBOPS categories (SF insurance & pension, SG financial, SH charges for
  IP, SI telecom/computer/information, SJ other business services, SK1/SK audiovisual‑
  personal-cultural), imports side. Expected **higher** than the WTO series — the 1b
  diagnostic prints both and flags any year where BaTIS < WTO (category-selection error).
  Reference: G24, "Options for a Protocol on Services under the UNFCITC",
  https://g24.org/wp-content/uploads/2026/04/Options-for-a-Protocol-on-Services-under-the-UNFCITC-1.pdf
- **MNE-share scaling of the DDS leg (2026-07-12)**: BaTIS imports are all-supplier
  trade flows, but the destination key replaces an **MNE** sales variable, so the leg is
  multiplied by the per-year AAMNE MNE share of exports in the deliverable-producing
  ISIC sectors (SF/SG → K64T66; SI → J58T60/J61/J62T63; SJ → M69T75/N77T82; SK1 →
  R90T93): 2016 57.8%, 2017 58.1%, 2018 55.6%, 2019 52.6%, 2020 56.3% (rolled forward
  to 2021–22). With the scaling, the DDS leg carries ~3.7–4.2% of the global key
  (previously ~7%). This is a global per-year scalar — a bilateral supplier-specific
  weighting is possible but not implemented.
- **ADS enters only via BaTIS** (user 2026-07-12): no separate ADS leg — see the
  retired-`destmneddsads` note above.
- **Ex-IP sensitivity (2026-07-12)**: BaTIS imports include intra-group services trade,
  while the CbCR slot being replaced is *unrelated-party* revenues. SH (charges for the
  use of IP) is the unambiguous case — 14.8% of the pooled 2016–22 aggregate and largely
  affiliate→parent royalty flows (category shares: SJ 45.7%, SI 17.7%, SH 14.8%, SG 14.0%,
  SF 6.0%, SK1 1.9%). `destmneddsexip` drops SH from the deliverable leg (same MNE-share
  scaling as the headline). Materiality is second-order: the scaled DDS leg carries only
  ~4% of the combined pool, so dropping SH moves the combined shares by well under 1%.
- **Bilateral variant**: weights each market's all-MNE destination sales by the parent
  country's ownership share of that market's MNE output (AAMNE bilateral host×owner GO);
  the host's own D_MNE output counts as host-owned; uncovered (parent, market) pairs fall
  back to the parent's global ownership share so every parent has a complete USD factor.
  Approximation: exports netted at host level (bilateral exports by owner are not
  published). The digital part stays market-level in all variants (BaTIS partners are
  supplying countries, not HQs).

## Data sources / downloads

| Input | File | Status |
|---|---|---|
| AAMNE MNE-split (F/D_MNE/D_OTH) | `data/raw/destination_based_sales/oecd_aamne_mne_xvem_2026-06.csv` | present |
| WTO digitally-delivered services | `data/raw/destination_based_sales/wto_dds_imports_2026-06.csv` | present (fallback for part 2) |
| **BaTIS** (EBOPS bilateral) | `data/raw/destination_based_sales/oecd_wto_batis_data_bpm6/…December2025_bulk.csv` | present (active) |
| **AAMNE bilateral output** (host × investing country) | `data/raw/destination_based_sales/oecd_aamne_bilateral_output_2026-07.csv` | present (active) |

Both gated blocks print loud fallback/skip messages until the files arrive; the loaders
(`_load_batis_dds_imports`, Part D) are column-tolerant and raise with the found columns
if a layout isn't recognised — extend the mapping there when the real files land.

## Methodology note: `GO`, imports, the sales hub, and the resource sector (2026-07-18)

Conceptual note (discussion, not yet implemented) on making the origin/destination
split "more focused", and the data constraints that bound what is feasible.

### What `GO` is, and why the current key excludes imports
`GO` is **gross output** in the OECD **ICIO** sense (Cadestin et al. 2018), ownership-split
(F / D_MNE / D_OTH): the full production value (`GO = GVA + intermediate consumption`) of
firms **located in the host country**, by ISIC industry, current-price million USD. It is
measured **where production happens** — an imported good's value sits in the *exporter's*
`GO`, never the importer's (trade-sector output is on a *margins* basis, so the importing
country picks up only the distribution margin on an import).

Consequently the AAMNE leg `mne_sales = GO − EXGR` (`1b:355`) is **domestic production
minus exports = domestic production absorbed at home**. It contains **no imports**. For
goods it is therefore a *domestic-market-activity* proxy, **not** a *final-consumption*
measure. Imports enter the headline key only through (a) the separate **BaTIS leg**
(digitally-deliverable **services** imports) and (b) the thin local distribution margin on
imported goods.

**The data actually carries imports.** `destination/oecd_aamne_mne_xvem_2026-06.csv` has columns
`GO, GVA, EXGR, IMGR` — the gross-imports variable `IMGR` is present but **unused**. So a
true apparent-consumption/absorption measure `GO − EXGR + IMGR` is constructible from the
same file (77 AAMNE economies). The current omission is a construction choice inherited from
the OECD CFB "turnover − exports" proxy, not a data limitation. Caveats before using it:
`IMGR` over all sectors already includes **services** imports, so adding it would
**double-count the BaTIS leg** (they are alternative ways to bring imports in); and it is
still 77-economy coverage (imputed countries have no `IMGR`).

### The sales-hub / origin problem, and why related-party sales are not the fix
On the **origin** side we use the CbCR `unrelated_party_revenues` slot. Two problems:
1. **No sector detail** in CbCR — resources cannot be isolated on the origin side at all.
2. **Sales-hub distortion.** If coffee grown in Brazil is distributed via a Swiss hub to
   German customers, the third-party sale is booked in **Switzerland** — neither producer
   nor consumer.

The tempting fix ("use *related-party* sales in the hub case, since they trace Brazil→
Switzerland") is rejected: (i) we cannot identify which cells are hub re-exports (no sector,
no counterparty detail); (ii) related-party sales are **booked intra-group transfers** — the
single most transfer-price-manipulable number in the data. Using them as an apportionment
factor would re-import into the formula exactly the manipulation unitary taxation exists to
remove. The hub problem is instead handled **structurally**: destination reallocation makes
booking hubs wash out (Switzerland produces/consumes ~no coffee, so it carries ~no weight in
a real-economy key), and the **employees factor** (half the headline formula) independently
down-weights hubs (they employ almost nobody).

### Where the coffee lands under each measure
| Measure | Credited to | Verdict |
|---|---|---|
| Origin (CbCR unrelated-party) | Switzerland (hub) | booking artifact |
| Destination (`GO − EXGR`) | ~nobody — exported from Brazil, and Germany only books the distribution margin | loses the value |
| Destination + imports (`GO − EXGR + IMGR`) | Germany (consumer) | right for market sectors |
| Destination, resources kept at origin (`GO`) | Brazil (producer) | right for resources |

### Suggested refinement (data-feasible)
Keep destination-based sales as the headline, but **treat the natural-resource sectors as
origin within it** — i.e. do **not** deduct exports (use `GO`, not `GO − EXGR`) for **mining
`B05T09` + agriculture `A01T03`**. Rationale: (a) AAMNE has the sector detail to do it
cleanly; (b) `GO` is already a production concept located at the producer, so declining to
subtract resource exports is *consistent* with the measure rather than a hack; (c) it needs
no manipulable booked number. On the CbCR/origin side make **no** change — document that
origin sales are hub-distorted and sector-blind, and that destination reallocation plus the
employees factor are what neutralise the hub problem.

**Limitations to state alongside it:**
- The `GO` tweak reaches only the **77 AAMNE economies** (lifts NGA/CHL/KAZ/COL, not the
  imputed LICs NER/MWI/BFA…). The AAMNE leg is imputed for non-AAMNE countries as a macro
  ratio (`log(mne_sales/GDP) ~ log GDP + log GDP p.c. + log trade`, `1b:409`) with **no
  sector information**, so there is nothing resource-specific to adjust there. Reaching the
  LICs needs a separate origin term from data that covers them (WB natural-resource rents,
  the extractive panel, or Comtrade mining+ag exports) — a second, larger step.
- It refines the **destination** measure only; the origin measure stays as the
  hub-distorted, sector-blind CbCR series used as the contrast case.
- For goods generally, "destination" here is domestic-market-activity, not final
  consumption — a limitation wider than resources (it undercounts every heavily-traded
  manufacture at the point of consumption). The `+ IMGR` option above is the fuller fix.

### What the OECD (2020) actually argues — and why it tempers the above
OECD (2020), *Tax Challenges Arising from Digitalisation – Economic Impact Assessment*,
ch. 2, paras 91–99 (`docs/OECD_2020_destinationbasedsales.pdf`) is explicit about *what to
include and why*:
- **Para 92** defines the proxy: `turnover of MNE entities in J − exports of MNE entities
  from J`.
- **Para 93** gives the reason it is NOT a consumption measure: it is "a better proxy…
  than… more aggregated measures that **do not distinguish MNE and non-MNE sales** (e.g.
  household consumption in national accounts)." So imports are omitted **deliberately** —
  the only data that isolates MNEs (AAMNE, by ownership) gives turnover and exports, not
  final consumption. **This corrects the `+ IMGR` idea above:** `IMGR` is the importing
  MNE's *own input imports*, not *imported final sales into J* — and para 93 states remote/
  imported final sales "are not included either at their point of destination" because the
  data cannot locate them. `+ IMGR` would add a different quantity, not reconstruct
  consumption.
- Para 93 also stresses the measure targets **shares, not levels** ("the aim… is to measure
  the share of each jurisdiction in global destination-based sales"), so roughly-proportional
  omissions wash out — the whole approach is defended on that basis.

**Consequence for the resource-origin suggestion — but read with the all-sector caveat
below.** Under the destination principle as OECD defines it, a resource exporter's destination
sales genuinely *are* ≈0 (it exports; it does not sell to local final consumers), so on OECD's
own terms the key is working as intended.

**BUT we already left OECD's frame.** OECD's CFB key covers only **consumer-facing** sectors —
its `cfb_sectors` list (Table 2.2 Panel B) **excludes** mining `B05T09` and agriculture
`A01T03`. Our headline `mne_share` deliberately uses **all 41 sectors** (B2B, finance, primary
included) for scope-consistency with the all-sector CbCR `unrelated_party_revenues` slot it
replaces. So resources are in our key **only because of that broadening**, and "the destination
principle says exporters correctly get ≈0" invokes a principle we already stretched past its
domain for exactly these sectors (crude oil sold to a refinery has no "final consumer market").
Resource-origin is therefore **not** a betrayal of a clean principle — it is another pragmatic,
sector-specific choice inside an already-pragmatic all-sector construction. The import-omission
logic (para 93) is unaffected by this, as it is a method argument, not a sector one (and is
*more* binding for B2B, which has no household-consumption analog at all).

**So the decision rests on practicalities, not OECD fidelity:**
1. **Carve-out overlap** — resources are already protected at source by `excl_resource`;
   resource-origin on the sales key does it a second time. Main reason for caution; argues for
   *never* combining the two.
2. **AAMNE coverage** — reaches NGA/CHL/KAZ/COL, not the imputed LICs.
3. **Scope-symmetry** — going all-sector was to keep destination a like-for-like replacement of
   the all-sector, hub-distorted CbCR origin key (which can't be sector-split); treating
   resources specially in destination alone reintroduces an origin/destination scope mismatch.

**Revised recommendation:** the destination sales factor is defensible as-is; the resource/
source claim is most cleanly carried by the `excl_resource` carve-out. A resource-origin sales
variant is a **legitimate pragmatic option** (not a principle violation) — best run as a
**sensitivity on the baseline (resource-included) dataset**, where there is no carve-out to
double up with, and reported as "resources credited at source in the sales factor." Never
combine it with `excl_resource`.

**Status:** conceptual / proposed. Not implemented — no code, key columns, or `DEST_MEASURES`
entries added yet.
