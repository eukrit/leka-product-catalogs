# Cloud Build trigger setup — leka-product-catalogs + leka-website

**Status:** Manual one-time setup. Cannot be done from the CLI/gcloud because
GitHub repository connection requires an interactive OAuth handshake.

**Current state (2026-05-15):**
- Only **one** trigger exists in project `ai-agents-go`:
  `deploy-grand-stone-website` → `eukrit/grand-stone-website`.
- `eukrit/leka-product-catalogs` and `eukrit/leka-website` are **not connected**
  to Cloud Build. Every Medusa rebuild / storefront rebuild requires a manual
  `gcloud builds submit` (see runbook below).
- `eukrit/vendors` is also not connected (see `vendors/BUILD_LOG.md` v1.11.0).

## Why not via gcloud

`gcloud beta builds connections create github` requires an OAuth token from the
GitHub App that owns `eukrit/*`. The token can only be minted via the Cloud
Build console's "Connect repository" flow because the GitHub side prompts for
permission grant in the browser. This is a one-time per-repo cost.

## Setup (≈ 5 minutes per repo)

1. Open **Cloud Build → Triggers** in the GCP console (project
   `ai-agents-go`, region `global`):
   https://console.cloud.google.com/cloud-build/triggers?project=ai-agents-go

2. Click **CONNECT REPOSITORY** (top of the page) → **GitHub (1st gen)** →
   *Continue* → authenticate as the GitHub user that owns `eukrit/*`.

3. Select the repository to connect:
   - `eukrit/leka-product-catalogs`
   - `eukrit/leka-website`
   - `eukrit/vendors`
   …then *Connect*.

4. On the **Create a trigger** prompt that follows, fill in:

   ### For leka-product-catalogs (Medusa backend)
   | Field | Value |
   |---|---|
   | Name | `deploy-leka-medusa-backend` |
   | Event | Push to a branch |
   | Source repository | `eukrit/leka-product-catalogs` |
   | Branch | `^main$` |
   | Included files filter (glob) | `medusa-backend/**` `cloudbuild.yaml` `medusa-backend/Dockerfile` |
   | Configuration | Cloud Build configuration file (yaml or json) |
   | Location | Repository · `/cloudbuild.yaml` |
   | Service account | `claude@ai-agents-go.iam.gserviceaccount.com` |
   | Region | `global` |

   ### For leka-website (catalogs storefront)
   | Field | Value |
   |---|---|
   | Name | `deploy-leka-catalogs` |
   | Event | Push to a branch |
   | Source repository | `eukrit/leka-website` |
   | Branch | `^main$` |
   | Included files filter | `catalogs/**` `cloudbuild-catalogs.yaml` |
   | Configuration | Cloud Build configuration file (yaml or json) |
   | Location | Repository · `/cloudbuild-catalogs.yaml` |
   | Service account | `claude@ai-agents-go.iam.gserviceaccount.com` |
   | Region | `global` |

   ### For vendors (Rampline Drive sync image)
   | Field | Value |
   |---|---|
   | Name | `deploy-rampline-drive-sync` |
   | Event | Push to a branch |
   | Source repository | `eukrit/vendors` |
   | Branch | `^main$` |
   | Included files filter | `rampline-catalog/**` `cloudbuild-rampline-drive-sync.yaml` `rampline-catalog/Dockerfile.drive-sync` |
   | Configuration | Cloud Build configuration file (yaml or json) |
   | Location | Repository · `/cloudbuild-rampline-drive-sync.yaml` |
   | Service account | `claude@ai-agents-go.iam.gserviceaccount.com` |
   | Region | `global` |

5. *Create*. The trigger is now active. Subsequent `git push origin main`
   will rebuild + redeploy automatically.

## Manual-deploy runbook (until triggers are wired up)

### Medusa backend (leka-product-catalogs)
```powershell
cd C:\Users\eukri\OneDrive\Documents\Claude Code\leka-product-catalogs
gcloud builds submit `
  --config=cloudbuild.yaml `
  --substitutions=BRANCH_NAME=main,SHORT_SHA=$(git rev-parse --short=7 HEAD),_REGION=asia-southeast1,_AR_REPO=asia-southeast1-docker.pkg.dev/ai-agents-go/leka-product-catalogs `
  --project=ai-agents-go `
  --ignore-file=.gcloudignore `
  --machine-type=e2-highcpu-8
```

### Catalogs storefront (leka-website)
```powershell
cd C:\Users\eukri\OneDrive\Documents\Claude Code\leka-website
gcloud builds submit `
  --config=cloudbuild-catalogs.yaml `
  --substitutions=BRANCH_NAME=main,SHORT_SHA=$(git rev-parse --short=7 HEAD) `
  --project=ai-agents-go `
  --ignore-file=.gcloudignore
```

### Rampline Drive sync image (vendors)
```powershell
cd C:\Users\eukri\OneDrive\Documents\Claude Code\vendors
gcloud builds submit `
  --config=cloudbuild-rampline-drive-sync.yaml `
  --project=ai-agents-go `
  --ignore-file=.gcloudignore
```

## Verification after each trigger is created

```bash
gcloud builds triggers list --project=ai-agents-go \
  --format="table(name,github.name,filename,github.push.branch)" \
  | grep -E "leka-medusa|leka-catalogs|rampline-drive"
```

Expect three rows. After the next push to each repo, the first auto-build
should appear in `gcloud builds list --project=ai-agents-go --limit=5`.

## Notes

- `claude@ai-agents-go.iam.gserviceaccount.com` already has the IAM roles
  Cloud Build needs (`roles/cloudbuild.builds.builder`,
  `roles/run.admin`, `roles/iam.serviceAccountUser`,
  `roles/secretmanager.secretAccessor`). No extra IAM work required.
- Trigger creation does **not** trigger an initial build — the first push
  after creation does.
- If the GitHub App installation is missing the repos, edit the install at
  https://github.com/apps/google-cloud-build/installations/new and grant
  access to `eukrit/*`.
