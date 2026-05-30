# PRG→BKK Air-Freight Rate Research — 2026-05-30

Lane researched: **Prague (PRG) → Bangkok (BKK)**, general air cargo, 100–1,000 kg chargeable, occasional / non-contracted (spot) freight. For Thai landed-cost pipeline (4soft wooden play equipment).

## FX snapshot
- **USD/THB: 32.5506** — source: https://www.xe.com/currencyconverter/convert/?Amount=1&From=USD&To=THB (mid-market, 2026-05-29 19:42 UTC)
- **EUR/THB: 37.9794** — source: https://www.xe.com/currencyconverter/convert/?Amount=1&From=EUR&To=THB (mid-market, 2026-05-29 19:42 UTC)

## Rates gathered

PRG has limited dedicated freighter capacity vs Frankfurt (FRA) / Vienna (VIE), so most forwarders truck PRG cargo to FRA or VIE for long-haul. FRA→BKK and Europe→SEA backhaul lanes are the cleanest public proxies. Asia→Europe (headhaul) figures are noted but **excluded** from the recommendation because the headhaul/backhaul spread on this corridor is large (headhaul is currently ~1.5–2× backhaul).

| # | Source | Lane | Rate native | Rate THB/kg | Transit days | Notes | URL | Fetched |
|---|--------|------|-------------|-------------|--------------|-------|-----|---------|
| 1 | Xeneta (via Air Cargo News) | Europe origin → global (avg) | USD 2.87/kg all-in spot | **93 THB/kg** | N/A (index) | Europe-outbound average, Apr 2026, +32% YoY. Best macro anchor for backhaul to Asia. | https://www.aircargonews.net/data/2026/05/xeneta-the-worst-may-be-over-after-air-cargo-prices-surge-in-april/ | 2026-05-30 |
| 2 | WorldACD weekly trends (wk 18 2026) | Global avg | USD 3.29/kg yield | **107 THB/kg** | N/A (index) | Global all-lane average, early May 2026; PRG→BKK typically sits at or slightly below this. | https://www.worldacd.com/trend-reports/weekly/worldacd-weekly-air-cargo-trends-2026-week-18/ | 2026-05-30 |
| 3 | WorldACD (Apr 2026 monthly) | Global avg | USD 3.17/kg yield | **103 THB/kg** | N/A (index) | April 2026 global average — highest level of the year. | https://www.aircargonews.net/data/2026/05/xeneta-the-worst-may-be-over-after-air-cargo-prices-surge-in-april/ | 2026-05-30 |
| 4 | FreightAmigo 2026 rate guide | FRA → HKG (proxy) | EUR 2.00–5.00/kg base + 20–35% FSC | **76–190 THB/kg** (mid ~133) | 1–3 | Frankfurt→Hong Kong is a published proxy for FRA→SEA backhaul; BKK typically 5–15% cheaper than HKG ex-FRA. Range is wide — covers shoulder vs peak. | https://www.freightamigo.com/en/blog/logistics/air-freight-costs-in-2026-prices-rates-per-kg-and-key-insights/ | 2026-05-30 |
| 5 | Airfreightprice.com / forwarder quote desk | TH → EU (reverse proxy) | USD 2.80/kg all-in | **91 THB/kg** | 3–5 | Q2 2026 standard rate — return-direction proxy. Europe→TH backhaul typically sits within ±15%. | https://airfreightprice.com/shipping/thailand-to-europe-air-freight-rates/ | 2026-05-30 |
| 6 | Suaid Global 2026 rate guide | Europe → USA (proxy) | USD 2.50–4.50/kg standard | **81–146 THB/kg** | 1–3 | Long-haul transatlantic ex-EU baseline. PRG→BKK is longer but on a less-contested lane; useful sanity floor. | https://suaidglobal.com/insights/air-freight-cost-per-kg/ | 2026-05-30 |
| 7 | FreightAmigo intra-Asia | Intra-Asia | USD 2.00–3.50/kg standard | **65–114 THB/kg** | 1–2 | Floor reference only — shorter haul, excluded from PRG→BKK median. | https://www.freightamigo.com/en/blog/logistics/air-freight-costs-in-2026-prices-rates-per-kg-and-key-insights/ | 2026-05-30 |
| 8 | Freightos Air Index (FAX) — *excluded direction* | SEA → EU (headhaul) | USD 5.30–5.40/kg | (176 THB/kg) | 1–3 | **Excluded from recommendation** — wrong direction. SEA→EU headhaul is currently elevated by Red Sea / Middle East routing; PRG→BKK as the backhaul is materially cheaper. | https://www.freightos.com/freight-industry-updates/weekly-freight-updates/ | 2026-05-30 |

