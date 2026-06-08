"""Bootstrap the PolySoft brand in the Leka Medusa backend.

Creates (idempotently):
  1. A "Polysoft" Sales Channel.
  2. A "Polysoft Storefront" publishable API key.
  3. The key <-> sales-channel link.

Mirrors how Vortex was onboarded (its products land in the per-brand
"Vortex Aquatics" sales channel). Product creation itself is done by
`vendors/polysoft-catalog/scripts/push_to_medusa.py`, which imports the
scraped PolySoft range into the sales channel id this script prints.

PolySoft has no public SKUs/pricing, so products ship without prices
(hasPricing:false), exactly like Vortex's initial onboarding.

Auth resolution (leak-resistant, Rule 12):
  env LEKA_MEDUSA_ADMIN_EMAIL / LEKA_MEDUSA_ADMIN_PASSWORD
  -> else fetched from Secret Manager (medusa-admin-email / medusa-admin-password)
     via gcloud with the active identity.

Run:
    python scripts/bootstrap_polysoft.py            # create / confirm
    python scripts/bootstrap_polysoft.py --print    # just print existing ids
"""
from __future__ import annotations

import os
import subprocess
import sys

import requests

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
SC_NAME = "Polysoft"
SC_DESCRIPTION = "Seamless wet-pour / EPDM aquatic safety surfacing (PolySoft Surfaces)"
PK_TITLE = "Polysoft Storefront"
TIMEOUT = 45


def _sm(secret: str) -> str | None:
    try:
        r = subprocess.run(
            ["gcloud", "secrets", "versions", "access", "latest",
             f"--secret={secret}", "--project=ai-agents-go"],
            capture_output=True, text=True, timeout=30, shell=(os.name == "nt"),
        )
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None
    except Exception:  # noqa: BLE001
        return None


def _creds() -> tuple[str, str]:
    email = os.environ.get("LEKA_MEDUSA_ADMIN_EMAIL") or _sm("leka-medusa-admin-email")
    pw = os.environ.get("LEKA_MEDUSA_ADMIN_PASSWORD") or _sm("leka-medusa-admin-password")
    if not (email and pw):
        raise RuntimeError(
            "Medusa admin creds not found. Set LEKA_MEDUSA_ADMIN_EMAIL / "
            "LEKA_MEDUSA_ADMIN_PASSWORD or grant access to the leka-medusa-admin-* secrets."
        )
    return email, pw


def auth() -> str:
    email, pw = _creds()
    r = requests.post(f"{BACKEND}/auth/user/emailpass",
                      json={"email": email, "password": pw}, timeout=TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"auth failed ({r.status_code})")
    return r.json()["token"]


def find_sales_channel(token: str, name: str) -> dict | None:
    H = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BACKEND}/admin/sales-channels", headers=H,
                     params={"limit": 200}, timeout=TIMEOUT)
    r.raise_for_status()
    for s in r.json().get("sales_channels", []):
        if s["name"].strip().lower() == name.lower():
            return s
    return None


def create_sales_channel(token: str) -> dict:
    H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(f"{BACKEND}/admin/sales-channels", headers=H,
                      json={"name": SC_NAME, "description": SC_DESCRIPTION}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["sales_channel"]


def find_publishable_key(token: str, title: str) -> dict | None:
    H = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BACKEND}/admin/api-keys", headers=H,
                     params={"limit": 200, "type": "publishable"}, timeout=TIMEOUT)
    r.raise_for_status()
    for k in r.json().get("api_keys", []):
        if k.get("title", "").strip().lower() == title.lower():
            return k
    return None


def create_publishable_key(token: str) -> dict:
    H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(f"{BACKEND}/admin/api-keys", headers=H,
                      json={"title": PK_TITLE, "type": "publishable"}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["api_key"]


def link_key_to_sc(token: str, key_id: str, sc_id: str) -> None:
    H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(f"{BACKEND}/admin/api-keys/{key_id}/sales-channels", headers=H,
                      json={"add": [sc_id]}, timeout=TIMEOUT)
    # 200 on success; ignore "already linked" style 4xx.
    if r.status_code not in (200, 201):
        print(f"[warn] link key->sc returned {r.status_code}: {r.text[:160]}")


def main():
    print_only = "--print" in sys.argv
    token = auth()
    print("[auth] ok")

    sc = find_sales_channel(token, SC_NAME)
    if sc:
        print(f"[sc] exists: {sc['id']}  ({sc['name']})")
    elif print_only:
        print("[sc] none (run without --print to create)")
    else:
        sc = create_sales_channel(token)
        print(f"[sc] created: {sc['id']}  ({sc['name']})")

    key = find_publishable_key(token, PK_TITLE)
    if key:
        print(f"[pk] exists: {key['id']}  token={key.get('token')}")
    elif print_only:
        print("[pk] none (run without --print to create)")
    else:
        key = create_publishable_key(token)
        print(f"[pk] created: {key['id']}  token={key.get('token')}")

    if sc and key and not print_only:
        link_key_to_sc(token, key["id"], sc["id"])
        print(f"[link] key {key['id']} -> sc {sc['id']}")

    if sc and key:
        print("\n=== WIRE THESE ===")
        print(f"SALES_CHANNEL_ID = {sc['id']}")
        print(f"PUBLISHABLE_KEY  = {key.get('token')}")
        print("vendors/polysoft-catalog/scripts/push_to_medusa.py -> POLYSOFT_SC")
        print("leka-website/cloudbuild-catalogs.yaml -> _PK_POLYSOFT (token, browser-exposed)")


if __name__ == "__main__":
    main()
