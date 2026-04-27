#!/usr/bin/env bash
# check-ci-status.sh — CI/CD gate. Polls Cloud Build + GitHub Actions for a
# specific commit and returns once everything is green, or aborts on failure.
#
# Used by auto-commit-and-merge.sh between push and admin-merge so a failing
# build cannot be silently shipped.
#
# Usage:
#   ./scripts/check-ci-status.sh [<commit-sha>] [--max-wait <seconds>] [--poll <seconds>] [--allow-no-checks]
#
# Defaults:
#   commit-sha   = HEAD
#   --max-wait   = 600  (10 minutes)
#   --poll       = 10   (seconds between polls)
#   --allow-no-checks present → exit 0 if no Cloud Build + no GitHub Actions
#                              run is found for the commit (default: exit 0
#                              with a warning, since some projects have no CI).
#
# Exit codes:
#   0  = all checks succeeded (or none configured + --allow-no-checks)
#   1  = at least one check failed
#   2  = checks still in progress after --max-wait (timeout)
#   3  = upstream tooling (gh / gcloud) error
#
# Required tools: gh (GitHub CLI), gcloud (optional — skipped if absent).

set -uo pipefail

SHA=""
MAX_WAIT=600
POLL=10
ALLOW_NO_CHECKS=1   # default-on: most projects don't have remote CI, that's fine

while [ $# -gt 0 ]; do
  case "$1" in
    --max-wait) MAX_WAIT="$2"; shift 2 ;;
    --poll)     POLL="$2"; shift 2 ;;
    --allow-no-checks) ALLOW_NO_CHECKS=1; shift ;;
    --strict)   ALLOW_NO_CHECKS=0; shift ;;
    -h|--help)  sed -n '2,30p' "$0"; exit 0 ;;
    *)          [ -z "$SHA" ] && { SHA="$1"; shift; } || { echo "[ci-gate] unknown arg: $1" >&2; exit 3; } ;;
  esac
done

[ -z "$SHA" ] && SHA=$(git rev-parse HEAD 2>/dev/null || echo "")
if [ -z "$SHA" ]; then
  echo "[ci-gate] could not resolve commit sha." >&2
  exit 3
fi
SHORT_SHA=$(echo "$SHA" | cut -c1-12)

REMOTE_URL=$(git config --get remote.origin.url 2>/dev/null || echo "")
REPO_SLUG=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[/:]([^/]+/[^/.]+)(\.git)?$|\1|; t; s|.*||')

echo "[ci-gate] commit=${SHORT_SHA} repo=${REPO_SLUG:-<none>} max_wait=${MAX_WAIT}s poll=${POLL}s"

# ---- Probes ------------------------------------------------------------

probe_gh_runs() {
  # Returns: "<status>|<conclusion>|<url>" lines for runs matching $SHA, or empty.
  command -v gh >/dev/null 2>&1 || return 0
  [ -n "$REPO_SLUG" ] || return 0
  gh run list --repo "$REPO_SLUG" --commit "$SHA" --limit 20 \
      --json status,conclusion,url,name 2>/dev/null \
    | python -c "import sys,json
try:
    rows=json.load(sys.stdin)
except Exception:
    sys.exit(0)
for r in rows:
    print(f\"{r.get('status','')}|{r.get('conclusion','') or ''}|{r.get('url','')}|{r.get('name','')}\")" 2>/dev/null
}

probe_gcb_builds() {
  # Returns: "<status>|<id>|<logUrl>" lines for Cloud Build runs of $SHA, or empty.
  command -v gcloud >/dev/null 2>&1 || return 0
  gcloud builds list \
      --filter="substitutions.COMMIT_SHA=${SHA} OR sourceProvenance.resolvedRepoSource.commitSha=${SHA}" \
      --format="value(status,id,logUrl)" \
      --limit=10 2>/dev/null \
    | awk -F'\t' 'NF>0 {print $1"|"$2"|"$3}'
}

# Status conventions:
#   GitHub Actions: status in {queued, in_progress, completed}; conclusion in {success, failure, cancelled, ...}
#   Cloud Build:    status in {QUEUED, WORKING, SUCCESS, FAILURE, INTERNAL_ERROR, TIMEOUT, CANCELLED}

START=$(date +%s)
while :; do
  GH_OUT=$(probe_gh_runs)
  GCB_OUT=$(probe_gcb_builds)

  PENDING=0; FAILED=0; SUCCEEDED=0; TOTAL=0; FAIL_URLS=""

  while IFS='|' read -r status conclusion url name; do
    [ -z "$status" ] && continue
    TOTAL=$((TOTAL+1))
    if [ "$status" != "completed" ]; then
      PENDING=$((PENDING+1))
    elif [ "$conclusion" = "success" ]; then
      SUCCEEDED=$((SUCCEEDED+1))
    else
      FAILED=$((FAILED+1)); FAIL_URLS="${FAIL_URLS}\n  - GH ${name}: ${url} (${conclusion})"
    fi
  done <<< "$GH_OUT"

  while IFS='|' read -r status id url; do
    [ -z "$status" ] && continue
    TOTAL=$((TOTAL+1))
    case "$status" in
      QUEUED|WORKING|PENDING) PENDING=$((PENDING+1)) ;;
      SUCCESS)                SUCCEEDED=$((SUCCEEDED+1)) ;;
      *)                      FAILED=$((FAILED+1)); FAIL_URLS="${FAIL_URLS}\n  - GCB ${id}: ${url:-<no-url>} (${status})" ;;
    esac
  done <<< "$GCB_OUT"

  ELAPSED=$(( $(date +%s) - START ))

  if [ "$TOTAL" -eq 0 ]; then
    if [ "$ALLOW_NO_CHECKS" -eq 1 ]; then
      echo "[ci-gate] no CI runs found for ${SHORT_SHA} — assuming OK (use --strict to fail)."
      exit 0
    else
      if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
        echo "[ci-gate] timeout: no CI runs registered for ${SHORT_SHA} after ${MAX_WAIT}s." >&2
        exit 2
      fi
      echo "[ci-gate] no CI runs yet for ${SHORT_SHA} — waiting ${POLL}s (elapsed ${ELAPSED}s)..."
      sleep "$POLL"; continue
    fi
  fi

  if [ "$FAILED" -gt 0 ]; then
    echo "[ci-gate] FAILED — ${FAILED}/${TOTAL} check(s) failed for ${SHORT_SHA}." >&2
    printf "${FAIL_URLS}\n" >&2
    exit 1
  fi

  if [ "$PENDING" -eq 0 ]; then
    echo "[ci-gate] all checks green for ${SHORT_SHA} (${SUCCEEDED}/${TOTAL})."
    exit 0
  fi

  if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
    echo "[ci-gate] timeout: ${PENDING}/${TOTAL} check(s) still in progress for ${SHORT_SHA} after ${MAX_WAIT}s." >&2
    exit 2
  fi

  echo "[ci-gate] ${SUCCEEDED}/${TOTAL} green, ${PENDING} pending — waiting ${POLL}s (elapsed ${ELAPSED}s)..."
  sleep "$POLL"
done
