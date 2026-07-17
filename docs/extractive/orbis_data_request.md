# Orbis data request — CbCR-scope company universe

Request to a colleague who holds the Orbis flatfiles in a SQL database. Goal: a
single entity-level table covering **all companies in scope of country-by-country
reporting (CbCR)** — i.e. all members of every multinational group above the
€750M threshold, across **all sectors** (not just extractives). Field names below
match the Orbis flatfile / "Global format" column labels, so they should line up
with the SQL columns.

## 1. Population / filter (what "in scope" means)

- **Window:** fiscal years **2016–2022** (please extend to the latest available — 2023/2024 — if cheap; we'll subset).
- **Group threshold (the €750M):** a group is in scope if its **Global Ultimate Owner (GUO at >50%, the Orbis `GUO 50`)** has **consolidated** `Operating revenue (Turnover)` **≥ €750 million** in **at least one** year of the window.
  - Use the GUO's **consolidated** account (`Consolidation code` = **C1** or **C2**). If the GUO has no consolidated account, fall back to the **maximum single-entity** operating revenue within the group as the proxy.
  - Threshold currency is **EUR €750M** (the legal CbCR threshold). If you work in USD, ≈ **$750M** is fine (we treat €750M ≈ $750M), or convert at each year's average EUR/USD rate.
- **Return rows for:** **every entity whose `GUO 50` is an in-scope GUO, plus the GUO entities themselves** — i.e. the full group membership, regardless of each subsidiary's own size.

## 2. Variables to return (one row per entity)

**Identification**
- `BvD ID number`  *(key)*
- `Name`
- `Country ISO code`  *(the entity's own country = "market" country for nexus)*
- `Entity type`

**Industry classification**
- `NACE Rev. 2, core code (4 digits)`
- `NACE Rev. 2, primary code(s)`
- `NACE Rev. 2, secondary code(s)`

**Group structure**
- `Number of subsidiaries`

**Ownership (the GUO @50%)**
- `GUO 50` — BvD ID of the ultimate owner  *(= HQ entity)*
- `GUO 50 - Name`
- `GUO 50 - Type`  *(listed / state-owned / private — we derive ownership class from this)*
- `GUO 50 - Country ISO code`  *(the entity's **HQ country** for HQ-shares & nexus)*

**Financials — per year 2016–2022** (this is the key block)
- `Operating revenue (Turnover)` — in **thousand USD** (or thousand EUR; tell us which), one value **per year**
- `Number of employees` — per year *(optional but useful)*
- `Consolidation code` and `Closing date` per statement *(so we can pick the right account / map to a calendar year)*

*(Not currently needed, include only if trivial: `P/L before tax`, `Total assets`, `Shareholders funds`.)*

## 3. Output format

- One row per **entity** (BvD ID). Per-year financials either **wide** (`Operating revenue (Turnover) <year>` columns 2016…2022) — which matches how the repo reads them today — **or long** (entity × year rows); we can pivot either way.
- Tab- or pipe-delimited, UTF-8, with a header row.
- If easy, a second small table mapping `GUO 50 → consolidated operating revenue per year` (the figure used for the threshold) so we can audit which groups qualified.

## 4. Notes

- We already have a **2022/2023-vintage** local flatfile copy (`D:\data\Orbis_raw`, June folders) and will build the universe from it for the 2016–2022 analysis. **This request is the refresh** — its value is (a) complete/recent FY2022, (b) 2023+ years, and (c) full all-sector coverage rather than our current extractive-only pull.
- The same table serves several uses in the repo: the **HQ-share** weighting (`3_2`), the **CbCR entity universe / €750M flag** (`1_7a`), the **HQ↔market nexus** for destination-based sales (`1e`, which needs `Country ISO code` + `GUO 50 - Country ISO code` per entity), and **firm counts by HQ country**.
