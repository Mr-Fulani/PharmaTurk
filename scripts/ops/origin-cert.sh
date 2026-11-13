#!/usr/bin/env bash
# Origin certificate for Cloudflare Full (strict): Let's Encrypt via HTTP-01.
#   origin-cert.sh issue   — first certificate (once, by hand)
#   origin-cert.sh renew   — from cron; reloads nginx only after a renewal
# Files live in nginx/tls/ (gitignored, mounted read-only into nginx).
# Steps: docs/PROD_ORIGIN_SECURITY.md.
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
TLS="$PWD/nginx/tls"
NGINX="${NGINX_CONTAINER:-mudaroba-nginx-1}"
IMAGE="certbot/certbot:v5.9.0"
mkdir -p "$TLS/letsencrypt" "$TLS/acme"

certbot() {
  docker run --rm --user "$(id -u):$(id -g)" \
    -v "$TLS/letsencrypt:/etc/letsencrypt" -v "$TLS/acme:/var/www/acme" \
    "$IMAGE" --config-dir /etc/letsencrypt --work-dir /etc/letsencrypt/work \
    --logs-dir /etc/letsencrypt/logs "$@"
}

case "${1:-}" in
  issue)
    certbot certonly --webroot -w /var/www/acme --cert-name mudaroba.com \
      -d mudaroba.com -d www.mudaroba.com \
      --agree-tos --register-unsafely-without-email --non-interactive
    ;;
  renew)
    date -u +%FT%TZ
    certbot renew --quiet --deploy-hook "touch /etc/letsencrypt/renewed"
    if [[ -f "$TLS/letsencrypt/renewed" ]]; then
      docker exec "$NGINX" nginx -t
      docker exec "$NGINX" nginx -s reload
      rm "$TLS/letsencrypt/renewed"
      echo "renewed, nginx reloaded"
    fi
    ;;
  *) echo "usage: $0 issue|renew" >&2; exit 2 ;;
esac
