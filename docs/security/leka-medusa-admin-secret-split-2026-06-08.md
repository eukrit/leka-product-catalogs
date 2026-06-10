# Leka Medusa admin auth — dedicated secret split

**Date:** 2026-06-08
**Severity:** Medium (silent auth failure for all Leka admin scripts; no leak)
**Process Standard:** Rule 9 (secrets in Secret Manager), Rule 12 (secret hygiene)

## The trap

The Leka Medusa backend (`https://leka-medusa-backend-538978391890.asia-southeast1.run.app`,
admin login `admin@leka.studio`) authenticated using the **shared** Secret Manager
secrets `medusa-admin-email` / `medusa-admin-password` in project `ai-agents-go`.

Those shared secrets are also written to by **Areda** automation. As of 2026-06-08:

- `medusa-admin-email:latest` = `admin@aredaatelier.com` (Areda) — **wrong for Leka**.
- `medusa-admin-password:latest` had been set to Areda's password (v6), which
  **401s** against the Leka backend. Only the (later disabled) **v5** held the
  Leka password.

Result: every Leka script that fetched these secrets at `:latest` silently failed
admin auth. Areda already had its own dedicated `areda-medusa-admin-email` /
`areda-medusa-admin-password`, so the shared `medusa-admin-*` secrets were
ambiguous and unsafe for either brand.

## Fix (preferred option a — dedicated secrets, additive/non-destructive)

1. Created **`leka-medusa-admin-email`** = `admin@leka.studio` and
   **`leka-medusa-admin-password`** = the Leka password (copied from
   `medusa-admin-password` **v5**) in `ai-agents-go` (automatic replication,
   labels `brand=leka,kind=medusa-admin`).
2. Granted `roles/secretmanager.secretAccessor` on both new secrets to:
   - `538978391890-compute@developer.gserviceaccount.com` (Cloud Run runtime SA)
   - `538978391890@cloudbuild.gserviceaccount.com` (Cloud Build SA)
   - `claude@ai-agents-go.iam.gserviceaccount.com`
   (mirrors the shared secret's bindings.)
3. Migrated every Leka consumer to read the dedicated secrets:
   - **Python (10):** `scripts/apply_wisdom_enrichment.py`,
     `scripts/add_kidstramp_impact_protection.py`, `scripts/bootstrap_polysoft.py`,
     `scripts/backfill_eurotramp_photos_to_medusa.py`,
     `scripts/backfill_leka_project_images.py`,
     `scripts/hide_leka_project_lowres_products.py`,
     `scripts/medusa_create_toys_category.py`,
     `wisdom-catalog/enrich_furniture_pdf_images.py`,
     `wisdom-catalog/import_outdoor_play_to_medusa.py`,
     `wisdom-catalog/sync_po_sgd_to_medusa.py`.
   - **Cloud Build:** `cloudbuild.yaml` (service `--set-secrets`),
     `cloudbuild-debug-admin.yaml` (`availableSecrets`).
   - **Hints/docstrings:** `scripts/audit_eurotramp_images.ts`,
     `scripts/eurotramp_snapshot.py`, `vortex-catalog/crosscheck_bare_products.py`,
     `medusa-backend/start.sh`.
   - Env overrides `LEKA_MEDUSA_ADMIN_EMAIL` / `LEKA_MEDUSA_ADMIN_PASSWORD` still
     take precedence in scripts.

The shared `medusa-admin-*` secrets (including v5/v6/v7) were **left untouched** —
no version was disabled or destroyed. Areda is unaffected (its own
`areda-medusa-admin-*` secrets).

## Verification

| Backend | Secrets used | Result |
|---|---|---|
| Leka (`leka-medusa-backend`) | `leka-medusa-admin-email` + `leka-medusa-admin-password` | `POST /auth/user/emailpass` → **HTTP 200** (token) |
| Areda (`areda-medusa`) | `areda-medusa-admin-email` + `areda-medusa-admin-password` | `POST /auth/user/emailpass` → **HTTP 200** (token) |

`sha256(leka-medusa-admin-password:latest) == sha256(medusa-admin-password v5)`.

## Concurrent-session note

While this fix was applied, a separate `claude@` session independently applied the
fragile **option b**: it disabled `medusa-admin-password` v6 and added **v7** =
Leka password, so the shared secret's `:latest` authenticates Leka again. That
hack does **not** fix `medusa-admin-email:latest` (still Areda's) and re-breaks the
next time Areda pushes a new shared-password version. The dedicated-secret split
documented here supersedes it.

## Follow-ups (not done here)

- Once all consumers are confirmed on the dedicated secrets in production, consider
  removing the Leka entanglement from the shared `medusa-admin-*` secrets entirely
  (and have Areda stop writing Leka-affecting values). Not destructive-safe to do
  until both brands' deploys are verified.
- A redeploy of `leka-medusa-backend` refreshes its runtime `MEDUSA_ADMIN_PASSWORD`
  env to `leka-medusa-admin-password:latest` (cosmetic — the live admin password
  lives in the DB `provider_identity`, not env; see the 2026-06-06 rotation doc).
