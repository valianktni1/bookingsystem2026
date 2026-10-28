#!/usr/bin/env bash
# Focused admin workflow. Existing client sending and payment rules are retained. Back up, pin the build, preflight, then restart.
set -Eeuo pipefail

cd "${WBM_STACK_DIR:-/mnt/apps/dockge/data/bookingsystem2026}"
umask 077
RELEASE_COMMIT="c5ff5f951b1f2bea4a62a1a0f5f8d6aa5e9a2605"

if [[ ! -f .env ]]; then
  echo 'STOP: .env is missing. Run this in the existing live BookingSystem2026 stack.'
  exit 1
fi

# Pin the temporary build definition to the exact tested V8.80 source commit.
# The live compose.yaml is never edited.
release_compose=$(mktemp "$PWD/compose.v880.XXXXXX")
cleanup_release_compose() { rm -f "$release_compose"; }
trap cleanup_release_compose EXIT
sed -E "s|(https://github.com/valianktni1/bookingsystem2026\.git)(#main)?|\1#$RELEASE_COMMIT|g" \
  compose.yaml > "$release_compose"
grep -Fq "https://github.com/valianktni1/bookingsystem2026.git#$RELEASE_COMMIT" "$release_compose" || {
  echo 'STOP: the app is not configured to build this repository from GitHub. No changes made.'
  exit 1
}
live_compose=(docker compose -f compose.yaml)
build_compose=(docker compose -f "$release_compose")
"${live_compose[@]}" config --quiet
"${build_compose[@]}" config --quiet

backup_dir="$PWD/deployment-backups/before-v880-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir"

echo '1/5 Backing up and verifying the running database...'
"${live_compose[@]}" exec -T database sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup_dir/bookingapp.dump"
test -s "$backup_dir/bookingapp.dump"
"${live_compose[@]}" exec -T database pg_restore --list < "$backup_dir/bookingapp.dump" > /dev/null
cp compose.yaml "$backup_dir/compose.yaml"
cp .env "$backup_dir/app.env"

app_container=$("${live_compose[@]}" ps -q app)
if [[ -z "$app_container" ]]; then
  echo 'STOP: cannot find the running app to preserve for rollback.'
  exit 1
fi

old_image=$(docker inspect --format '{{.Image}}' "$app_container")
rollback_image="bookingapp-v880-rollback:$(date +%Y%m%d-%H%M%S)"
docker image tag "$old_image" "$rollback_image"
cat > "$backup_dir/rollback.yaml" <<EOF
services:
  app:
    image: $rollback_image
    pull_policy: never
EOF

echo "Backup saved: $backup_dir/bookingapp.dump"
printf '\nRollback command if needed:\nsudo docker compose -f %q -f %q up -d --no-deps --no-build app\n' "$PWD/compose.yaml" "$backup_dir/rollback.yaml"
echo '2/5 Building V8.80 while the current app stays running...'
"${build_compose[@]}" build --no-cache app

echo '3/5 Verifying the new image before touching the live container...'
"${build_compose[@]}" run --rm --no-deps --entrypoint python app -c '
from pathlib import Path
from app.main import app
from app.quote_templates import public_quote_bank_details
assert app.version == "2.8.80"
assert "quote-bank-details-v8-77" in Path("/app/app/static/client.html").read_text()
assert "gallery-connection-v8-80" in Path("/app/app/static/index.html").read_text()
assert "quoteBankDetails" in Path("/app/app/static/client.js").read_text()
assert "gallery-connection-v8-80" in Path("/app/app/static/index.html").read_text()
assert "Gallery connection & package settings" in Path("/app/app/static/v880.js").read_text()
assert "v880-rules" in Path("/app/app/static/v880.css").read_text()
assert any(route.path == "/api/gallery-connection/settings" for route in app.routes)
assert "EmailLog.sent_at.desc()" in Path("/app/app/mail_routes.py").read_text()
assert "quote-bank-details-v8-77" in Path("/app/app/static/quote-preview.html").read_text()
assert chr(92) + "n" not in Path("/app/app/static/index.html").read_text()
print("V8.80 imports and feature checks passed")
'

echo '4/5 Starting the updated app...'
"${live_compose[@]}" up -d --no-deps app

echo '5/5 Checking the live app...'
ready=0
for attempt in {1..30}; do
  if "${live_compose[@]}" exec -T app python -c '
import json, urllib.request
from pathlib import Path
health = json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=4))
assert health["status"] == "ok"
assert "quote-bank-details-v8-77" in Path("/app/app/static/client.html").read_text()
assert "gallery-connection-v8-80" in Path("/app/app/static/index.html").read_text()
' > /dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done

"${live_compose[@]}" ps
printf '\nRollback command if needed:\nsudo docker compose -f %q -f %q up -d --no-deps --no-build app\n' "$PWD/compose.yaml" "$backup_dir/rollback.yaml"

if [[ "$ready" != 1 ]]; then
  echo 'Health check did not pass. Use the rollback command above and share the app logs.'
  "${live_compose[@]}" logs --tail=80 app
  exit 1
fi

echo 'V8.80 is responding. Refresh with Ctrl+F5. Gallery connection is OFF until enabled in Settings > Wedding galleries.'



