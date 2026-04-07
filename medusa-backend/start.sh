#!/bin/sh
# Run database migrations, then start the server
echo "Running database migrations..."
npx medusa db:migrate 2>&1 || echo "Migration failed or already up to date"
echo "Starting Medusa server..."
npm run start
