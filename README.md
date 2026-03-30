# leka-product-catalogs

Multi-brand product catalog system hosted on GCP. Each brand gets its own subfolder with a complete pipeline: data import, image extraction, Firestore storage, and Cloud Run web app — all using the **Leka Design System**.

## Quick Start

```bash
git clone https://github.com/eukrit/leka-product-catalogs.git
cd leka-product-catalogs
pip install -r requirements.txt
python src/main.py
```

## Project Structure
```
leka-product-catalogs/
├── CLAUDE.md                    # Build rules and credentials
├── CHANGELOG.md                 # Version history (all brands)
├── README.md                    # This file
├── Dockerfile                   # Root service container (Python 3.11)
├── cloudbuild.yaml              # GCP Cloud Build pipeline
├── requirements.txt             # Python dependencies
├── verify.sh                    # Post-build verification
├── manifest.example.json        # GCP config template
├── .gitignore
├── src/
│   └── main.py                  # Root health/index service
├── scripts/                     # Utility scripts
├── docs/                        # HTML deployment summaries
├── firestore/
│   ├── firestore.rules          # Firestore security rules
│   └── firestore.indexes.json   # Composite indexes
├── wisdom-catalog/              # Wisdom brand
│   ├── import_to_firestore.py
│   ├── export_to_json.py
│   ├── extract_images.py
│   ├── verify_data.py
│   ├── map_images_verified.py
│   ├── DEPLOYMENT_LOG.md
│   └── web-app/
│       └── public/data/         # Static JSON product data
└── <next-brand>/                # Future brands follow same structure
```

## GCP Infrastructure

| Resource | Value |
|----------|-------|
| GCP Project | `ai-agents-go` |
| Region | `asia-southeast1` |
| Cloud Run | Auto-deployed on push to `main` |
| Firestore | Native mode, default database |
| GCS Bucket | `ai-agents-go-documents` |
| Cloud Build | GitHub trigger via `github-eukrit` connection |

## Active Brands

| Brand | Products | Cloud Run |
|-------|----------|-----------|
| Wisdom | 5,071 | TBD |

## Design System — Leka

Font: **Manrope** | Purple: `#8003FF` | Navy: `#182557` | Cream: `#FFF9E6`

Figma: `https://www.figma.com/file/ER6pbDqrJ4Uo9FuldnYBfm`

## Development Workflow

1. Work on `dev/feature-name` branch
2. Run `./verify.sh` locally
3. Push → Cloud Build runs tests
4. Merge to `main` → auto-deploy to Cloud Run

## Credential Management

See [CLAUDE.md](CLAUDE.md) for full credential documentation. All secrets managed via GCP Secret Manager.

## Commit Convention
```
feat(scope): description    # new feature
fix(scope): description     # bug fix
docs(scope): description    # documentation
chore(scope): description   # config/infra
test(scope): description    # tests
```
