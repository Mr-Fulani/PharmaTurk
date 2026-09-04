# Production watchdog

## Scope and owner

Owner: `site-operations`. Receiver: the existing administrative Telegram chat
configured by `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

The watchdog runs every five minutes in the serviced `celery` queue and checks:

- `GET /` — Cloudflare/Nginx/Next.js reachability;
- `GET /api/live/` — Django process liveness and its exact JSON contract;
- `GET /api/health/` — PostgreSQL and Redis readiness and its exact JSON contract.

It does not follow redirects. A non-200 response, timeout, connection failure or
invalid health payload is a failed probe. Two consecutive failed runs open one
incident. The receiver gets one alert, at most one reminder per hour, and one
recovery notification after all probes recover. Telegram failures never log the
tokenized API URL.

This in-process watchdog cannot detect loss of the whole Docker host, its
Internet connection, Redis broker, or Celery Beat itself. Keep that residual
risk visible and add a separate off-host uptime check when a provider/receiver
is selected.

## Configuration

Production must explicitly set:

```dotenv
PRODUCTION_WATCHDOG_ENABLED=true
PRODUCTION_WATCHDOG_BASE_URL=https://mudaroba.com
PRODUCTION_WATCHDOG_INTERVAL_SECONDS=300
PRODUCTION_WATCHDOG_FAILURE_THRESHOLD=2
PRODUCTION_WATCHDOG_REPEAT_SECONDS=3600
PRODUCTION_WATCHDOG_REQUEST_TIMEOUT_SECONDS=10
```

`python manage.py check` fails when the watchdog is enabled without an HTTPS
origin or Telegram receiver credentials.

## Triage

1. Confirm `https://mudaroba.com/api/live/` and `/api/health/` independently.
2. If liveness fails, inspect backend container status and logs.
3. If readiness fails with `db=false`, inspect PostgreSQL health and connection
   exhaustion. If `cache=false`, inspect Redis and the cache logical database.
4. If only the homepage fails, inspect Nginx, frontend and Cloudflare origin
   routing.
5. Do not clear Redis, restart databases, or restore backups merely to silence
   an alert. Diagnose first and use the release rollback procedure for a bad
   application revision.

## Safe verification

Run a healthy probe without sending a message:

```bash
poetry run python manage.py shell --no-imports -c \
  'from apps.monitoring.tasks import run_production_watchdog; print(run_production_watchdog())'
```

Expected status is `healthy`. Receiver connectivity can be checked without a
message through Telegram `getMe` and `getChat`. Failure/recovery delivery is
covered by unit tests; do not deliberately take production dependencies down.
