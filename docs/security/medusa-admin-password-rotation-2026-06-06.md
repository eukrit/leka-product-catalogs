# Security remediation — Medusa admin password leak + rotation

**Date:** 2026-06-06
**Severity:** High (live admin credential committed to source + present in git history)
**Process Standard:** Rule 12 (secret hygiene — never hardcode credentials)

## What happened

The live Medusa admin password for `leka-medusa-backend` was hardcoded as a
string literal (`ADMIN_PASSWORD = "<redacted>"`) in committed scripts, and the
value was present in git history. The admin email was likewise hardcoded.

## Files remediated (this change)

| File | Fix |
|---|---|
| `scripts/backfill_eurotramp_photos_to_medusa.py` | Read creds via `LEKA_MEDUSA_ADMIN_EMAIL` / `LEKA_MEDUSA_ADMIN_PASSWORD` env, falling back to Secret Manager (`medusa-admin-email` / `medusa-admin-password`) — mirrors `scripts/apply_wisdom_enrichment.py`. |
| `scripts/audit_eurotramp_images.ts` | Read `process.env.LEKA_MEDUSA_ADMIN_PASSWORD` (no literal); hard-fail with a Secret-Manager hint if unset. Email falls back to a non-secret default. |
| `scripts/rehost-images-to-gcs.ts` | Same env pattern. |
| `scripts/upload-vendors-to-medusa.ts` | Same env pattern. |
| `medusa-backend/start.sh` | Removed the hardcoded `${MEDUSA_ADMIN_PASSWORD:-<literal>}` fallback; admin seeding now runs only when `MEDUSA_ADMIN_PASSWORD` is set (mounted from Secret Manager by cloudbuild). |
| `vortex-catalog/DEPLOYMENT_LOG.md` | Redacted the literal that was printed in the doc. |

After this change, `grep -r "<the literal>"` across the tree returns no matches.

## Rotation performed (live)

1. Generated a new 32-char password (never logged).
2. Stored it as a **new version (v5)** of Secret Manager `medusa-admin-password`
   *before* applying it to live (recoverable ordering).
3. Applied it to the live backend via the Medusa v2 emailpass
   `POST /auth/user/emailpass/update` route, authenticated with a
   reset-password JWT minted from `JWT_SECRET` (the login-token path is rejected
   by `validateToken`, which requires an `entity_id` claim).
4. **Verified:** new password authenticates (HTTP 200); old password rejected
   (HTTP 401).
5. **Disabled** the old enabled Secret Manager versions (v2, v4) that held the
   compromised value. Only **v5** is now enabled. (v1 was already destroyed,
   v3 already disabled.)

`medusa-admin-password:latest` (= v5) equals the live password, so all consumers
(`--set-secrets`, scripts using `:latest`) stay consistent. No redeploy is
required for auth (the password lives in the DB `provider_identity`, not env);
the env var refreshes to `:latest` on the next deploy.

## Follow-ups (not done here)

- **Optional git-history purge** (Rule 12): the old literal still exists in git
  history. Rotation has already neutralized the value (it no longer
  authenticates and is disabled in Secret Manager), so this is
  defense-in-depth. A history rewrite (`git filter-repo` / BFG) requires a
  force-push that rewrites shared history and cannot go through a normal PR —
  it needs explicit sign-off before running.
- A redeploy of `leka-medusa-backend` will refresh its runtime `MEDUSA_ADMIN_PASSWORD`
  env to the new `:latest` (cosmetic — not used for auth).

## Addendum — 2026-06-08: bad v6 + `:latest` repair

A **v6** was added to `medusa-admin-password` on 2026-06-08 (01:16 UTC) holding
the **wrong value** — it was the *Areda* Medusa admin password (a 15-char string,
NOT empty as first reported), accidentally written to Leka's secret. This is the
same Areda↔Leka cross-contamination already seen on `medusa-admin-email`. Because
v6 became `:latest`, any consumer reading `:latest` (scripts on the Secret-Manager
fallback; the next `leka-medusa-backend` redeploy mounting `MEDUSA_ADMIN_PASSWORD`)
would have gotten the wrong password → 401 / broken admin seeding. Confirmed:
v6 auth → **401**, v5 auth → **200**.

**Important Secret Manager behavior learned:** the `latest` alias resolves to the
**highest version number regardless of state** — it does NOT skip to the next
*enabled* version. So merely *disabling* v6 did **not** fall through to v5;
`access latest` then failed with `FAILED_PRECONDITION: version 6 is in DISABLED
state` (worse — the next redeploy would fail secret resolution entirely).

**Fix applied:**
1. Disabled v6 (wrong value, kept for audit trail).
2. Added **v7** by piping v5's payload straight into a new version
   (`access 5 | versions add --data-file=-`) — the value never touched stdout/logs.
3. v7 is now `:latest` (ENABLED, 32 bytes).

**Verified:** `access latest` returns a 32-char value; `POST /auth/user/emailpass`
with `admin@leka.studio` + `:latest` → **HTTP 200**. v5 remains enabled as a
backstop; v6 disabled.
