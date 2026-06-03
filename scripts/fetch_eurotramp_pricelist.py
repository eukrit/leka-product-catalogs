"""Download Eurotramp price-list attachments from Gmail into the repo.

Eurotramp emails their price lists (PDF + Excel) as attachments. The MCP Gmail
connector cannot stream attachment bytes, so we pull them directly via the Gmail
API using the ai-agents-go service account with domain-wide delegation (DWD),
impersonating the mailbox that received each message.

Targets (see plan check-our-eurotramp-pricelist-jolly-muffin.md):
  * 2026 (1E) Kids Tramp + BounceCloud list  — msg 19c2d7a2bb37a161,
    mailbox eukrit@parkandgarden.com
  * 2025 Production Performance Series list   — thread/query in niwat@goco.bz

Files land in data/scraped/eurotramp/pricelists/.

Usage:
    # default: pull both known targets
    python scripts/fetch_eurotramp_pricelist.py

    # ad-hoc: any mailbox + Gmail query
    python scripts/fetch_eurotramp_pricelist.py \
        --mailbox niwat@goco.bz --query 'from:eurotramp.com has:attachment filename:xlsx'

DWD note: the SA has DWD on the goco.bz domain (used by the Gmail Router). Other
domains (e.g. parkandgarden.com) may not be delegated — if a target 403s, the
script reports it and you can save that one attachment manually from Gmail.
"""
from __future__ import annotations

import argparse
import base64
import logging
import os
import re
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "scraped" / "eurotramp" / "pricelists"

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Default SA key (DWD-enabled on goco.bz). Override with GOOGLE_APPLICATION_CREDENTIALS.
DEFAULT_SA_KEY = Path(
    r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code"
    r"\GCP Credentials\ai-agents-go-claude.json"
)

# Known targets: (mailbox to impersonate, Gmail search query, label for logs).
DEFAULT_TARGETS = [
    (
        "eukrit@parkandgarden.com",
        'from:eurotramp.com subject:"price list" has:attachment newer_than:1y',
        "2026 (1E) Kids Tramp + BounceCloud",
    ),
    (
        "niwat@goco.bz",
        'from:eurotramp.com "price list" has:attachment',
        "Production Performance Series",
    ),
]

# Attachment filename/MIME filter — keep spreadsheets and PDFs only.
KEEP_EXT = (".xlsx", ".xls", ".pdf", ".csv")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("eurotramp_pricelist")


def gmail_service(sa_key: Path, mailbox: str):
    creds = service_account.Credentials.from_service_account_file(
        str(sa_key), scopes=SCOPES, subject=mailbox
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._ +()-]", "_", name).strip()


def _iter_parts(part):
    """Yield every part in a message payload tree (depth-first)."""
    if not part:
        return
    yield part
    for sub in part.get("parts", []) or []:
        yield from _iter_parts(sub)


def download_from_message(svc, mailbox: str, msg_id: str) -> list[Path]:
    saved: list[Path] = []
    msg = svc.users().messages().get(userId="me", id=msg_id, format="full").execute()
    payload = msg.get("payload", {})
    for part in _iter_parts(payload):
        filename = part.get("filename") or ""
        if not filename:
            continue
        if not filename.lower().endswith(KEEP_EXT):
            continue
        body = part.get("body", {})
        data = body.get("data")
        att_id = body.get("attachmentId")
        if not data and att_id:
            att = (
                svc.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=msg_id, id=att_id)
                .execute()
            )
            data = att.get("data")
        if not data:
            continue
        raw = base64.urlsafe_b64decode(data.encode("utf-8"))
        out_path = OUT_DIR / _safe_name(filename)
        # If two messages share a filename, suffix with the message id tail.
        if out_path.exists() and out_path.read_bytes() != raw:
            stem, ext = os.path.splitext(out_path.name)
            out_path = OUT_DIR / f"{stem} [{msg_id[-6:]}]{ext}"
        out_path.write_bytes(raw)
        log.info("  saved %s (%.1f KB)", out_path.name, len(raw) / 1024)
        saved.append(out_path)
    return saved


def run_target(sa_key: Path, mailbox: str, query: str, label: str) -> list[Path]:
    log.info("[%s] mailbox=%s query=%s", label, mailbox, query)
    try:
        svc = gmail_service(sa_key, mailbox)
        resp = svc.users().messages().list(userId="me", q=query, maxResults=25).execute()
    except HttpError as e:
        log.error("[%s] Gmail API error for %s: %s", label, mailbox, e)
        log.error("  -> DWD may not be delegated for this domain; save this one manually.")
        return []
    except Exception as e:  # noqa: BLE001 — surface auth/delegation failures clearly
        log.error("[%s] auth/delegation failed for %s: %s", label, mailbox, e)
        return []

    messages = resp.get("messages", [])
    log.info("[%s] %d matching message(s)", label, len(messages))
    saved: list[Path] = []
    for m in messages:
        try:
            saved.extend(download_from_message(svc, mailbox, m["id"]))
        except HttpError as e:
            log.error("[%s] failed on message %s: %s", label, m["id"], e)
    return saved


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sa-key", type=Path,
                    default=Path(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")) or DEFAULT_SA_KEY)
    ap.add_argument("--mailbox", help="Impersonate this mailbox (ad-hoc mode).")
    ap.add_argument("--query", help="Gmail search query (ad-hoc mode).")
    ap.add_argument("--label", default="ad-hoc")
    args = ap.parse_args()

    sa_key = args.sa_key if args.sa_key and Path(args.sa_key).is_file() else DEFAULT_SA_KEY
    if not sa_key.is_file():
        raise SystemExit(f"SA key not found: {sa_key}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.mailbox and args.query:
        targets = [(args.mailbox, args.query, args.label)]
    else:
        targets = DEFAULT_TARGETS

    all_saved: list[Path] = []
    for mailbox, query, label in targets:
        all_saved.extend(run_target(sa_key, mailbox, query, label))

    log.info("Done. %d file(s) saved to %s", len(all_saved), OUT_DIR)
    for p in all_saved:
        log.info("  - %s", p.relative_to(REPO_ROOT))
    if not all_saved:
        log.warning("No attachments downloaded — check DWD delegation / queries above.")


if __name__ == "__main__":
    main()
