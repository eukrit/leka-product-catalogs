FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
# --prefer-offline: hit npm cache first, skip registry round-trips when possible
# --no-audit / --no-fund: skip post-install audit + funding HTTP calls
# Together these typically cut `npm ci` wall-clock by 30–60s on Cloud Build.
RUN npm ci --prefer-offline --no-audit --no-fund

COPY . .

# Build with development env so config validation doesn't require real DB/Redis
ENV NODE_ENV=development
ENV DATABASE_URL=postgres://placeholder:placeholder@localhost:5432/placeholder
ENV REDIS_URL=redis://localhost:6379

# Bake the production backend URL into the admin UI bundle at build time.
# Without this, the admin bundle hard-codes localhost:9000 and the served
# admin can't talk back to the API. Default keeps local dev working.
ARG MEDUSA_BACKEND_URL=http://localhost:9000
ENV MEDUSA_BACKEND_URL=$MEDUSA_BACKEND_URL

RUN npm run build

# Compile medusa-config.ts to JS so runtime doesn't need ts-node
RUN npx ts-node -e "const ts = require('typescript'); const src = require('fs').readFileSync('medusa-config.ts','utf8'); const out = ts.transpileModule(src, { compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true, target: ts.ScriptTarget.ES2021 }}); require('fs').writeFileSync('medusa-config.js', out.outputText);"

# Note: not pruning devDeps — ts-node and typescript needed at runtime
# for medusa CLI commands (db:migrate, start)

FROM node:20-slim

WORKDIR /app

COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.medusa ./.medusa
COPY --from=builder /app/package.json ./
COPY --from=builder /app/medusa-config.ts ./
COPY --from=builder /app/medusa-config.js ./
COPY --from=builder /app/tsconfig.json ./
COPY --from=builder /app/src ./src
COPY --from=builder /app/start.sh ./
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

EXPOSE 9000

ENV NODE_ENV=production
ENV PORT=9000

CMD ["./start.sh"]
