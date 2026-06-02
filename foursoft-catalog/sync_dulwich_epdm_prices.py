"""Refresh the Dulwich R2 draft order (order_01KSTN74...) 4soft EPDM line prices
to the new live Medusa catalog SGD (the 20%-discount sea-LCL reprice).

Surgical in-place edit via the Medusa v2 draft-order edit workflow — keeps the
51-line set intact, only repoints the 22 EPDM (^[A-Z]d-dd[A-Z]-...) line
unit_prices to vendors/4soft.retail_sgd (== synced catalog). Targets are read
from foursoft-catalog/data/pricelist_2025-03-01_landed.csv (item_code->retail_sgd),
verified equal to live Medusa.

Dry-run by default; --write to apply.
"""
from __future__ import annotations
import argparse, csv, re, subprocess, sys, time
from pathlib import Path
import requests

DO_ID = "order_01KSTN74NRPQ3DGETVHERQ1Z2G"
BASE = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
LANDED = Path(__file__).resolve().parent / "data" / "pricelist_2025-03-01_landed.csv"


def sec(n):
    return subprocess.run(["gcloud", "secrets", "versions", "access", "latest",
                           f"--secret={n}", "--project=ai-agents-go"],
                          capture_output=True, text=True, shell=True).stdout.strip()


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", str(s).upper()) if s else ""


def is_epdm(c):
    return bool(re.match(r"^[A-Z]\d-\d{2}[A-Z]-\d{2,3}", (c or "").upper()))


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    args = ap.parse_args()

    key = sec("medusa-admin-api-key-proposal-engine")
    A = (key, "")
    target = {norm(r["item_code"]): float(r["retail_sgd"]) for r in
              csv.DictReader(LANDED.open(encoding="utf-8")) if r.get("retail_sgd")}

    pe = requests.get(f"{BASE}/admin/draft-orders/{DO_ID}/proposal-export", auth=A, timeout=40).json()
    items = pe["cart"]["items"]
    updates = []
    for it in items:
        code = (it.get("metadata") or {}).get("product_code")
        if not is_epdm(code):
            continue
        n = norm(code)
        if n not in target:
            print(f"  ! EPDM line {code} has no catalog target — skipping")
            continue
        want_cents = int(round(target[n] * 100))
        cur_cents = it.get("unit_price") or 0
        if abs(want_cents - cur_cents) > 0:
            updates.append((it["id"], code, cur_cents, want_cents, it.get("quantity") or 1))

    print(f"draft order {DO_ID}: {len(items)} lines; {len(updates)} EPDM lines to update")
    for iid, code, cur, want, qty in updates:
        print(f"  {code:<16} {cur/100:>10,.2f} -> {want/100:>10,.2f}  ({(want-cur)/cur*100:+.1f}%)")
    if not args.write:
        print("(dry-run — re-run with --write to apply)")
        return 0
    if not updates:
        print("nothing to update")
        return 0

    r = requests.post(f"{BASE}/admin/draft-orders/{DO_ID}/edit", auth=A, json={}, timeout=40)
    if r.status_code >= 300:
        print("begin-edit failed:", r.status_code, r.text[:300]); return 1
    print("edit session begun")
    try:
        for iid, code, cur, want, qty in updates:
            ur = requests.post(
                f"{BASE}/admin/draft-orders/{DO_ID}/edit/items/item/{iid}",
                auth=A, json={"unit_price": want, "quantity": int(qty)}, timeout=40)
            if ur.status_code >= 300:
                raise RuntimeError(f"update {code} failed: {ur.status_code} {ur.text[:200]}")
            print(f"  updated {code} -> {want/100:,.2f}")
        cr = requests.post(f"{BASE}/admin/draft-orders/{DO_ID}/edit/confirm", auth=A, json={}, timeout=60)
        if cr.status_code >= 300:
            raise RuntimeError(f"confirm failed: {cr.status_code} {cr.text[:300]}")
        print("edit confirmed.")
    except Exception as e:
        print("ERROR:", e)
        requests.delete(f"{BASE}/admin/draft-orders/{DO_ID}/edit", auth=A, timeout=40)
        print("edit session cancelled (rolled back).")
        return 1

    time.sleep(2)
    pe2 = requests.get(f"{BASE}/admin/draft-orders/{DO_ID}/proposal-export", auth=A, timeout=40).json()
    ok = 0
    for it in pe2["cart"]["items"]:
        code = (it.get("metadata") or {}).get("product_code")
        n = norm(code)
        if is_epdm(code) and n in target and abs((it.get("unit_price") or 0) - int(round(target[n] * 100))) <= 1:
            ok += 1
    print(f"verified {ok}/{len(updates)} EPDM lines now match the 20% catalog")
    return 0


if __name__ == "__main__":
    sys.exit(main())
