# Eurotramp — Held-back merge-candidate proposal

_Generated 2026-06-06 from the **EuroTramp 2023 Info-Package** local asset pack
(`Info-Package-KidsTramp-PlayPro_EN`, `Info-Package-Playground-Outdoor-Trampolines-2023`)
cross-referenced with the live Medusa snapshot (`eurotramp-live-snapshot-2026-06-06.json`)._

> **Proposal only — do NOT auto-merge.** These collapse a set of draft spare-part
> SKUs into variant-bearing parents. Each needs the Eurotramp price list to lock
> the variant axis before execution.

## Key insight the local pack revealed

The **`2023_01 A4_Flyer_Fallschutz_EN.pdf`** ("KidsTramp Impact Protection") states the
impact-protection range was re-issued in 2023 with a **"pure EPDM top layer"**, and that:

> *"For spare-parts orders the **old** impact-protection elements are still available.
> New orders of complete trampolines plus impact protection we will confirm with the
> **new article numbers** in the future."*

This explains the duplicated impact-protection SKUs in Medusa: every piece exists as an
**OLD (pre-2023)** article and a geometry-identical **NEW (2023, EPDM-top)** article. The
split is a **system version**, not a colour or a size. This reframes two of the three
candidate families below.

---

## 1. `single-tile-impact-protection` — **STRONG evidence → propose merge**

33 draft SKUs, all `Single tile impact protection Kids Tramp …`, resolve to **9
(model, piece) groups**, each appearing in both system versions:

| Group (model · piece) | OLD articles | NEW EPDM articles | geometry (W×L cm) |
|---|---|---|---|
| Kids Tramp · cornerpiece | E97302, E97303, E97305, E97306 | E97402, E97403, E97405, E97406 | 28×47 |
| Kids Tramp **XL** · centrepiece | E97301, E97304 | E97401, E97404 | 28×50 |
| Kids Tramp **Loop** · centrepiece | E97308 | E97408 | 50×36 |
| Kids Tramp **Loop** · cornerpiece | E97307 | E97407 | 50×36 |
| Kids Tramp **Loop XL** · centrepiece **left** | E97310 | E97410 | — |
| Kids Tramp **Loop XL** · centrepiece **right** | E97311 | E97411 | — |
| Kids Tramp **Loop XL** · cornerpiece | E97309 | E97409 | — |
| Kids Tramp **Track** · centrepiece | E97006 (40×50), E97008, E97012 (40×60), E97013 (40×30) | E97056 (40×50), E97058, E97059 (40×60) | 40×{30,50,60} |
| Kids Tramp **Track** · cornerpiece | E97005, E97007 | E97055, E97057 | 40×5 |

**Pairing rule (confirmed by data):** OLD→NEW is `+100` in the e973xx→e974xx block
(Kids Tramp / XL / Loop / Loop XL) and `+50` in the e970xx→e970(5x) block (Track), and
the geometry (`metadata.dimensions`) matches across each pair.

### Proposed structure
One product **per (model, piece)**, with variant axes:
- **System** = `Old (pre-2023)` · `New (EPDM top, 2023)`
- **Size/Length** (Track centrepiece only) = `30 cm` · `50 cm` · `60 cm`
- (Loop XL centrepiece keeps `left` / `right` as the parent split, as today.)

### Open questions before executing
- **Kids Tramp base cornerpiece has 4 articles per system** (E97302/03/05/06) all 28×47.
  These are almost certainly the **4 corner positions** of the square pad, but the local
  pack doesn't label position → need the price list to name them (e.g. front-left … back-right).
- E97013 (40×30, OLD) has no obvious NEW pair listed (E97058 has no dimensions captured) —
  confirm E97013 ↔ E97058 before collapsing.

---

## 2. `adhesive-cartridge` E97003 / E97043 — **re-interpret → propose 2-variant merge**

| article | title | GTIN |
|---|---|---|
| **E97003** | adhesive cartridge for Kids Tramp impact protection | 4260477184610 |
| **E97043** | adhesive cartridge for Kids Tramp impact protection | 4260477194022 |

The task hypothesised "likely 2 **sizes**". The Fallschutz flyer's old/new split and the
article offset (`E97003` → `E97043`, the same `+40` family step seen across the impact-protection
range) indicate these are **two system versions, not two sizes**:
- **E97003** — adhesive for the **OLD** impact-protection system (spare-parts continuity).
- **E97043** — adhesive for the **NEW (2023, EPDM-top)** system.

### Proposed structure
One product **"Adhesive cartridge for Kids Tramp impact protection"** with variant
**System** = `Old system` · `New EPDM system`. _Confidence: medium_ — confirm against the
price list that the cartridge differs by system (vs being an identical consumable simply
re-coded), in which case keep separate / merge as a single SKU instead.

---

## 3. `top-sheet-for-bouncecloud` E21030 / E21031 / E21032 — **insufficient evidence → HOLD**

| article | title | GTIN |
|---|---|---|
| E21030 | Top-Sheet for BounceCloud | 4260477195326 |
| E21031 | Top-Sheet for BounceCloud | 4260477195333 |
| E21032 | Top-Sheet for BounceCloud | 4260477195319 |

The task hypothesised "likely 3 **colours**". **The local pack does not cover BounceCloud**
(it ships in the KidsTramp-PlayPro and Playground-Outdoor packs only), so it provides **no
label** for these three. Moreover, BounceCloud itself is sold in **9 colours** (articles
93000–93008: green/yellow/orange/blue/purple/…), so a **3-way** split is unlikely to be
colour. More plausibly the 3 top-sheets are **3 sizes/formats**, but that is unconfirmed.

**Recommendation:** do **not** merge yet. Resolve the axis with the **BounceCloud price
list / spec sheet** (the only source that distinguishes these three). Once known, merge into
one "Top-Sheet for BounceCloud" with the correct variant axis (size **or** colour-group).

---

## Summary

| Family | Local-pack evidence | Recommendation |
|---|---|---|
| single-tile impact protection (33 SKUs) | **Strong** (Fallschutz old/new + geometry) | Propose merge → 9 parents, System × Size variants |
| adhesive cartridge (E97003/E97043) | Medium (old/new system) | Propose 2-variant merge; confirm vs price list |
| top-sheet for BounceCloud (E21030-32) | **None** | Hold — needs BounceCloud price list |
