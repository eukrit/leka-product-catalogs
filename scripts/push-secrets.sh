#!/bin/bash
# push-secrets.sh — Push local credential values to GCP Secret Manager
# Usage: ./scripts/push-secrets.sh [--project ai-agents-go]
#
# Run this ONCE to provision all secrets from the centralized Credentials folder.
# After this, Cloud Build and Cloud Run can access secrets natively.
# Requires: gcloud CLI authenticated with secretmanager.admin role.

set -e

PROJECT="${1:-ai-agents-go}"
CREDENTIALS_FOLDER="${CREDENTIALS_FOLDER:-$HOME/OneDrive/Documents/Claude Code/Credentials Claude Code}"

echo "=== Pushing secrets to GCP Secret Manager ==="
echo "Project: $PROJECT"
echo "Source:  $CREDENTIALS_FOLDER"
echo ""

create_or_update_secret() {
  local NAME="$1"
  local VALUE="$2"

  if [ -z "$VALUE" ]; then
    echo "[SKIP] $NAME — empty value"
    return
  fi

  # Create secret if it doesn't exist
  if ! gcloud secrets describe "$NAME" --project="$PROJECT" > /dev/null 2>&1; then
    gcloud secrets create "$NAME" --replication-policy=automatic --project="$PROJECT"
    echo "[NEW] Created secret: $NAME"
  fi

  # Add new version
  echo -n "$VALUE" | gcloud secrets versions add "$NAME" --data-file=- --project="$PROJECT"
  echo "[OK] $NAME — version added"
}

# Read values from credential files
echo "--- Reading credential files ---"

# Peak API
if [ -f "$CREDENTIALS_FOLDER/Peak API Credential.txt" ]; then
  echo "[INFO] Reading Peak API credentials..."
  # These need to be extracted manually from the file
  echo "[NOTE] Parse Peak API Credential.txt and set PEAK_USER_TOKEN, PEAK_CONNECT_KEY"
fi

# Xero
if [ -f "$CREDENTIALS_FOLDER/Xero Credentials.txt" ]; then
  echo "[INFO] Reading Xero credentials..."
  echo "[NOTE] Parse Xero Credentials.txt and set XERO_CLIENT_ID, XERO_CLIENT_SECRET"
fi

# Notion
if [ -f "$CREDENTIALS_FOLDER/NOTION_API_KEY.md" ]; then
  NOTION_KEY=$(grep -oP 'ntn_[a-zA-Z0-9]+' "$CREDENTIALS_FOLDER/NOTION_API_KEY.md" 2>/dev/null || echo "")
  create_or_update_secret "notion-api-key" "$NOTION_KEY"
fi

# Figma
if [ -f "$CREDENTIALS_FOLDER/Figma Token.txt" ]; then
  FIGMA_KEY=$(grep -oP 'figd_[a-zA-Z0-9_]+' "$CREDENTIALS_FOLDER/Figma Token.txt" 2>/dev/null || echo "")
  create_or_update_secret "figma-token" "$FIGMA_KEY"
fi

# Slack
if [ -f "$CREDENTIALS_FOLDER/Slack OAuth.txt" ]; then
  SLACK_TOKEN=$(grep -oP 'xoxb-[a-zA-Z0-9-]+' "$CREDENTIALS_FOLDER/Slack OAuth.txt" 2>/dev/null || echo "")
  create_or_update_secret "slack-bot-token" "$SLACK_TOKEN"
fi

echo ""
echo "--- Grant Cloud Build access to secrets ---"
CB_SA="${PROJECT}@cloudbuild.gserviceaccount.com"
for SECRET_NAME in peak-api-token peak-connect-key n8n-webhook-key xero-client-id xero-client-secret notion-api-key slack-bot-token slack-webhook-url figma-token; do
  if gcloud secrets describe "$SECRET_NAME" --project="$PROJECT" > /dev/null 2>&1; then
    gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
      --member="serviceAccount:$CB_SA" \
      --role="roles/secretmanager.secretAccessor" \
      --project="$PROJECT" \
      --quiet 2>/dev/null
    echo "[OK] Granted $CB_SA access to $SECRET_NAME"
  fi
done

# Also grant Cloud Run service account
CR_SA="claude@ai-agents-go.iam.gserviceaccount.com"
for SECRET_NAME in peak-api-token n8n-webhook-key notion-api-key slack-bot-token; do
  if gcloud secrets describe "$SECRET_NAME" --project="$PROJECT" > /dev/null 2>&1; then
    gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
      --member="serviceAccount:$CR_SA" \
      --role="roles/secretmanager.secretAccessor" \
      --project="$PROJECT" \
      --quiet 2>/dev/null
    echo "[OK] Granted $CR_SA access to $SECRET_NAME"
  fi
done

echo ""
echo "=== Done ==="
echo "Verify with: gcloud secrets list --project=$PROJECT"
