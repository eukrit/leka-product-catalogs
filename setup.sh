#!/bin/bash
# setup.sh — Bootstrap a new project from the GO Corporation template
# Usage: ./setup.sh <project-name> [language]
#   language: "node" (default) or "python"
#
# Example:
#   ./setup.sh peak-mcp-service python
#   ./setup.sh n8n-webhook-gateway node

set -e

PROJECT_NAME="${1:?Usage: ./setup.sh <project-name> [node|python]}"
LANGUAGE="${2:-node}"
GITHUB_ORG="eukrit"
GCP_PROJECT="ai-agents-go"
GCP_REGION="asia-southeast1"
SERVICE_ACCOUNT="claude@ai-agents-go.iam.gserviceaccount.com"
CREDENTIALS_SOURCE="${CREDENTIALS_FOLDER:-/c/Users/eukri/OneDrive/Documents/Claude Code/Credentials Claude Code}"

echo "=== GO Corporation Project Setup ==="
echo "Project:  $PROJECT_NAME"
echo "Language: $LANGUAGE"
echo "GitHub:   $GITHUB_ORG/$PROJECT_NAME"
echo "GCP:      $GCP_PROJECT ($GCP_REGION)"
echo ""

# =============================================
# LANGUAGE SETUP
# =============================================
if [ "$LANGUAGE" = "python" ]; then
  echo "--- Configuring for Python ---"
  # Swap Dockerfile
  rm -f Dockerfile
  mv Dockerfile.python Dockerfile
  # Set up Python files
  mv requirements.txt.example requirements.txt
  mv src/main.py.example src/main.py
  rm -f src/index.js package.json
  # Update CLAUDE.md language
  sed -i "s/\[node|python\]/python/g" CLAUDE.md
  echo "[OK] Python project configured"
else
  echo "--- Configuring for Node.js ---"
  # Clean up Python files
  rm -f Dockerfile.python requirements.txt.example src/main.py.example
  sed -i "s/\[node|python\]/node/g" CLAUDE.md
  echo "[OK] Node.js project configured"
fi

# =============================================
# REPLACE PLACEHOLDERS (all known values prefilled)
# =============================================
echo ""
echo "--- Replacing placeholders ---"

# CLAUDE.md
sed -i "s/\[PROJECT_NAME\]/$PROJECT_NAME/g" CLAUDE.md

# manifest.example.json
sed -i "s/\[PROJECT_NAME\]/$PROJECT_NAME/g" manifest.example.json
sed -i "s/\[SERVICE_NAME\]/$PROJECT_NAME/g" manifest.example.json
sed -i "s|__LOCAL_PATH__|$(pwd)|g" manifest.example.json 2>/dev/null || true

# cloudbuild.yaml
sed -i "s/your-service-name/$PROJECT_NAME/g" cloudbuild.yaml

# package.json (Node.js only)
[ -f "package.json" ] && sed -i "s/goco-project-template/$PROJECT_NAME/g" package.json

# README
sed -i "s/goco-project-template/$PROJECT_NAME/g" README.md

# Summary.html
sed -i "s/\[PROJECT_NAME\]/$PROJECT_NAME/g" docs/Summary.html
[ "$LANGUAGE" = "python" ] && sed -i "s/Node.js 20/Python 3.11/g" docs/Summary.html

echo "[OK] All placeholders replaced"

# =============================================
# CREDENTIAL SETUP
# =============================================
echo ""
echo "--- Setting up credentials ---"

# Create manifest.json from example
cp manifest.example.json manifest.json
echo "[OK] Created manifest.json"

# Create .env from .env.example
if [ -f ".env.example" ]; then
  cp .env.example .env
  echo "[OK] Created .env from .env.example"
fi

# Copy credential files for local development
echo ""
echo "--- Copying credential files ---"
mkdir -p credentials

if [ -d "$CREDENTIALS_SOURCE" ]; then
  for FILE in "ai-agents-go-4c81b70995db.json" \
              "client_secret_538978391890-2ol1mrglnelng580ldvj5fi4tkrliqhf.apps.googleusercontent.com.json" \
              "xero_tokens.json" \
              "token_oauth.json" \
              "token_gmail_settings.json"; do
    if [ -f "$CREDENTIALS_SOURCE/$FILE" ]; then
      cp "$CREDENTIALS_SOURCE/$FILE" "credentials/$FILE"
      echo "  [OK] $FILE"
    fi
  done
else
  echo "[WARN] Credentials folder not found: $CREDENTIALS_SOURCE"
  echo "       Manually copy credential files to credentials/"
fi

# Verify .gitignore
if grep -q "credentials/" .gitignore 2>/dev/null; then
  echo "[OK] .gitignore blocks credentials/"
else
  echo "credentials/" >> .gitignore
fi

# =============================================
# GIT INIT
# =============================================
echo ""
if [ ! -d ".git" ]; then
  git init -b main
  git add -A
  git commit -m "chore: bootstrap $PROJECT_NAME from template ($LANGUAGE)"
  echo "[OK] Git initialized on main branch"
fi

# =============================================
# SUMMARY
# =============================================
echo ""
echo "=========================================="
echo "  Setup Complete: $PROJECT_NAME"
echo "=========================================="
echo ""
echo "  Language:    $LANGUAGE"
echo "  GCP Project: $GCP_PROJECT"
echo "  Region:      $GCP_REGION"
echo "  Service Acct: $SERVICE_ACCOUNT"
echo ""
echo "  credentials/ contents:"
ls credentials/ 2>/dev/null | sed 's/^/    /' || echo "    (empty)"
echo ""
echo "  Next steps:"
echo "    1. Populate .env (pick one):"
echo "       a) bash \"$CREDENTIALS_SOURCE/Templates/init-env.sh\" .   # auto-populate from Credentials folder"
echo "       b) ./scripts/load-secrets.sh $GCP_PROJECT                # pull from GCP Secret Manager"
if [ "$LANGUAGE" = "python" ]; then
echo "    2. Edit src/main.py with your service logic"
echo "    3. pip install -r requirements.txt"
else
echo "    2. Edit src/index.js with your service logic"
echo "    3. npm install"
fi
echo "    4. ./verify.sh"
echo "    5. git remote add origin https://github.com/$GITHUB_ORG/$PROJECT_NAME.git"
echo "    6. git push -u origin main"
echo ""