### Surcharge composition (Europe → Asia, 2026)
- Fuel surcharge (FSC): **USD 0.41–1.65/kg** or ~20–35% of base rate (FreightAmigo, Apr 2026)
- Security surcharge (SSC): EUR 0.10–0.22/kg
- War-risk surcharge: EUR 0.20–0.50/kg (currently active on Europe→Asia due to Middle East routing)
- Origin handling minimum: EUR 20–38 per AWB
- Combined surcharges typically add **30–60%** on top of base; rates listed as "all-in" already include them.

## Recommendation

Pick from the backhaul-relevant rows only (rows 1, 2, 3, 4, 5, 6) — i.e. exclude row 7 (intra-Asia, too short) and row 8 (wrong direction, headhaul). Convert all to THB/kg, sort, and pick percentiles.

THB/kg points used (rows 1–6 midpoints): **93, 107, 103, 133, 91, 114** → sorted: 91, 93, 103, 107, 114, 133.

- **Low (P10 / conservative shipper quote)**: **~90 THB/kg** (USD 2.80, ~EUR 2.40) — matches Thailand→Europe published spot and Xeneta Europe-origin average. Defensible as best-case all-in for a well-prepared 500–1,000 kg consolidation via FRA hub.
- **Median (recommended baseline for landed-cost)**: **~105 THB/kg** (USD 3.20, ~EUR 2.80) — clusters tightly around WorldACD's April global avg ($3.17) and week-18 avg ($3.29). This is the rate to use in the pipeline.
- **High (P90 / contingency / small-shipment surcharge)**: **~135 THB/kg** (USD 4.15, ~EUR 3.55) — covers FreightAmigo FRA→HKG midpoint and a PRG-to-FRA trucking premium of ~10–15%. Use this for sub-300 kg shipments, peak-season (Sep–Nov), or any war-risk re-rating.
- **Volumetric divisor (general cargo, IATA)**: **167 kg/m³** (= 6,000 cm³/kg). Chargeable weight = max(gross kg, volume_m³ × 167).
- **Surcharges note**: The chosen 90 / 105 / 135 THB/kg are **all-in** (base + FSC + SSC + war-risk + origin handling). Do **not** add FSC% on top. If a forwarder quotes a *base* rate only, expect to add ~30–50% for FSC+SSC+war-risk to get to these all-in numbers.

## Methodology notes
- No public source publishes a PRG→BKK spot rate; PRG lacks scheduled main-deck freighter capacity and is almost always trucked to FRA (or occasionally VIE) for long-haul. Therefore the analysis uses **Europe-outbound averages** (Xeneta, WorldACD) and **FRA→HKG / TH→EU** as the closest published proxies, with a small PRG-trucking premium baked into the High bucket.
- **Excluded as outliers**: (a) DHL Express courier-style 400+ THB/kg quotes (out of scope — express, not general cargo); (b) SEA→EU headhaul $5.30–5.40/kg (wrong direction; current Red Sea premium makes it a poor proxy for the lighter-loaded backhaul); (c) intra-Asia $2.00–3.50/kg (too short a haul).
- **FX conversion** uses xe.com mid-market USD/THB and EUR/THB snapshots taken 2026-05-29 19:42 UTC. Real forwarder invoices will use bank TT rates ~0.3–0.6% worse than mid-market; the rounding above absorbs this.
- **Coverage caveat**: Only 6 backhaul-relevant data points (1 lane index, 2 global indices, 3 forwarder rate guides). No direct PRG→BKK quote was obtainable without a logged-in WebCargo / myDHLi account. Recommendation is defensible as a planning rate but should be re-validated with a real RFQ before contracting >2,000 kg/month.
- **Refresh cadence**: Re-run this research monthly while Middle East routing premiums persist; quarterly otherwise.
