"""Send an Eurotramp request email FROM eukrit@goco.bz via Gmail API (DWD).

Asks Eurotramp for the two gaps left after pricing the competition/performance
line from "Price list 2025 (1E)":
  (1) net purchase prices (EUR) for 6 articles missing from that list, and
  (2) high-resolution product photos for items we have no usable hero image for.

Same DWD pattern as scripts/send_eurotramp_request.py (SA impersonates
eukrit@goco.bz, gmail.send scope).

Usage:
    python scripts/send_eurotramp_pricing_photos_request.py --dry-run   # render only
    python scripts/send_eurotramp_pricing_photos_request.py             # actually send
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
SENDER = "eukrit@goco.bz"
TO = ["deli@eurotramp.com"]
CC = ["shipping@goco.bz", "niwat@goco.bz"]
SUBJECT = "Eurotramp x GO Corporation - prices for 6 articles + product photos"

DEFAULT_SA_KEY = Path(
    r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code"
    r"\GCP Credentials\ai-agents-go-claude.json"
)

BODY = """\
Dear Elif,

Thank you again for the price list. We are building out the Eurotramp competition / performance range in our catalogue and have priced most of it from "Price list 2025 (1E)". Two small gaps remain, and your help would let us finish the line.

1) Net purchase prices (EUR) for 6 articles not in the 2025 (1E) list
A handful of articles we sell are not on the sheet we have. Could you please send the current net purchase price (EUR, ex-works) for each:

  - 38000  - Complete Competition Trampoline (competition set / field of play)
  - 40000  - FiveSquare
  - 98001B - Trampoline Set "Freestyle"
  - 28330  - Spieth Ground Safety Mat
  - 28600F - Spotting Mat "Freestyle"
  - 26200  - Set of Landing Mats (Double-Minitramp)

If any of these has been renamed, superseded, or is quoted only on request, just let us know the current article and price.

2) High-resolution product photos
For a few items we do not yet have a usable product photo and are currently showing a placeholder or a component image. Could you share high-resolution photography (or a link to your media library) for:

  - Trampoline Set "One Field" (98001K) - a hero shot of the complete one-field setup
  - Complete Competition Trampoline (38000) - an assembled competition field-of-play image

More broadly, if you have a media pack for the Performance Series (Master, Grand Master, Ultimate, Ultimate Freestyle, DMT) and the competition accessories, we would gladly take it - good imagery helps our Thai customers a lot.

Many thanks for your support.

Best regards,
Eukrit

Eukrit Kraikosol
Director, GO Corporation Co., Ltd.
M +66 61 4916393 | eukrit@goco.bz
"""

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("send_eurotramp_pricing_photos_request")


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
    log.info("Sent - message id: %s, threadId: %s", sent.get("id"), sent.get("threadId"))


if __name__ == "__main__":
    main()
