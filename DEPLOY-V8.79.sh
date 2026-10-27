#!/usr/bin/env bash
# Focused admin workflow. Existing client sending and payment rules are retained. Back up, pin the build, preflight, then restart.
set -Eeuo pipefail

cd "${WBM_STACK_DIR:-/mnt/apps/dockge/data/bookingsystem2026}"
umask 077
RELEASE_COMMIT="88f693d84aa4cfa7aab53e4fb7e4b984bf0ef973"

if [[ ! -f .env ]]; then
  echo 'STOP: .env is missing. Run this in the existing live BookingSystem2026 stack.'
  exit 1
fi

# Pin the temporary build definition to the exact tested V8.79 source commit.
# The live compose.yaml is never edited.
release_compose=$(mktemp "$PWD/compose.v879.XXXXXX")
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

backup_dir="$PWD/deployment-backups/before-v879-$(date +%Y%m%d-%H%M%S)"
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
rollback_image="bookingapp-v879-rollback:$(date +%Y%m%d-%H%M%S)"
docker image tag "$old_image" "$rollback_image"
cat > "$backup_dir/rollback.yaml" <<EOF
services:
  app:
    image: $rollback_image
    pull_policy: never
EOF

echo "Backup saved: $backup_dir/bookingapp.dump"
printf '\nRollback command if needed:\nsudo docker compose -f %q -f %q up -d --no-deps --no-build app\n' "$PWD/compose.yaml" "$backup_dir/rollback.yaml"
echo '2/5 Building V8.79 while the current app stays running...'
"${build_compose[@]}" build --no-cache app

echo '3/5 Verifying the new image before touching the live container...'
"${build_compose[@]}" run --rm --no-deps --entrypoint python app -c '
from pathlib import Path
from app.main import app
from app.quote_templates import public_quote_bank_details
assert app.version == "2.8.79"
assert "quote-bank-details-v8-77" in Path("/app/app/static/client.html").read_text()
assert "stage-actions-v8-79" in Path("/app/app/static/index.html").read_text()
assert "quoteBankDetails" in Path("/app/app/static/client.js").read_text()
assert "stage-actions-v8-79" in Path("/app/app/static/index.html").read_text()
assert "Other payment actions" in Path("/app/app/static/v879.js").read_text()
assert "v878-offer-summary" in Path("/app/app/static/v857.js").read_text()
assert "v879-record-payment" in Path("/app/app/static/v879.css").read_text()
assert "EmailLog.sent_at.desc()" in Path("/app/app/mail_routes.py").read_text()
assert "quote-bank-details-v8-77" in Path("/app/app/static/quote-preview.html").read_text()
assert chr(92) + "n" not in Path("/app/app/static/index.html").read_text()
print("V8.79 imports and feature checks passed")
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
assert "stage-actions-v8-79" in Path("/app/app/static/index.html").read_text()
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

echo 'V8.79 is responding. Refresh with Ctrl+F5. Stage-aware actions and clearer Payments are ready.'


