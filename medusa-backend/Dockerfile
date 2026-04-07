FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

# Build with development env so config validation doesn't require real DB/Redis
ENV NODE_ENV=development
ENV DATABASE_URL=postgres://placeholder:placeholder@localhost:5432/placeholder
ENV REDIS_URL=redis://localhost:6379
RUN npm run build

# Prune dev dependencies after build
RUN npm prune --omit=dev

FROM node:20-slim

WORKDIR /app

COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.medusa ./.medusa
COPY --from=builder /app/package.json ./
COPY --from=builder /app/medusa-config.ts ./
COPY --from=builder /app/tsconfig.json ./
COPY --from=builder /app/start.sh ./
RUN chmod +x start.sh

EXPOSE 9000

ENV NODE_ENV=production
ENV PORT=9000

CMD ["./start.sh"]
