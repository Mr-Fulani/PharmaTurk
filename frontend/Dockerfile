# syntax=docker/dockerfile:1

FROM node:18-bullseye AS base
WORKDIR /app
ENV NEXT_DISABLE_SWC_NATIVE=1 \
    NODE_ENV=production

# Устанавливаем зависимости
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./
RUN if [ -f yarn.lock ]; then yarn install --frozen-lockfile; \
    elif [ -f pnpm-lock.yaml ]; then corepack enable && pnpm install --frozen-lockfile; \
    else npm install --legacy-peer-deps; fi

# Копируем исходники
COPY . .

# Сборка
RUN npm run build || (yarn build || (corepack enable && pnpm build))

# Runtime образ
FROM node:18-bullseye AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_DISABLE_SWC_NATIVE=1

# Копируем node_modules и .next
COPY --from=base /app/node_modules ./node_modules
COPY --from=base /app/package.json ./package.json
COPY --from=base /app/out ./out
COPY --from=base /app/tsconfig.json ./tsconfig.json
COPY --from=base /app/next.config.js ./next.config.js

EXPOSE 8080
CMD ["npx", "http-server", "out", "-p", "8080", "-a", "0.0.0.0"]
