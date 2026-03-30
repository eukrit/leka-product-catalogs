# goco-project-template

GO Corporation — Cloud Run project template with CI/CD, AI evaluation loop, and structured development workflow.

## Quick Start

### From Template
```bash
gh repo clone eukrit/goco-project-template my-new-project -- --template
cd my-new-project
chmod +x setup.sh verify.sh scripts/*.sh
./setup.sh my-new-project eukrit
```

### Manual Setup
```bash
git clone https://github.com/eukrit/goco-project-template.git my-new-project
cd my-new-project
chmod +x setup.sh verify.sh scripts/*.sh
./setup.sh my-new-project eukrit
```

## Project Structure
```
project-root/
├── manifest.json            # LOCAL ONLY — gitignored
├── manifest.example.json    # Committed template (ENV: and SECRET: refs only)
├── .env                     # LOCAL ONLY — gitignored (local dev fallback)
├── .env.example             # Committed template for .env
├── credentials/             # LOCAL ONLY — gitignored (symlinked credential files)
├── CLAUDE.md                # Claude Code session instructions + credential docs
├── CHANGELOG.md             # Auto-updated each build
├── cloudbuild.yaml          # GCP Cloud Build config (secrets from Secret Manager)
├── verify.sh                # Post-build verification (includes credential checks)
├── Dockerfile               # Cloud Run container
├── package.json             # Node.js dependencies
├── scripts/
│   ├── load-secrets.sh      # Pull secrets from GCP Secret Manager → .env
│   └── push-secrets.sh      # Push local credentials → GCP Secret Manager
├── src/
│   └── index.js             # Cloud Run app skeleton
├── docs/
│   ├── Summary.html         # Executive summary (auto-generated)
│   ├── DeploymentPlan.md    # Task backlog + AI improvements
│   └── BuildPlans/
│       └── BuildPlan_v1.0.0.md
└── .github/
    └── PULL_REQUEST_TEMPLATE/
        └── pull_request_template.md
```

## Credential Management

### Hierarchy (Priority Order)
1. **GCP Secret Manager** — primary for CI/CD and Cloud Run (all secrets live here)
2. **Service Account JSON** — for GCP API auth (Sheets, Drive, etc.)
3. **MCP Connectors** — Gmail, Calendar, Notion, Slack, Figma (no local creds needed)
4. **Local .env** — fallback for local development only

### First-Time Setup
```bash
# Option A: Pull from GCP Secret Manager (preferred)
./scripts/load-secrets.sh ai-agents-go

# Option B: Manual — copy from centralized Credentials folder
cp .env.example .env
# Edit .env with values from: Credentials Claude Code/Instructions/API Access Master Instructions.txt
```

### Provisioning Secrets to GCP (one-time per secret)
```bash
# Push all credentials to Secret Manager
./scripts/push-secrets.sh ai-agents-go

# Or individual secrets:
echo -n "YOUR_VALUE" | gcloud secrets versions add SECRET_NAME --data-file=- --project=ai-agents-go
```

### Secret Manager Inventory
| Secret | Used By |
|---|---|
| `peak-api-token` | Peak Accounting API |
| `peak-connect-key` | Peak Accounting API |
| `n8n-webhook-key` | n8n webhook auth |
| `xero-client-id` | Xero OAuth |
| `xero-client-secret` | Xero OAuth |
| `notion-api-key` | Notion API |
| `slack-bot-token` | Slack bot |
| `slack-webhook-url` | Slack notifications |
| `figma-token` | Figma API |

### Safety Rules
- **NEVER** commit `.env`, `manifest.json`, `credentials/`, or `*.key` files
- **NEVER** hardcode credentials in source code
- **ALWAYS** use `ENV:` or `SECRET:` references in manifest.json
- All credential patterns are blocked by `.gitignore`
- `verify.sh` checks for leaked credentials in git

## Development Workflow

1. **Plan** — Create Build Plan in Notion, get approval
2. **Develop** — Work on `dev/feature-name` branch with conventional commits
3. **Verify** — Run `./verify.sh` locally
4. **Push** — Push to GitHub → Cloud Build runs tests
5. **AI Eval** — Claude reviews verify-report.json, scores the build
6. **Merge** — PR to `main` → Cloud Build deploys to Cloud Run
7. **Sign-off** — Human reviews and approves

## Branch Strategy
- `main` — production, auto-deploys via Cloud Build
- `dev/feature-name` — development, build + test only

## Commit Convention
```
feat(scope): description    # new feature
fix(scope): description     # bug fix
docs(scope): description    # documentation
chore(scope): description   # config/infra
test(scope): description    # tests
```

## GCP Setup
- Project: `ai-agents-go`
- Region: `asia-southeast1`
- Service account: `claude@ai-agents-go.iam.gserviceaccount.com`
- Secrets: GCP Secret Manager (see inventory above)
- CI/CD: Cloud Build triggers on push to `main` (deploy) and `dev/*` (test)
