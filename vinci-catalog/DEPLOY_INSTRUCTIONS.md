# Vinci Play Catalog — Deploy Instructions

## Resume Session

Branch: `claude/project-overview-gNRJV`

```bash
git fetch origin claude/project-overview-gNRJV
git checkout claude/project-overview-gNRJV
```

## Deploy to Cloud Run

The previous deploy failed because Cloud Build ran in `asia-south` region.
Fix: specify `--default-build-region` or use `us-central1` for the build.

### Option A: Deploy with explicit build region (recommended)

```bash
cd vinci-catalog/web-app
gcloud run deploy vinci-catalog \
  --source . \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --project ai-agents-go \
  --default-build-region us-central1
```

### Option B: If Option A fails, build and push manually

```bash
# 1. Build the image
cd vinci-catalog/web-app
gcloud builds submit --tag gcr.io/ai-agents-go/vinci-catalog --project ai-agents-go

# 2. Deploy the image
gcloud run deploy vinci-catalog \
  --image gcr.io/ai-agents-go/vinci-catalog \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --project ai-agents-go \
  --memory 256Mi \
  --max-instances 3
```

### Option C: Deploy via Artifact Registry (if gcr.io is blocked)

```bash
# 1. Build
cd vinci-catalog/web-app
gcloud builds submit \
  --tag asia-southeast1-docker.pkg.dev/ai-agents-go/leka-product-catalogs/vinci-catalog \
  --project ai-agents-go \
  --region us-central1

# 2. Deploy
gcloud run deploy vinci-catalog \
  --image asia-southeast1-docker.pkg.dev/ai-agents-go/leka-product-catalogs/vinci-catalog \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --project ai-agents-go
```

## Expected Output

```
Service [vinci-catalog] revision [...] has been deployed
Service URL: https://vinci-catalog-xxxxxxxxxx-as.a.run.app
```

## After Deploy

1. Visit the URL to verify the catalog loads
2. Share the URL back — CLAUDE.md and DEPLOYMENT_LOG.md will be updated

## Full Scrape (optional — only 47 Spring products included now)

```bash
cd leka-product-catalogs
pip install requests beautifulsoup4
python vinci-catalog/scrape_catalog.py           # all 29 series
python vinci-catalog/scrape_catalog.py --resume  # if interrupted
```

Then redeploy to include all products.

## What's in This Branch

| Commit | Description |
|--------|-------------|
| `527271d` | Dockerfile + cloudbuild.yaml for Cloud Run |
| `5d9a3b8` | Web app (HTML/CSS/JS) + scraper fixes |
| `8b5f49c` | Correct series slugs for arena/jumpoo/steel+ |
| `445a40f` | Vinci Play brand: scraper + importer + schema |
| `615e129` | Multi-brand architecture (products_vinci collection) |
