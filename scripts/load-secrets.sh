#!/bin/bash
# load-secrets.sh — Pull secrets from GCP Secret Manager into local .env
# Usage: ./scripts/load-secrets.sh [--project ai-agents-go]
#
# This is the preferred way to populate local credentials.
# Requires: gcloud CLI authenticated with access to Secret Manager.

set -e

PROJECT="${1:-ai-agents-go}"
ENV_FILE=".env"

echo "=== Loading secrets from GCP Secret Manager ==="
echo "Project: $PROJECT"
echo "Target:  $ENV_FILE"
echo ""

# Start with the example template
if [ -f ".env.example" ]; then
  cp .env.example "$ENV_FILE"
  echo "[INFO] Created .env from .env.example"
else
  touch "$ENV_FILE"
fi

# Map: Secret Manager name → .env variable name
declare -A SECRETS
SECRETS=(
  ["peak-api-token"]="PEAK_USER_TOKEN"
  ["peak-connect-key"]="PEAK_CONNECT_KEY"
  ["n8n-webhook-key"]="N8N_WEBHOOK_KEY"
  ["xero-client-id"]="XERO_CLIENT_ID"
  ["xero-client-secret"]="XERO_CLIENT_SECRET"
  ["notion-api-key"]="NOTION_API_KEY"
  ["slack-bot-token"]="SLACK_BOT_TOKEN"
  ["slack-webhook-url"]="SLACK_WEBHOOK_URL"
  ["figma-token"]="FIGMA_TOKEN"
  ["google-ads-dev-token"]="GOOGLE_ADS_DEV_TOKEN"
  ["google-ads-refresh-token"]="GOOGLE_ADS_REFRESH_TOKEN"
)

LOADED=0
SKIPPED=0

for SECRET_NAME in "${!SECRETS[@]}"; do
  ENV_VAR="${SECRETS[$SECRET_NAME]}"
  VALUE=$(gcloud secrets versions access latest --secret="$SECRET_NAME" --project="$PROJECT" 2>/dev/null || echo "")

  if [ -n "$VALUE" ]; then
    # Replace the empty value in .env
    sed -i "s|^${ENV_VAR}=.*|${ENV_VAR}=${VALUE}|" "$ENV_FILE"
    echo "[OK] $SECRET_NAME → $ENV_VAR"
    LOADED=$((LOADED+1))
  else
    echo "[SKIP] $SECRET_NAME — not found or no access"
    SKIPPED=$((SKIPPED+1))
  fi
done

echo ""
echo "=== Done: $LOADED loaded, $SKIPPED skipped ==="
echo "Review $ENV_FILE and fill in any remaining values manually."
