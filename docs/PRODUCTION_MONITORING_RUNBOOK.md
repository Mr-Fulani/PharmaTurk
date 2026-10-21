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
Internet connection, Redis broker, or Celery Beat itself. That is why it stayed
silent during the 2026-10-19 outage: the host froze out of memory (see
`PROD_MEMORY.md`), so Beat and the `celery` worker that run the watchdog froze
with it. It is also off unless production `.env` sets
`PRODUCTION_WATCHDOG_ENABLED=true` (default `false`). The off-host check below
covers the residual risk.

## External uptime check (off-host)

Provider: HetrixTools free plan (15 monitors, 1-minute checks, Telegram and
e-mail alerts, commercial use allowed; log in at least once per 90 days or the
free account is deactivated). UptimeRobot's free plan is limited to
non-commercial use and has no Telegram, so it fits only as an e-mail backup.

Setup (owner, in the HetrixTools web UI):

1. Register at hetrixtools.com and confirm the e-mail.
2. Contact Lists → add a list, enable Telegram and follow the bot link it shows
   (press Start in Telegram); keep the account e-mail as a second channel.
3. Uptime Monitors → add a Website monitor `https://mudaroba.com/api/health/`,
   keyword `"status":"ok"` (DRF renders compact JSON; not-ready is also HTTP 503), interval 1 minute,
   several locations, alert after 2 failed checks, the contact list from step 2.
4. Add a second Website monitor `https://mudaroba.com/` (homepage through
   Cloudflare/Nginx/Next.js).
5. Check delivery with the contact list's test notification.

If Cloudflare starts challenging the monitor (false alarms with 403), allow the
provider's user agent or IPs in a Cloudflare WAF skip rule for these two paths.

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
   exhaustion. If `cache=false`, inspect the separate cache container
   `redis-cache` (`allkeys-lru`, `maxmemory 128mb`; the Celery broker lives in
   `redis`, see `docs/PROD_MEMORY.md`).
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

## Disk and Redis alerts

`apps.monitoring.tasks.check_server_resources` runs every ten minutes in the
`celery` queue and uses the same Telegram receiver. It alerts when free space
on the host disk drops below `SERVER_DISK_MIN_FREE_GB` (4 GiB), when the broker
`redis` reaches `REDIS_BROKER_MAX_MEMORY_PERCENT` (70 %) of `maxmemory`, when the
`redis-cache` exceeds `REDIS_CACHE_MAX_MEMORY_PERCENT` (110 %; LRU keeps it near
100 % by design), when a Redis has no `maxmemory`, its last RDB save failed or it
is unreachable. A new problem is sent at once, a repeated one at most every six
hours, and one recovery message follows. It is enabled together with the
watchdog (`SERVER_RESOURCES_MONITOR_ENABLED`). Thresholds and what to do:
`docs/PROD_DISK_AND_REDIS.md`.
