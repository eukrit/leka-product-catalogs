#!/bin/sh

echo "=== Medusa Backend Startup ==="
echo "NODE_ENV: $NODE_ENV"
echo "DATABASE_URL set: $([ -n "$DATABASE_URL" ] && echo 'yes' || echo 'NO')"
echo "REDIS_URL set: $([ -n "$REDIS_URL" ] && echo 'yes' || echo 'NO')"

echo ""
echo "Running database migrations..."
npx medusa db:migrate 2>&1
MIGRATE_EXIT=$?
echo "Migration exit code: $MIGRATE_EXIT"

if [ $MIGRATE_EXIT -ne 0 ]; then
  echo "WARNING: Migration failed with exit code $MIGRATE_EXIT, attempting to start anyway..."
fi

# Create admin user on first run (idempotent — fails silently if exists)
if [ -n "$MEDUSA_ADMIN_EMAIL" ]; then
  echo ""
  echo "Ensuring admin user exists..."
  npx medusa user -e "$MEDUSA_ADMIN_EMAIL" -p "${MEDUSA_ADMIN_PASSWORD:-LekaAdmin2026}" 2>&1 || echo "Admin user already exists or creation failed"
fi

echo ""
echo "Starting Medusa server on port ${PORT:-9000}..."
# Medusa v2 expects to start from .medusa/server (where the built admin assets
# live alongside the compiled server). Starting from /app causes
# `medusa start` with DISABLE_ADMIN=false to look for .medusa/admin/index.html
# which doesn't exist — the built admin is at .medusa/server/public/admin/.
# Run from the correct cwd; resolve the medusa CLI via the parent
# /app/node_modules so we don't need a second install inside .medusa/server.
cd /app/.medusa/server
exec node /app/node_modules/.bin/medusa start
