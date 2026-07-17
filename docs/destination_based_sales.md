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
| AAMNE MNE-split (F/D_MNE/D_OTH) | `data/raw/AAMNE_MNE_XVEM.csv` | present |
| WTO digitally-delivered services | `data/raw/DDS_bulk_download.csv` | present (fallback for part 2) |
| **BaTIS** (EBOPS bilateral) | `data/raw/OECD-WTO_BATIS_data_BPM6-1/…December2025_bulk.csv` | present (active) |
| **AAMNE bilateral output** (host × investing country) | `data/raw/aamne-bilateral-output.csv` | present (active) |

Both gated blocks print loud fallback/skip messages until the files arrive; the loaders
(`_load_batis_dds_imports`, Part D) are column-tolerant and raise with the found columns
if a layout isn't recognised — extend the mapping there when the real files land.
