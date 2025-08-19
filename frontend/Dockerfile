# syntax=docker/dockerfile:1

FROM node:18-bullseye
WORKDIR /app

# Устанавливаем зависимости
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./
RUN if [ -f yarn.lock ]; then \
      yarn install --frozen-lockfile; \
    elif [ -f pnpm-lock.yaml ]; then \
      corepack enable && pnpm install --frozen-lockfile; \
    elif [ -f package-lock.json ]; then \
      npm ci || npm install; \
    else \
      npm install --legacy-peer-deps; \
    fi

# Копируем исходники
COPY . .

ENV NODE_ENV=development
ENV NEXT_DISABLE_SWC_NATIVE=1

EXPOSE 3000
CMD ["npm", "run", "dev"]