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

echo ""
echo "Starting Medusa server on port ${PORT:-9000}..."
exec npm run start
