# Deployment Plan — Living Document

This is the living improvement and task backlog. Claude updates this after every build during the AI evaluation pass.

## Outstanding Tasks

| Project | Task | Priority | Status | Added |
|---------|------|----------|--------|-------|
| ALL | Set up first project using this framework | High | Pending | 2026-03-24 |
| ALL | Configure GCP Cloud Build triggers per project | High | Pending | 2026-03-24 |
| ALL | Add Secret Manager integration to cloudbuild.yaml | High | Pending | 2026-03-24 |
| n8n/Peak | Verify all 80+ Peak API endpoints reachable via MCP | Med | Pending | 2026-03-24 |
| ALL | Set CLOUD_RUN_URL env var per project in verify.sh | Med | Pending | 2026-03-24 |

## Completed Tasks

| Task | Completed In | Date |
|------|-------------|------|
| Manifest Instructions framework designed | v0.1.0 | 2026-03-24 |
| CLAUDE.md template created | v0.1.0 | 2026-03-24 |
| cloudbuild.yaml template created | v0.1.0 | 2026-03-24 |
| verify.sh post-build script created | v0.1.0 | 2026-03-24 |
| Notion master dashboard structured | v0.1.0 | 2026-03-24 |

## AI Improvement Log

### v0.1.0 | 2026-03-24
- **Finding**: Framework created from scratch — no prior baseline to compare against.
- **Recommendation**: First real project build should validate all templates work end-to-end.
- **Recommendation**: Add Slack notification step to cloudbuild.yaml.
- **Recommendation**: Consider adding docs/build-meta.json for automated parsing.

## Build History

| Version | Date | Branch | Status | Pass Rate | Notes |
|---------|------|--------|--------|-----------|-------|
| v0.1.0 | 2026-03-24 | — | Complete | — | Framework initialisation |
