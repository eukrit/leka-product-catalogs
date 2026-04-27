#!/usr/bin/env bash
# auto-commit-and-merge.sh — Rule 5 canonical helper.
#
# Default-on pipeline: verify → stage → commit → push → (if feature branch) admin-squash PR.
# Opt-outs: .claude/autocommit.opt-out file, Rule 0 goco-project-template protection,
#           and any --no-push / --dry-run CLI flag the caller passes.
#
# Usage:
#   ./scripts/auto-commit-and-merge.sh                     # full pipeline, stages ALL changes (git add -A)
#   ./scripts/auto-commit-and-merge.sh --paths <p1> <p2>   # stage only the listed paths (scoped commit)
#   ./scripts/auto-commit-and-merge.sh -m "feat: ..."      # override commit message
#   ./scripts/auto-commit-and-merge.sh --dry-run           # stop after staging, show diff
#   ./scripts/auto-commit-and-merge.sh --no-push           # commit but don't push
#   ./scripts/auto-commit-and-merge.sh --no-merge          # push but don't open/merge PR
#
# --paths is the safe default when the working tree has unrelated WIP you don't want to bundle.
# Turn-level opt-out is handled upstream (the caller Claude inspects the user's message for
# "draft only" / "don't push" / "don't commit" / "hold off" and skips calling this helper).

set -euo pipefail

COMMIT_MSG=""
DRY_RUN=0
NO_PUSH=0
NO_MERGE=0
PATHS=()
USE_PATHS=0

while [ $# -gt 0 ]; do
  case "$1" in
    -m|--message) COMMIT_MSG="$2"; shift 2 ;;
    --dry-run)    DRY_RUN=1; shift ;;
    --no-push)    NO_PUSH=1; shift ;;
    --no-merge)   NO_MERGE=1; shift ;;
    --paths)      USE_PATHS=1; shift
                  while [ $# -gt 0 ] && [[ "$1" != --* ]] && [[ "$1" != -m ]]; do
                    PATHS+=("$1"); shift
                  done
                  ;;
    *) echo "[auto-commit] unknown arg: $1" >&2; exit 2 ;;
  esac
done

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
if [ -z "$PROJECT_ROOT" ]; then
  echo "[auto-commit] not inside a git repo — aborting." >&2
  exit 1
fi
cd "$PROJECT_ROOT"
WORKTREE_NAME=$(basename "$PROJECT_ROOT")

# Resolve the MAIN repo directory so the repo-mapping check works from a linked
# worktree. `git rev-parse --git-common-dir` returns the path to the main repo's
# .git (shared across all worktrees); its parent is the main checkout.
GIT_COMMON_DIR="$(git rev-parse --git-common-dir 2>/dev/null || echo ".git")"
GIT_COMMON_ABS="$(cd "$GIT_COMMON_DIR" 2>/dev/null && pwd)"
if [ -n "$GIT_COMMON_ABS" ]; then
  MAIN_REPO_DIR="$(dirname "$GIT_COMMON_ABS")"
else
  MAIN_REPO_DIR="$PROJECT_ROOT"
fi
PROJECT_NAME=$(basename "$MAIN_REPO_DIR")

# ---- Opt-out gates (Rule 5) ----
if [ -f ".claude/autocommit.opt-out" ]; then
  echo "[auto-commit] .claude/autocommit.opt-out present — skipping. Remove the file to re-enable."
  exit 0
fi

# ---- Rule 0: goco-project-template protection ----
REMOTE_URL=$(git config --get remote.origin.url 2>/dev/null || echo "")
REMOTE_NAME=$(basename -s .git "$REMOTE_URL" 2>/dev/null || echo "")
if [ "$WORKTREE_NAME" = "goco-project-template" ] \
   || [ "$PROJECT_NAME" = "goco-project-template" ] \
   || [ "$REMOTE_NAME" = "goco-project-template" ]; then
  echo "[auto-commit] goco-project-template is READ-ONLY (Rule 0). Aborting." >&2
  exit 1
fi

# ---- Repo mapping check (Rule 5 step 1) ----
if [ -z "$REMOTE_URL" ]; then
  echo "[auto-commit] no origin remote configured. Propose running:" >&2
  echo "    gh repo create eukrit/${PROJECT_NAME} --private --source=. --push" >&2
  exit 1
fi
if [ -n "$REMOTE_NAME" ] && [ "$REMOTE_NAME" != "$PROJECT_NAME" ]; then
  echo "[auto-commit] MISMATCH: local folder '$PROJECT_NAME' vs remote '$REMOTE_NAME'." >&2
  echo "              Fix the remote or rename the folder before pushing (Rule 5)." >&2
  exit 1
fi

# ---- Verify (Rule 5 step 2) ----
if [ -x "./scripts/verify.sh" ]; then
  echo "[auto-commit] running ./scripts/verify.sh ..."
  ./scripts/verify.sh
