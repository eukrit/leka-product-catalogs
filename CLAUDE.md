# leka-product-catalogs

## Project Identity
- Project: leka-product-catalogs
- Owner: Eukrit / GO Corporation Co., Ltd.
- Notion Dashboard: https://www.notion.so/gocorp/Coding-Project-Dashboard-Claude-32c82cea8bb080f1bbd7f26770ae9e80
- GitHub Repo: https://github.com/eukrit/leka-product-catalogs
- GCP Project ID: ai-agents-go
- GCP Project Number: 538978391890
- Cloud Run Services: leka-medusa-backend (Medusa v2), leka-medusa-storefront (Next.js)
- Region: asia-southeast1
- Service Account: claude@ai-agents-go.iam.gserviceaccount.com
- Artifact Registry: asia-southeast1-docker.pkg.dev/ai-agents-go/leka-product-catalogs
- Backend: Medusa Commerce v2 (TypeScript/Node.js)
- Frontend: Next.js 15 (React/TypeScript)
- Database: Cloud SQL PostgreSQL 15
- Cache: Memorystore Redis

## What This Project Does
Multi-brand product catalog and e-commerce system powered by Medusa Commerce v2, hosted on GCP. Each brand is a Medusa Sales Channel with its own product set, pricing, and storefront. Features: product browsing, search, filtering, cart, checkout, order management, and admin dashboard. All catalogs use the **Leka Design System**.

## Related Repos
- **accounting-automation** (master) — Peak API, Xero, MCP server → `eukrit/accounting-automation`
- **business-automation** (main) — ERP gateway, shared libs, dashboard → `eukrit/business-automation`
- **areda-product-catalogs** (main) — Areda brand catalog → `eukrit/areda-product-catalogs`
- Credential files → use `Credentials Claude Code` folder + GCP Secret Manager

## MANDATORY: After every code change
1. `git add` + `git commit` + `git push origin main`
2. Cloud Build auto-deploys to Cloud Run — verify build succeeds
3. Update `eukrit/business-automation` dashboard (`docs/index.html`) if architecture changes
4. Update CHANGELOG.md with version entry

## Credentials & Secrets

### Centralized Credentials Folder
All API credentials are stored in:
```
C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code
```
Master instructions: `Credentials Claude Code/Instructions/API Access Master Instructions.txt`

### Credential Loading Rules
1. **Local development**: Load from `.env` file (gitignored) or `credentials/` folder
2. **CI/CD (Cloud Build)**: Load from GCP Secret Manager
3. **MCP connectors**: Auth handled by the MCP platform — no local credentials needed
4. **NEVER hardcode** credentials in source code or committed files
5. **NEVER commit** `.env`, `manifest.json`, `credentials/`, `*.key`, `*.pem`, token files

### GCP Secret Manager (CI/CD)
| Secret Name | Source File | Used By |
|---|---|---|
| `peak-api-token` | Peak API Credential.txt | Peak API calls |
| `xero-client-secret` | Xero Credentials.txt | Xero OAuth refresh |
| `notion-api-key` | NOTION_API_KEY.md | Notion API |
| `slack-bot-token` | Slack OAuth.txt | Slack notifications |
| `figma-token` | Figma Token.txt | Figma API |
| `n8n-webhook-key` | n8n config | n8n webhook auth |

### Credential File References
| File | Location | Purpose |
|---|---|---|
| `ai-agents-go-4c81b70995db.json` | Credentials folder | GCP service account key |
| `client_secret_538978391890-*.json` | Credentials folder | GCP OAuth client |
| `xero_tokens.json` | Credentials folder | Xero OAuth tokens (rotating) |
| `token_oauth.json` | Credentials folder | Google OAuth token |
| `token_gmail_settings.json` | Credentials folder | Gmail OAuth token |

## GCP Infrastructure
| Resource | Value |
|----------|-------|
| GCP Project | `ai-agents-go` |
| Service Account | `claude@ai-agents-go.iam.gserviceaccount.com` |
| Firestore | Native mode, database `leka-product-catalogs` (asia-southeast1) |
| GCS Bucket | `ai-agents-go-documents` (public read, uniform bucket-level access) |
| Cloud Build | GitHub connection `github-eukrit` (us-central1) |
| Cloud Run | asia-southeast1 region |

## Design System — Leka
All catalogs use the **Leka Design System** (Figma: `ER6pbDqrJ4Uo9FuldnYBfm`):

| Token | Value |
|-------|-------|
| Font | Manrope (400-800) |
| Purple | `#8003FF` |
| Navy | `#182557` |
| Cream | `#FFF9E6` |
| Magenta | `#970260` |
| Amber | `#FFA900` |
| Red-Orange | `#E54822` |
| Card radius | 16px |
| Button radius | 8px |
| Badge radius | 9999px (pill) |
| Shadow | `0px 2px 8px rgba(24,37,87,0.08)` |

## Active Brands

| Brand | Subfolder | Cloud Run URL | Products | Source |
|-------|-----------|---------------|----------|--------|
| Wisdom | `wisdom-catalog/` | TBD | 5,071 | Excel catalogs |
| Vinci Play | `vinci-catalog/` | https://catalogs.leka.studio | 1,172 | vinci-play.com scrape |

