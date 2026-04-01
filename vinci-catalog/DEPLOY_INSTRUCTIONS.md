# Vinci Play Catalog — Deploy Instructions

## Live URL
**https://vinci-catalog-538978391890.asia-southeast1.run.app/**

## Branch
`claude/project-overview-gNRJV`

---

## Remaining Tasks

### Task 1: Full Scrape (all 29 series, ~1,000+ products)
Currently only 47 Spring series products are live. Run the full scrape to get all products.

```bash
cd leka-product-catalogs
pip install requests beautifulsoup4
python vinci-catalog/scrape_catalog.py           # ~30-60 min
python vinci-catalog/scrape_catalog.py --resume  # if interrupted
```

### Task 2: Redeploy with Full Data
After scraping, redeploy to include all products.

```bash
cd vinci-catalog/web-app
gcloud run deploy vinci-catalog \
  --source . \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --project ai-agents-go
```

### Task 3: Import to Firestore
Import the scraped data into Firestore for API access and cross-brand queries.

```bash
python vinci-catalog/import_to_firestore.py --dry-run   # preview
python vinci-catalog/import_to_firestore.py              # write to Firestore
```

### Task 4: Update Root Service
Update `src/main.py` brands list and redeploy the root `leka-product-catalogs` service.

### Task 5: Merge to Main
Once all tasks are verified, merge `claude/project-overview-gNRJV` to `main`.

---

## Deploy Commands Reference

### Standard deploy (what worked)
```bash
cd vinci-catalog/web-app
gcloud run deploy vinci-catalog \
  --source . \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --project ai-agents-go
```

### Manual build + deploy (fallback)
```bash
cd vinci-catalog/web-app
gcloud builds submit --tag gcr.io/ai-agents-go/vinci-catalog --project ai-agents-go

gcloud run deploy vinci-catalog \
  --image gcr.io/ai-agents-go/vinci-catalog \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --project ai-agents-go \
  --memory 256Mi \
  --max-instances 3
```

### Via Artifact Registry
```bash
cd vinci-catalog/web-app
gcloud builds submit \
  --tag asia-southeast1-docker.pkg.dev/ai-agents-go/leka-product-catalogs/vinci-catalog \
  --project ai-agents-go

gcloud run deploy vinci-catalog \
  --image asia-southeast1-docker.pkg.dev/ai-agents-go/leka-product-catalogs/vinci-catalog \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --project ai-agents-go
```

---

## Commit History

| Commit | Description |
|--------|-------------|
| `5d38bda` | Deploy instructions + .dockerignore |
| `527271d` | Dockerfile + cloudbuild.yaml for Cloud Run |
| `5d9a3b8` | Web app (HTML/CSS/JS) + scraper fixes |
| `8b5f49c` | Correct series slugs for arena/jumpoo/steel+ |
| `445a40f` | Vinci Play brand: scraper + importer + schema |
| `615e129` | Multi-brand architecture (products_vinci collection) |
