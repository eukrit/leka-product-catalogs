# Product Catalog Builder — Deployment Instructions

This repository hosts product catalogs for multiple vendor brands. Each brand gets its own subfolder with a self-contained pipeline: data import, image extraction, Firestore storage, and a Cloud Run web app using the Leka Design System.

## Architecture

```
product-catalogs/
├── CLAUDE.md                    # Build rules and housekeeping
├── CHANGELOG.md                 # Version history across all brands
├── VERSION                      # Current version
├── DEPLOYMENT_INSTRUCTIONS.md   # This file
├── docs/                        # HTML deployment summaries (auto-generated)
│   └── wisdom-catalog.html
├── wisdom-catalog/              # First brand
│   ├── import_to_firestore.py
│   ├── export_to_json.py
│   ├── extract_images.py
│   ├── firestore_schema.json
│   ├── DEPLOYMENT_LOG.md
│   └── web-app/
│       ├── Dockerfile
│       ├── cloudbuild.yaml
│       ├── server.py
│       └── public/
│           ├── index.html
│           ├── styles.css
│           ├── app.js
│           └── data/
└── <next-brand>/                # Future brands follow same structure
```

## GCP Infrastructure (shared)

| Resource | Value |
|----------|-------|
| GCP Project | `ai-agents-go` |
| Service Account | `claude@ai-agents-go.iam.gserviceaccount.com` |
| Credentials | `C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json` |
| Firestore | Native mode, default database |
| GCS Bucket | `ai-agents-go-documents` (public read) |
| Cloud Build | GitHub connection `github-eukrit` (us-central1) |
| Cloud Run | asia-southeast1 region |

## How to Build a New Brand Catalog

### Step 1: Create Brand Subfolder

```
mkdir <brand-name>/
```

### Step 2: Source Product Data

Download product data (xlsx/csv) from the relevant source:
- **Slack channel**: Use Slack Bot API with token from `Slack OAuth.txt`
- **Email attachments**: Use Gmail MCP
- **Google Drive**: Use Drive MCP or service account

Place source files in `<Brand> Slack Downloads/` (gitignored).

### Step 3: Create Firestore Import Script

Copy and adapt `wisdom-catalog/import_to_firestore.py`:

1. Update `DOWNLOADS_DIR` to point to new source files
2. Update `CATEGORY_MAP` for the brand's product code prefixes
3. Update `SUBCATEGORY_KEYWORDS` for product types
4. Update sheet names and column mappings to match the xlsx structure
5. Choose Firestore collection name: `products_<brand>` (or use the shared `products` collection with a `brand` field)

Key schema fields (consistent across brands):
```python
{
    "item_code": str,       # Unique product identifier
    "description": str,     # English product name
    "category": str,        # Auto-classified category
    "subcategory": str,     # Optional sub-classification
    "material": str,        # Primary material
    "dimensions": {         # Parsed from size strings
        "raw": str,
        "length_cm": float,
        "width_cm": float,
        "height_cm": float
    },
    "volume_cbm": float,    # Cubic meters
    "weight_kg": float,     # Kilograms
    "pricing": {
        "fob_usd": float,
        "currency": "USD",
        "price_date": str
    },
    "catalog_page": int,
    "catalog_source": str,
    "images": [],           # Populated in Step 5
    "brand": str,           # Brand identifier
}
```

### Step 4: Run Import

```bash
python <brand-name>/import_to_firestore.py
```

### Step 5: Extract & Upload Product Images

Copy and adapt `wisdom-catalog/extract_images.py`:

1. Update PDF file list and catalog names
2. Update product code regex patterns for the brand
3. Run extraction, conversion, GCS upload, and Firestore linking

```bash
python <brand-name>/extract_images.py
```

Images are stored at: `gs://ai-agents-go-documents/product-images/<brand>/catalog/`

### Step 6: Export Static JSON

Copy and adapt `wisdom-catalog/export_to_json.py`:

1. Update Firestore collection/query filters for the brand
2. Update output directory

```bash
python <brand-name>/export_to_json.py
```

### Step 7: Create Web App

Copy `wisdom-catalog/web-app/` and customize:

1. Update `index.html` — brand name, title
2. Update `styles.css` — brand colors (use Figma design system tokens)
3. Update `app.js` — category icons, colors
4. Update `Dockerfile`, `server.py` — paths

### Step 8: Deploy to Cloud Run

```bash
cd <brand-name>/web-app
gcloud run deploy <brand>-catalog \
  --source . \
  --project=ai-agents-go \
  --region=asia-southeast1 \
  --allow-unauthenticated \
  --port=8080 \
  --memory=256Mi \
  --max-instances=3
```

### Step 9: Set Up Cloud Build Trigger

```bash
# Add repo access if needed (GitHub App installation)
gcloud builds repositories create product-catalogs \
  --connection=github-eukrit \
  --region=us-central1 \
  --remote-uri=https://github.com/eukrit/product-catalogs.git

# Create trigger
gcloud alpha builds triggers create github \
  --name=<brand>-catalog-deploy \
  --repository=projects/ai-agents-go/locations/us-central1/connections/github-eukrit/repositories/product-catalogs \
  --branch-pattern='^main$' \
  --build-config=<brand-name>/web-app/cloudbuild.yaml \
  --region=us-central1 \
  --service-account=projects/ai-agents-go/serviceAccounts/538978391890-compute@developer.gserviceaccount.com \
  --project=ai-agents-go
```

### Step 10: Write Deployment Summary

After each build, write:
1. `<brand-name>/DEPLOYMENT_LOG.md` — detailed log
2. `docs/<brand-name>.html` — HTML summary page
3. Update `CHANGELOG.md` with version entry

## Design System

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

## Dependencies

```
pip install pandas openpyxl pymupdf Pillow google-cloud-firestore google-cloud-storage flask
```
