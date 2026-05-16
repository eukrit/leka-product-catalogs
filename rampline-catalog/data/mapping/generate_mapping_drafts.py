"""Generate family_mapping_draft.csv + variant_scaffold_draft.csv for review.

Read-only against Medusa (uses an existing snapshot under
rampline-catalog/data/mapping/medusa_snapshot_*.json) and the pricelist xlsx.
Emits two CSVs that the user reviews + edits before any Medusa writes.

  family_mapping_draft.csv
      one row per (pricelist family) — proposed Medusa parent handle,
      proposed size sub-products, sample article codes, confidence.

  variant_scaffold_draft.csv
      one row per pricelist article code — the canonical record of what
      Medusa product + variant we'd create. Includes the parsed
      size/option-1 and surface/option-2, parent handle, suggested
      sub-product handle for Group A equipment (size = its own product),
      or the existing parent handle for Group B parks (each park stays as
      one product, gets 2-3 surface variants).
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[3]
MAPPING_DIR = ROOT / "rampline-catalog" / "data" / "mapping"
PRICELIST = (
    ROOT
    / "rampline-catalog"
    / "data"
    / "source"
    / "rampline_pricelist_2025_fetched-2026-05-13.xlsx"
)

# ---------------------------------------------------------------------------
# Medusa snapshot — find the latest, load it.
# ---------------------------------------------------------------------------
snaps = sorted(MAPPING_DIR.glob("medusa_snapshot_*.json"))
assert snaps, f"No medusa_snapshot_*.json in {MAPPING_DIR}"
SNAPSHOT = snaps[-1]
MEDUSA = json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def upper_ratio(s: str) -> float:
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if c.isupper()) / len(letters)


# Group A = equipment (proper-case title). Group B = park bundles (ALL-CAPS).
GROUP_A = [p for p in MEDUSA if upper_ratio(p["title"]) <= 0.7]
GROUP_B = [p for p in MEDUSA if upper_ratio(p["title"]) > 0.7]

A_BY_HANDLE = {p["handle"]: p for p in GROUP_A}
B_BY_HANDLE = {p["handle"]: p for p in GROUP_B}


# ---------------------------------------------------------------------------
# Pricelist parse.
# ---------------------------------------------------------------------------
def parse_pricelist():
    wb = openpyxl.load_workbook(PRICELIST, read_only=True, data_only=True)
    ws = wb.active
    out = []
    current_family = None
    current_discount = None
    for row_idx, r in enumerate(ws.iter_rows(values_only=True), start=1):
        if not r:
            continue
        a, b, c, d, e = (list(r) + [None] * 5)[:5]
        if a is None and isinstance(b, str) and isinstance(d, (int, float)) and 0 < d < 1:
            # The xlsx uses both ® and ™ glyphs which often arrive as the
            # replacement char � on Windows. Decide by family-name context:
            # SHOCKDECK gets ™, everything else gets ® (single instance:
            # this rule matches both Rampline 2025 + future trademarked items
            # by checking the SKU-prefix family rather than guessing per row).
            raw = b.strip()
            if raw.replace("�", "").strip().upper().startswith("SHOCKDECK"):
                current_family = raw.replace("�", "™")
            else:
                current_family = raw.replace("�", "®")
            current_discount = float(d)
            continue
        if isinstance(a, str) and a.strip().lower() == "article":
            continue
        if (
            isinstance(a, str)
            and a.strip()
            and isinstance(e, (int, float))
            and e > 0
        ):
            out.append(
                {
                    "row": row_idx,
                    "sku": a.strip(),
                    "description": (
                        str(b).replace("�", "®").replace("\xa0", " ").strip()
                        if b
                        else ""
                    ),
                    "family": current_family,
                    "family_discount": current_discount,
                    "recommended_nok": (
                        float(c) if isinstance(c, (int, float)) else None
                    ),
                    "net_nok": float(e),
                }
            )
    return out


# ---------------------------------------------------------------------------
# Article-code parsers — one per pricelist family.
# Each returns:
#   (parent_handle, sub_product_size_key, sub_product_title, surface_key, surface_title)
#
# Group A: sub_product_size_key is the "size" portion. We'll create one new
# Medusa product per (parent, size_key). Surface = variant axis.
# Group B (SHOCKDECK BP codes): sub_product_size_key is None — parks stay as
# one product each, surfaces are the variant axis.
# ---------------------------------------------------------------------------

SURFACE_BY_SUFFIX = {
    "": ("wet_pour", "Wet pour"),       # base / unsuffixed
    "AG": ("artificial_grass", "Artificial grass"),
    "G": ("grass", "Grass"),
    "LF": ("loose_fills", "Loose fills"),
}


def _parse_suffix(sku: str, prefix_re: str) -> tuple[str, str]:
    """Return (size_token, surface_suffix) by stripping the prefix from sku."""
    m = re.match(prefix_re + r"(.*)", sku)
    rest = (m.group(1) if m else sku).strip()
    parts = rest.split()
    # last token is surface if it's one of AG/G/LF
    if parts and parts[-1].upper() in ("AG", "G", "LF"):
        return " ".join(parts[:-1]).strip(), parts[-1].upper()
    return rest, ""


# Per-family rules. Two model styles:
#  - size_as_product:  Size becomes its own Medusa product. Surface is the
#                      sole variant option. Used for clean Size × Surface
#                      families (Rampball, Jumpstone).
#  - single_product:   One Medusa product per family parent; the variant
#                      axes (Size, Style, Component, Surface, Type, etc.)
#                      are encoded as Medusa options. Used for multi-axis
#                      or service-bundle families (Rampit, Rampit Hopper,
#                      BalanceBuddy, Fungi, Floating Bench, etc.) per
#                      user decision 2026-05-16.
FAMILY_RULES: dict[str, dict] = {
    "Tilting and rotating balance balls": {
        "model": "size_as_product",
        "parent_handle": "rampline-rampball",
        "prefix_re": r"RB",
        "size_label": lambda tok: f"Rampball {tok}",
        "size_slug": lambda tok: tok.lower(),
    },
    "Slack line rack with padded ramps and dynamic line": {
        # Only one size (RL410); RL410 EXT is just the loose-fills variant.
        "model": "single_product",
        "parent_handle": "rampline-rampline-slackline",
        "prefix_re": r"RL410",
        # Surface comes from the EXT suffix:
        #   RL410     → wet_pour
        #   RL410 EXT → loose_fills (description: "for grass and loose fills")
        "option_axes": [("Surface", "_ext_surface")],
    },
    "Natural rubber jump pads with a rough surface.": {
        "model": "size_as_product",
        "parent_handle": "rampline-jumpstone-en",
        "prefix_re": r"JS",
        "size_label": lambda tok: f"Jumpstone {tok}",
        "size_slug": lambda tok: tok.lower(),
    },
    "Balance beam, with shock absorbing natural rubber padding": {
        # 2 options: Length × Style
        # BB216R, BB216R EXT, BB216S, BB316R, BB316R EXT, BB316S
        "model": "single_product",
        "parent_handle": "rampline-balancebuddy-en",
        "prefix_re": r"BB",
        "option_axes": [("Length", "_bb_length"), ("Style", "_bb_style")],
    },
    "Zig-Zag balance beam, with shock absorbing natural rubber padding": {
        # 1 option: Surface (BB316W, BB316W LF)
        "model": "single_product",
        "parent_handle": "rampline-balancebuddy-wave",
        "prefix_re": r"BB316W",
        "option_axes": [("Surface", "_ext_surface")],
    },
    "Climbing mushrooms": {
        # 1 option: Size (F3, F5, F5 EXT — F5 EXT is the "for loose fills" version of F5)
        "model": "single_product",
        "parent_handle": "rampline-fungi-eng",
        "prefix_re": r"F",
        "option_axes": [("Size", "_fungi_size")],
    },
    "Fully welded, and powdercoated gim barr": {
        # Rampit Twin — 2 SKUs across 2 sizes (200, 220)
        "model": "single_product",
        "parent_handle": "rampline-rampit-swing",
        "prefix_re": r"4551",
        "option_axes": [("Size", "_rampit_twin_size")],
    },
    "Fully welded, and powdercoated activity rack": {
        # Rampit 85/120/150 — 1 option: Size
        "model": "single_product",
        "parent_handle": "rampline-rampit",
        "prefix_re": r"455[234]",
        "option_axes": [("Size", "_rampit_size")],
    },
    "Fully welded, and powdercoated activity bars and turning pads": {
        # Rampit Hopper — 2 options: Component × Surface
        # 4562 (activity bars), 4561 (rack), 4561-1 (turning pads), each with EXT (loose fills) variant
        "model": "single_product",
        "parent_handle": "rampline-rampit-hopper",
        "prefix_re": r"456[12](?:-\d)?",
        "option_axes": [("Component", "_hopper_component"), ("Surface", "_ext_surface")],
    },
    "Powder coated climbing pole, with bell on top": {
        "model": "single_product",
        "parent_handle": "rampline-rampit-storm-en",
        "prefix_re": r"4556",
        "option_axes": [],  # 1 SKU, no option needed
    },
    "Powder coated balance arch": {
        # Rampbow 4560 / 4560 EXT — 1 option: Surface
        "model": "single_product",
        "parent_handle": "rampline-rampbow",
        "prefix_re": r"4560",
        "option_axes": [("Surface", "_ext_surface")],
    },
    "Individually adapted bench that floats and rolls through the landscape, inspiring the user to creative physical movements": {
        # Floating Bench — 1 option: Type (Bench / LED strip / Customization / Rigging)
        "model": "single_product",
        "parent_handle": "rampline-floating-bench",
        "prefix_re": r"FB33",
        "option_axes": [("Type", "_fb_type")],
    },
    "SHOCKDECK™": {
        # Each BP code maps to one of the parks. SD 02 is a component on rampline-shockdeck.
        "model": "parks",
        "parent_handle": None,
    },
}


# ---------------------------------------------------------------------------
# Per-family option-value resolvers — return (key, label) for a SKU's row.
# ---------------------------------------------------------------------------
def _ext_surface(sku_rest: str, row: dict) -> tuple[str, str]:
    """RL410 / 4560 / BB316W / Rampbow / Wave: bare = WP, EXT or LF suffix = loose fills."""
    if re.search(r"\b(EXT|LF)\b", sku_rest, re.IGNORECASE):
        return ("loose_fills", "Loose fills")
    return ("wet_pour", "Wet pour")


def _bb_length(sku_rest: str, row: dict) -> tuple[str, str]:
    m = re.match(r"(\d{3})", sku_rest)
    if m:
        return (f"{m.group(1)}cm", f"{m.group(1)} cm")
    return ("?", "?")


def _bb_style(sku_rest: str, row: dict) -> tuple[str, str]:
    # BB216R, BB216R EXT → Straight (R for straight)
    # BB216S → Slanted
    # the R-EXT pair both get "Straight" but the EXT means loose_fills surface
    if re.search(r"\d{3}S\b", sku_rest):
        return ("slanted_wp", "Slanted (wet pour)")
    if re.search(r"\d{3}R EXT", sku_rest):
        return ("straight_lf", "Straight (loose fills)")
    if re.search(r"\d{3}R\b", sku_rest):
        return ("straight_wp", "Straight (wet pour)")
    return ("?", "?")


def _fungi_size(sku_rest: str, row: dict) -> tuple[str, str]:
    # F3, F5, F5 EXT — strip trailing colour code
    cleaned = re.sub(r"\s*\d{4}\b.*$", "", sku_rest).strip()
    if cleaned.startswith("3"):
        return ("3_stems_wp", "3 stems (wet pour)")
    if "EXT" in cleaned:
        return ("5_stems_lf", "5 stems (loose fills)")
    if cleaned.startswith("5"):
        return ("5_stems_wp", "5 stems (wet pour)")
    return ("?", cleaned or "?")


def _rampit_twin_size(sku_rest: str, row: dict) -> tuple[str, str]:
    # 4551 9001 → Twin 200; 4551 EXT → Twin 220
    desc = row.get("description", "")
    m = re.search(r"\b(2\d{2})\b", desc)
    if m:
        return (f"{m.group(1)}cm", f"{m.group(1)} cm")
    return ("?", "?")


def _rampit_size(sku_rest: str, row: dict) -> tuple[str, str]:
    desc = row.get("description", "")
    m = re.search(r"Rampit.*?(\d{2,3})\s*cm", desc)
    if not m:
        m = re.search(r"\b(\d{2,3})\s*cm", desc)
    if m:
        return (f"{m.group(1)}cm", f"{m.group(1)} cm")
    # Fall back from the prefix code: 4552→85, 4553→120, 4554→150
    sku = row.get("sku", "")
    if sku.startswith("4552"): return ("85cm", "85 cm")
    if sku.startswith("4553"): return ("120cm", "120 cm")
    if sku.startswith("4554"): return ("150cm", "150 cm")
    return ("?", "?")


def _hopper_component(sku_rest: str, row: dict) -> tuple[str, str]:
    sku = row.get("sku", "")
    desc = row.get("description", "")
    if sku.startswith("4562"):
        return ("activity_bars", "Activity bars")
    if sku.startswith("4561-1") or "turning pads" in desc.lower():
        return ("turning_pads", "Turning pads")
    if sku.startswith("4561"):
        return ("rack", "Rack")
    return ("?", "?")


def _fb_type(sku_rest: str, row: dict) -> tuple[str, str]:
    sku = row.get("sku", "")
    if sku == "FB33":
        return ("bench", "Bench")
    if sku == "FB33LED":
        return ("led_strip", "LED strip (per meter)")
    if sku == "FB33-1":
        return ("customization", "Customization / site adaptation")
    if sku == "FB33-2":
        return ("rigging", "Rigging & operation")
    return ("?", sku)


_RESOLVERS = {
    "_ext_surface": _ext_surface,
    "_bb_length": _bb_length,
    "_bb_style": _bb_style,
    "_fungi_size": _fungi_size,
    "_rampit_twin_size": _rampit_twin_size,
    "_rampit_size": _rampit_size,
    "_hopper_component": _hopper_component,
    "_fb_type": _fb_type,
}


# BP NN → park handle. Derived from descriptions in the pricelist + Medusa
# product titles. Mark uncertain ones for user review.
BP_TO_PARK = {
    "BP 01": ("rampline-kangaroo", "Kangaroo"),
    "BP 03": ("rampline-jane-jump", "Jane Jump"),
    "BP 05": ("rampline-monkey-business", "Monkey Business"),
    "BP 06": ("rampline-all-in", "All In"),
    "BP 08": ("rampline-the-floor-is-lava", "The Floor Is Lava"),
    "BP 10": ("rampline-dont-step-into-the-water", "Don't Step Into The Water"),
    "BP 11": ("rampline-junior-power-ii", "Junior Power II"),
    "BP 15": ("rampline-marathon-play", "Marathon Play"),
    "BP 17": ("rampline-junior-power", "Junior Power"),
    "BP 18": ("rampline-never-stop-playing", "Never Stop Playing"),
    "BP 19": ("rampline-classic-jump", "Classic Jump"),
    "BP 21": ("rampline-fearless", "Fearless"),
    "BP 22": ("rampline-crouching-tiger", "Crouching Tiger"),
    "BP 24": ("rampline-cliffhanger", "Cliffhanger"),
    "BP 25": ("rampline-take-5", "Take 5"),
    "BP 27": ("rampline-pulse-zone", "Pulse Zone"),
    "BP 30": ("rampline-hunting-high-and-low", "Hunting High and Low"),
    "BP 31": ("rampline-defying-gravity", "Defying Gravity"),
    "BP 32": ("rampline-fast-and-curious", "Fast and Curious"),
    "BP 33": ("rampline-play-tag", "Play Tag"),
    "BP 34": ("rampline-flex-forest", "Flex Forest"),
}


def parse_article_code(row: dict) -> dict:
    """Return parser result for one pricelist row. Adds error / unmapped flag."""
    sku = row["sku"]
    family = row["family"]
    rule = FAMILY_RULES.get(family)
    if not rule:
        return {**row, "unmapped": True, "error": f"unknown family: {family}"}

    # SHOCKDECK family: parks + SD-02 component
    if rule.get("model") == "parks":
        if re.match(r"SD ?\d+", sku):
            return {
                **row,
                "group": "B-component",
                "parent_handle": "rampline-shockdeck",
                "parent_title": "ShockDeck",
                "sub_product_handle": "rampline-shockdeck",
                "sub_product_title": "ShockDeck",
                "size_slug": None,
                "size_label": "ShockDeck component",
                "options": [],  # no option axis — single default variant
                "variant_sku": sku,
                "variant_title": "U-piece",
            }
        m = re.match(r"(BP ?\d+)\s*(.*)", sku)
        if not m:
            return {**row, "unmapped": True, "error": f"unrecognized SHOCKDECK code: {sku}"}
        bp_norm = re.sub(r"BP ?", "BP ", m.group(1)).strip()
        if not bp_norm.startswith("BP "):
            bp_norm = "BP " + bp_norm.replace("BP", "").strip()
        suffix = m.group(2).strip().upper()
        if bp_norm not in BP_TO_PARK:
            return {**row, "unmapped": True, "error": f"BP code {bp_norm!r} has no park mapping"}
        parent_handle, park_title = BP_TO_PARK[bp_norm]
        surface_key, surface_title = SURFACE_BY_SUFFIX.get(
            suffix, (f"unknown_{suffix.lower()}", suffix)
        )
        return {
            **row,
            "group": "B-park",
            "parent_handle": parent_handle,
            "parent_title": park_title,
            "sub_product_handle": parent_handle,
            "sub_product_title": park_title,
            "size_slug": None,
            "size_label": park_title,
            "options": [("Surface", surface_key, surface_title)],
            "variant_sku": sku,
            "variant_title": surface_title,
        }

    # Group A equipment
    parent_handle = rule["parent_handle"]
    parent = A_BY_HANDLE.get(parent_handle) or B_BY_HANDLE.get(parent_handle)
    parent_title = parent["title"] if parent else parent_handle

    if rule["model"] == "size_as_product":
        # Rampball, Jumpstone — Size is its own product, Surface is the variant axis.
        size_token, surface_suffix = _parse_suffix(sku, rule["prefix_re"])
        size_token = re.sub(r"\s*\d{4}\b.*$", "", size_token).strip()
        if not size_token:
            size_token = "standard"
        size_label = rule["size_label"](size_token)
        size_slug = rule["size_slug"](size_token)
        surface_key, surface_title = SURFACE_BY_SUFFIX.get(
            surface_suffix, (f"unknown_{surface_suffix.lower()}", surface_suffix)
        )
        sub_handle = f"{parent_handle}-{size_slug}"
        return {
            **row,
            "group": "A-equipment",
            "parent_handle": parent_handle,
            "parent_title": parent_title,
            "sub_product_handle": sub_handle,
            "sub_product_title": size_label,
            "size_slug": size_slug,
            "size_label": size_label,
            "options": [("Surface", surface_key, surface_title)],
            "variant_sku": sku,
            "variant_title": surface_title,
        }

    # single_product: variants live directly on the parent, axes per option_axes
    sku_rest = re.sub(r"^" + rule["prefix_re"], "", sku).strip()
    options: list[tuple[str, str, str]] = []
    for option_title, resolver_name in rule.get("option_axes", []):
        key, label = _RESOLVERS[resolver_name](sku_rest, row)
        options.append((option_title, key, label))
    variant_title = " / ".join(o[2] for o in options) if options else "Default"
    return {
        **row,
        "group": "A-equipment",
        "parent_handle": parent_handle,
        "parent_title": parent_title,
        "sub_product_handle": parent_handle,
        "sub_product_title": parent_title,
        "size_slug": None,
        "size_label": None,
        "options": options,
        "variant_sku": sku,
        "variant_title": variant_title,
    }


# ---------------------------------------------------------------------------
# Run + write CSVs.
# ---------------------------------------------------------------------------
def main():
    rows = parse_pricelist()
    parsed = [parse_article_code(r) for r in rows]

    # variant_scaffold_draft.csv — one row per pricelist article code
    scaffold_cols = [
        "row", "sku", "description", "family", "family_discount",
        "group", "parent_handle", "parent_title",
        "sub_product_handle", "sub_product_title",
        "size_slug", "size_label",
        "options_flat", "variant_sku", "variant_title",
        "recommended_nok", "net_nok",
        "unmapped", "error",
    ]
    out_scaffold = MAPPING_DIR / "variant_scaffold_draft.csv"
    with out_scaffold.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=scaffold_cols)
        w.writeheader()
        for p in parsed:
            opts = p.get("options") or []
            opts_flat = "|".join(f"{t}={k}:{l}" for (t, k, l) in opts)
            w.writerow({**{c: p.get(c, "") for c in scaffold_cols}, "options_flat": opts_flat})
    print(f"Wrote {out_scaffold}  ({len(parsed)} rows)")

    # family_mapping_draft.csv — one row per (family, parent_handle, sub_product_handle)
    by_subprod: dict[tuple, list] = {}
    for p in parsed:
        if p.get("unmapped"):
            continue
        key = (
            p["family"], p["family_discount"],
            p["parent_handle"], p["parent_title"],
            p["sub_product_handle"], p["sub_product_title"],
            p["size_slug"] or "",
            p["group"],
        )
        by_subprod.setdefault(key, []).append(p)

    out_fm = MAPPING_DIR / "family_mapping_draft.csv"
    with out_fm.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "family", "family_discount",
            "parent_handle", "parent_title",
            "sub_product_handle", "sub_product_title",
            "size_slug", "group", "n_variants",
            "option_titles", "variant_titles", "article_codes",
            "decision",
        ])
        for key in sorted(by_subprod.keys()):
            rows = by_subprod[key]
            (family, disc, parent_handle, parent_title,
             sub_handle, sub_title, size_slug, group) = key
            opt_titles = sorted({o[0] for r in rows for o in (r.get("options") or [])})
            v_titles = sorted({r.get("variant_title", "") for r in rows})
            skus = sorted({r["sku"] for r in rows})
            w.writerow([
                family, f"{disc:.2f}",
                parent_handle, parent_title,
                sub_handle, sub_title,
                size_slug or "", group, len(rows),
                "|".join(opt_titles),
                "|".join(v_titles),
                "|".join(skus),
                "",
            ])
    print(f"Wrote {out_fm}  ({len(by_subprod)} subproduct rows)")

    # Stats
    groups = {}
    for p in parsed:
        g = p.get("group", "unmapped")
        groups[g] = groups.get(g, 0) + 1
    unmapped = [p for p in parsed if p.get("unmapped")]
    print()
    print(f"Total pricelist rows: {len(parsed)}")
    print(f"By group: {groups}")
    print(f"Unmapped: {len(unmapped)}")
    for u in unmapped:
        print(f"  row{u['row']}  {u['sku']!r:14}  family={u['family']!r:60}  reason={u.get('error')!r}")
    # Group B parks not in any pricelist
    parked_priced = {p["parent_handle"] for p in parsed if p.get("group") == "B-park"}
    parked_all = {p["handle"] for p in GROUP_B}
    no_pricelist = parked_all - parked_priced
    print()
    print(f"Group B parks NOT in pricelist ({len(no_pricelist)}): "
          f"{sorted(no_pricelist)}")
    # Group A products not referenced
    a_referenced = {p["parent_handle"] for p in parsed if p.get("group", "").startswith("A")}
    a_all = {p["handle"] for p in GROUP_A}
    a_not_referenced = a_all - a_referenced - {"rampline-shockdeck"}
    print()
    print(f"Group A products NOT referenced by any pricelist row "
          f"({len(a_not_referenced)}): {sorted(a_not_referenced)}")


if __name__ == "__main__":
    main()
