FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
# Install all deps (including dev) for the build step
RUN npm ci

COPY . .
RUN npm run build

# Prune dev dependencies after build
RUN npm prune --omit=dev

FROM node:20-slim

WORKDIR /app

COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.medusa ./.medusa
COPY --from=builder /app/package.json ./

EXPOSE 9000

ENV NODE_ENV=production
ENV PORT=9000

CMD ["npm", "run", "start"]
