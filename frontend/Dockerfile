# syntax=docker/dockerfile:1

FROM node:18-bullseye AS base
WORKDIR /app
ENV NEXT_DISABLE_SWC_NATIVE=1 \
    NODE_ENV=production

# Устанавливаем зависимости (devDeps тоже нужны для сборки Tailwind)
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./
# Важно: устанавливаем dev-зависимости для сборки Tailwind
# и обрабатываем рассинхрон lock-файла (fallback на install)
RUN if [ -f yarn.lock ]; then \
      yarn install --frozen-lockfile --production=false; \
    elif [ -f pnpm-lock.yaml ]; then \
      corepack enable && pnpm install --frozen-lockfile --prod=false; \
    elif [ -f package-lock.json ]; then \
      npm ci --include=dev || npm install --include=dev; \
    else \
      npm install --include=dev --legacy-peer-deps; \
    fi

# Копируем исходники
COPY . .

# Сборка
RUN npm run build || (yarn build || (corepack enable && pnpm build))

# Runtime образ
FROM node:18-bullseye AS runner
WORKDIR /app
ENV NODE_ENV=development \
    NEXT_DISABLE_SWC_NATIVE=1

# Копируем node_modules и .next
COPY --from=base /app/node_modules ./node_modules
COPY --from=base /app/package.json ./package.json
COPY --from=base /app/.next ./.next
COPY --from=base /app/public ./public
COPY --from=base /app/next.config.js ./next.config.js
COPY --from=base /app/next-i18next.config.js ./next-i18next.config.js
COPY --from=base /app/public ./public
COPY --from=base /app/tsconfig.json ./tsconfig.json
COPY --from=base /app/tsconfig.json ./tsconfig.json
COPY --from=base /app/next.config.js ./next.config.js
COPY --from=base /app/styles ./styles

EXPOSE 3000
CMD ["npm", "run", "dev"]
