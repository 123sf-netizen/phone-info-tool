#!/usr/bin/env bash
set -euo pipefail
umask 077
base="$HOME/phone-info-tool"
release="$1"
cd "$release/local-app"
# Nginx workers run as a different UID inside the container.
chmod a+x "$release" "$release/local-app"
chmod a+r "$release"/*.html "$release/local-app/admin.html"
chmod -R a+rX "$release/images"
mkdir -p "$base/reports"
if [[ ! -f "$base/.env" ]]; then
  {
    printf 'MYSQL_PASSWORD=%s\n' "$(openssl rand -hex 24)"
    printf 'MYSQL_ROOT_PASSWORD=%s\n' "$(openssl rand -hex 24)"
    printf 'ADMIN_TOKEN=%s\n' "$(openssl rand -hex 32)"
  } > "$base/.env"
fi
mkdir -p storage
ln -sfn "$base/reports" storage/reports
docker compose --env-file "$base/.env" -p phone-info-cloud -f docker-compose.yml -f compose.cloud.yml up -d --build --wait --wait-timeout 180
curl --fail --silent --show-error http://127.0.0.1:61434/ -o /dev/null
curl --fail --silent --show-error http://127.0.0.1:61434/api/health
ln -sfn "$release" "$base/current"
