"""Send the Eurotramp request email FROM eukrit@goco.bz via Gmail API (DWD).

Asks Eurotramp for: (1) updated partner/dashboard access for GO Corporation,
(2) the updated full 2026 price list in Excel, (3) the missing per-SKU packing
dimensions + gross weight needed for Thai sea-freight landed-cost pricing.

Uses the ai-agents-go service account with domain-wide delegation, impersonating
eukrit@goco.bz with the gmail.send scope (same pattern as
wisdom-catalog/request_raw_media_from_wisdom.py).

Usage:
    python scripts/send_eurotramp_request.py --dry-run   # build, don't send
    python scripts/send_eurotramp_request.py             # actually send
"""
from __future__ import annotations

import argparse
import base64
import logging
import os
from email.mime.text import MIMEText
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
SENDER = "eukrit@goco.bz"          # DWD subject + From
TO = ["deli@eurotramp.com"]
CC = ["shipping@goco.bz", "niwat@goco.bz"]
SUBJECT = "Eurotramp x GO Corporation - dashboard access, 2026 price list & packing data"

DEFAULT_SA_KEY = Path(
    r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code"
    r"\GCP Credentials\ai-agents-go-claude.json"
)

BODY = """\
Dear Elif,

I hope all is well in Weilheim. As we continue to grow the Eurotramp range with our customers here in Thailand, there are three things that would help us a great deal, and I would be very grateful for your support.

1) Dashboard / partner portal access
If Eurotramp provides a partner or customer dashboard (orders, price lists, product data, downloads) for GO Corporation Co., Ltd., could you please set up or refresh our access and confirm the login details? If our account already exists, an updated invite or password reset to this address would be perfect.

2) Updated 2026 price list (Excel)
Could you please send us the current 2026 price list, valid from 01.03.2026, in Excel for the full range - Production Performance Series as well as Kids Tramp / BounceCloud? We have the 2026 Kids Tramp + BounceCloud sheet and the 2025 Production Performance Series Excel, but not yet the 2026 Production Performance Series in Excel form.

3) Per-SKU packing dimensions and weights (for logistics)
To calculate our Thai landed costs accurately (using real sea-freight volume rather than a flat uplift) we need packing data per article, which the price lists do not include. For each article, could you share:

  - Packed dimensions (L x W x H, in cm) per package/crate
  - Packed (gross) weight in kg per package
  - Number of packages per article when an item ships in more than one box/crate
  - Whether the item ships knocked-down/flat-packed or pre-assembled
  - Volumetric or chargeable weight, if you already compute it for your freight quotes

XLSX or CSV is ideal, but any format is fine. If a master packing or shipping-data list already exists internally (e.g. for your own freight quotations), that would save you compiling one fresh.

This will let us quote Thai projects faster and more accurately, replace our current flat shipping uplift with real per-SKU landed costs, and prepare customs paperwork more reliably. We are also building a structured catalog of the Eurotramp range so it is easily searchable for our Thai sales team and customers, and this data would round it out nicely.

Many thanks for your support.

Best regards,
Eukrit

Eukrit Kraikosol
Director, GO Corporation Co., Ltd.
M +66 61 4916393 | eukrit@goco.bz
"""

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("send_eurotramp_request")


def build_service(sa_key: Path):
    creds = service_account.Credentials.from_service_account_file(
        str(sa_key), scopes=SCOPES, subject=SENDER
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sa-key", type=Path,
                    default=Path(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")) or DEFAULT_SA_KEY)
    ap.add_argument("--dry-run", action="store_true", help="Build the message but do not send.")
    args = ap.parse_args()

    sa_key = args.sa_key if args.sa_key and Path(args.sa_key).is_file() else DEFAULT_SA_KEY
    if not sa_key.is_file():
        raise SystemExit(f"SA key not found: {sa_key}")

    msg = MIMEText(BODY, "plain", "utf-8")
    msg["From"] = SENDER
    msg["To"] = ", ".join(TO)
    msg["Cc"] = ", ".join(CC)
    msg["Subject"] = SUBJECT
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    log.info("From:    %s", SENDER)
    log.info("To:      %s", ", ".join(TO))
    log.info("Cc:      %s", ", ".join(CC))
    log.info("Subject: %s", SUBJECT)

    if args.dry_run:
        log.info("[dry-run] not sending. Body:\n%s", BODY)
        return

    svc = build_service(sa_key)
    sent = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
    log.info("Sent — message id: %s, threadId: %s", sent.get("id"), sent.get("threadId"))


if __name__ == "__main__":
    main()
