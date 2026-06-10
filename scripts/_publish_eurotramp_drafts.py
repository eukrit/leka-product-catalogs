"""Publish the 3 draft Eurotramp Kids-Tramp-Track spare-part umbrellas.

These carried the 2026 collision SKUs and were status=draft (hidden from the
storefront). After their variant prices were reconciled, publish them.
Idempotent: a product already published is left as-is. Retries on 5xx/timeout.
"""
from __future__ import annotations

import os
import sys
import time

import requests

BACKEND = "https://leka-medusa-backend-538978391890.asia-southeast1.run.app"
TIMEOUT = 120

PRODUCTS = {
    "eurotramp-jumping-bed-kids-tramp-track-playground": "prod_01KRGBFYKS2QKXDPTV24VV3K71",
    "eurotramp-bonded-impact-protection-kids-tramp-track": "prod_01KRGBDCAE69EYQGMYZ2KYPWJY",
    "eurotramp-playpro-rubber-protection-lip-for-kids-tramp-track": "prod_01KRGBHT3E0WK7EJ4QA2FV18CD",
}


def auth() -> str:
    r = requests.post(f"{BACKEND}/auth/user/emailpass",
                      json={"email": os.environ["LEKA_MEDUSA_ADMIN_EMAIL"],
                            "password": os.environ["LEKA_MEDUSA_ADMIN_PASSWORD"]},
                      timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["token"]


def main() -> int:
    token = auth()
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    rc = 0
    for handle, pid in PRODUCTS.items():
        g = requests.get(f"{BACKEND}/admin/products/{pid}",
                         params={"fields": "id,handle,status"}, headers=h, timeout=TIMEOUT)
        g.raise_for_status()
        cur = (g.json().get("product") or {}).get("status")
        if cur == "published":
            print(f"  already published: {handle}")
            continue
        ok = False
        delay = 3.0
        for attempt in range(1, 6):
            try:
                r = requests.post(f"{BACKEND}/admin/products/{pid}",
                                  json={"status": "published"}, headers=h, timeout=TIMEOUT)
                if r.status_code < 300:
                    print(f"  PUBLISHED {handle} ({cur} -> published)")
                    ok = True
                    break
                print(f"  {handle} status {r.status_code} (attempt {attempt}/5) — retry in {delay:.0f}s")
            except requests.RequestException as e:
                print(f"  {handle} error (attempt {attempt}/5): {str(e)[:100]} — retry in {delay:.0f}s")
            time.sleep(delay)
            delay = min(delay * 2, 30.0)
        if not ok:
            print(f"  FAILED to publish {handle}")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