elif [ -x "./verify.sh" ]; then
  echo "[auto-commit] running ./verify.sh ..."
  ./verify.sh
else
  # Minimum baseline: gitleaks if available, and hub regeneration.
  if command -v gitleaks >/dev/null 2>&1; then
    echo "[auto-commit] running gitleaks (no project verify.sh) ..."
    gitleaks detect --no-git --source . --verbose || { echo "[auto-commit] gitleaks failed" >&2; exit 1; }
  fi
  if [ -x "./scripts/generate-hub-page.sh" ]; then
    echo "[auto-commit] regenerating Hub Page ..."
    ./scripts/generate-hub-page.sh
  fi
fi

# ---- Stage ----
if [ "$USE_PATHS" -eq 1 ]; then
  if [ ${#PATHS[@]} -eq 0 ]; then
    echo "[auto-commit] --paths given with no arguments — nothing to stage." >&2
    exit 2
  fi
  echo "[auto-commit] scoped staging: ${PATHS[*]}"
  for p in "${PATHS[@]}"; do
    git add -- "$p" 2>/dev/null || echo "[auto-commit] warn: could not stage $p" >&2
  done
else
  # Sanity: anything to commit?
  if [ -z "$(git status --porcelain)" ]; then
    echo "[auto-commit] working tree clean — nothing to commit."
    exit 0
  fi
  git add -A
fi

# Second sanity after staging — scoped staging may have picked up nothing
if [ -z "$(git diff --cached --name-only)" ]; then
  echo "[auto-commit] nothing staged — nothing to commit."
  exit 0
fi

# ---- Dry-run exit ----
if [ "$DRY_RUN" -eq 1 ]; then
  echo "[auto-commit] --dry-run — staged changes (not committing):"
  git --no-pager diff --cached --stat
  exit 0
fi

# ---- Commit message ----
if [ -z "$COMMIT_MSG" ]; then
  CHANGED=$(git diff --cached --name-only | head -5 | paste -sd "," -)
  COUNT=$(git diff --cached --name-only | wc -l | tr -d ' ')
  COMMIT_MSG="chore: auto-commit (${COUNT} file(s): ${CHANGED}...)"
fi

git commit -m "$COMMIT_MSG"

# ---- Push ----
if [ "$NO_PUSH" -eq 1 ]; then
  echo "[auto-commit] --no-push — commit made locally."
  exit 0
fi

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
# Push; set upstream on first push from a new branch
if git rev-parse --abbrev-ref --symbolic-full-name "@{u}" >/dev/null 2>&1; then
  git push
else
  git push -u origin "$CURRENT_BRANCH"
fi

PUSHED_SHA=$(git rev-parse HEAD)

# ---- CI/CD gate (Rule 5 step 4.5) ----
# Wait for Cloud Build + GitHub Actions on this commit; abort merge on failure.
# Block on direct-to-main pushes too: surface the failing build URL even though
# we can't un-push (the next commit becomes the rollback driver).
DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "main")
CI_OK=1
if [ -x "./scripts/check-ci-status.sh" ]; then
  echo "[auto-commit] running CI/CD gate for ${PUSHED_SHA:0:12} ..."
  if ./scripts/check-ci-status.sh "$PUSHED_SHA"; then
    CI_OK=1
  else
    CI_RC=$?
    CI_OK=0
    echo "[auto-commit] CI/CD gate failed (rc=${CI_RC}) — admin-merge BLOCKED." >&2
  fi
else
  echo "[auto-commit] no scripts/check-ci-status.sh — skipping CI gate (run bootstrap-hub-pages.sh to install)."
fi

# ---- Auto-merge feature branches (Rule 5 step 4) ----
if [ "$NO_MERGE" -eq 0 ] && [ "$CURRENT_BRANCH" != "$DEFAULT_BRANCH" ] && [ "$CURRENT_BRANCH" != "main" ] && [ "$CURRENT_BRANCH" != "master" ]; then
  if [ "$CI_OK" -ne 1 ]; then
    echo "[auto-commit] feature branch ${CURRENT_BRANCH} pushed but NOT merged — fix CI then re-run with --no-push." >&2
    exit 1
  fi
  if command -v gh >/dev/null 2>&1; then
    echo "[auto-commit] opening + admin-squash-merging PR for ${CURRENT_BRANCH} → ${DEFAULT_BRANCH} ..."
    gh pr create --fill --base "$DEFAULT_BRANCH" --head "$CURRENT_BRANCH" 2>/dev/null || true
    gh pr merge --admin --squash --delete-branch "$CURRENT_BRANCH"
  else
    echo "[auto-commit] gh CLI not installed; push done but PR not auto-merged." >&2
  fi
fi

echo "[auto-commit] done — ${PROJECT_NAME} @ ${CURRENT_BRANCH}"
