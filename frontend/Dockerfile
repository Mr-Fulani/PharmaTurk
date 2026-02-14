# syntax=docker/dockerfile:1

# ========== Production (сборка: docker build --target production) ==========
FROM node:18-bullseye AS production
WORKDIR /app

COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./
RUN if [ -f yarn.lock ]; then \
      yarn install --frozen-lockfile --production=false; \
    elif [ -f pnpm-lock.yaml ]; then \
      corepack enable && pnpm install --frozen-lockfile; \
    elif [ -f package-lock.json ]; then \
      npm ci; \
    else \
      npm install --legacy-peer-deps; \
    fi

COPY . .
ENV NODE_ENV=production
ENV NEXT_DISABLE_SWC_NATIVE=1
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]

# ========== Development (по умолчанию) ==========
FROM node:18-bullseye AS development
WORKDIR /app

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

COPY . .
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENV NODE_ENV=development
ENV NEXT_DISABLE_SWC_NATIVE=1
EXPOSE 3000
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["npm", "run", "dev"]