## Project Structure (enforced)
```
leka-product-catalogs/
├── CLAUDE.md                    # This file — build rules
├── CHANGELOG.md                 # Version history (all brands)
├── README.md                    # Quick start guide
├── Dockerfile                   # Root service container
├── cloudbuild.yaml              # GCP Cloud Build pipeline
├── requirements.txt             # Python dependencies
├── verify.sh                    # Post-build verification
├── manifest.example.json        # GCP config template
├── .gitignore
├── src/
│   └── main.py                  # Root health/index service
├── scripts/                     # Utility scripts
├── docs/                        # HTML deployment summaries
│   └── <brand>.html
├── shared/                      # Shared multi-brand utilities
│   ├── __init__.py
│   ├── base_importer.py         # Common import logic (batch_write, parsing)
│   ├── category_mapper.py       # Unified category taxonomy
│   └── image_pipeline.py        # Shared PDF extraction & GCS upload
├── <brand-name>/                # One folder per brand
│   ├── import_to_firestore.py   # Data import pipeline
│   ├── export_to_json.py        # Static JSON export
│   ├── extract_images.py        # PDF image extraction
│   ├── firestore_schema.json    # Schema documentation
│   ├── DEPLOYMENT_LOG.md        # Brand-specific deploy log
│   └── web-app/                 # Cloud Run web app
│       ├── Dockerfile
│       ├── cloudbuild.yaml
│       ├── server.py
│       └── public/
│           ├── index.html
│           ├── styles.css
│           ├── app.js
│           └── data/            # Static JSON product data
└── firestore/
    ├── firestore.rules
    └── firestore.indexes.json
```

## Build Rules & Housekeeping

### After Every Build / Deployment
1. Update `<brand>/DEPLOYMENT_LOG.md` — dated entry with changes, counts, URLs
2. Generate `docs/<brand>.html` — HTML summary page (Leka Design System styling)
3. Update `CHANGELOG.md` — add version entry under brand heading
4. Commit and push to GitHub
5. Do NOT sync to GitHub: `extracted_images/`, `*Slack Downloads/`, `__pycache__/`, `.env`

### Firestore Collections (Multi-Brand Architecture)
All collections live in the **`leka-product-catalogs`** database (not `(default)`).
All `firestore.Client()` calls must include `database="leka-product-catalogs"`.

- `products_{brand}` — per-brand product documents (e.g. `products_wisdom`, `products_vinci`)
- `product_categories_{brand}` — per-brand category lookup
- `leka_vendor_quotations` — vendor quotations with `vendor_name` and `brand` fields

### Image Pipeline
1. Download catalog PDFs from source (Slack/email/Drive)
2. Extract images with PyMuPDF (`extract_images.py`)
3. Convert non-browser formats (`.jpx` → `.jpeg`) with Pillow
4. Upload to GCS: `gs://ai-agents-go-documents/product-images/<brand>/catalog/`
5. Map to Firestore product `images[]` array
6. GCS bucket uses **uniform bucket-level access** — do NOT call `blob.make_public()`

## Safety Rules
- NEVER commit credentials, API keys, or tokens
- NEVER auto-merge to main without test pass
- ALWAYS run verify.sh before marking build complete
- ALWAYS load credentials from .env or Secret Manager — never hardcode

## Commit Convention
- feat(scope): description
- fix(scope): description
- docs(scope): description
- chore(scope): description
- test(scope): description

## Branch Strategy
- main → production (auto-deploys to GCP)
- dev/[feature] → development (build only)

## Testing
Run `./verify.sh` for full verification suite.
Minimum pass rate: 100% on critical path, 80% overall.

## Tech Stack
- Runtime: Python 3.11
- Web Framework: Flask (serving static catalog apps)
- Infrastructure: GCP Cloud Run + Cloud Build
- Database: Firestore (Native mode)
- Storage: GCS (`ai-agents-go-documents`)
- CI/CD: GitHub → GCP Cloud Build trigger
- Automation: n8n (gocorp.app.n8n.cloud)
- Docs: Notion
- Design: Leka Design System (Figma)

## Dependencies
```
flask
gunicorn
pandas
openpyxl
pymupdf
Pillow
google-cloud-firestore
google-cloud-storage
```

---

## Claude Process Standards (MANDATORY)

Full reference: `Credentials Claude Code/Instructions/Claude Process Standards.md`

1. **Always maintain a todo list** — use `TodoWrite` for any task with >1 step or that edits files; mark items done immediately.
2. **Always update a build log** — append a dated, semver entry to `BUILD_LOG.md` (or existing `CHANGELOG.md`) for every build/version: version, date (YYYY-MM-DD), summary, files changed, outcome.
3. **Plan in batches; run them as one chained autonomous pass** — group todos into batches, surface the plan once, then execute every batch back-to-back in a single run. No turn-taking between todos or batches. Run long work with `run_in_background: true`; parallelize independent tool calls. Only stop for true blockers: destructive/unauthorized actions, missing credentials, genuine ambiguity, unrecoverable external errors, or explicit user confirmation request.
4. **Always update `build-summary.html`** at the project root for every build/version (template: `Credentials Claude Code/Instructions/build-summary.template.html`). Include version, date, status badge, and links to log + commit.
5. **Always commit and push — verify repo mapping first** — run `git remote -v` and confirm the remote repo name matches the local folder name (per the Code Sync Rules in the root `CLAUDE.md`). If mismatch (e.g. still pointing at `goco-project-template`), STOP and ask the user. Never push to the wrong repo.
