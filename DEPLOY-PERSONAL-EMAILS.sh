#!/usr/bin/env bash
# Personal email update. Back up, pin the build, preflight, then restart.
set -Eeuo pipefail

cd "${WBM_STACK_DIR:-/mnt/apps/dockge/data/bookingsystem2026}"
umask 077
RELEASE_COMMIT="7e42fe49dc824b7f47f62f10bf0985fd3529eaba"

if [[ ! -f .env ]]; then
  echo 'STOP: .env is missing. Run this in the existing live BookingSystem2026 stack.'
  exit 1
fi

# Pin the temporary build definition to the exact tested personal email update source commit.
# The live compose.yaml is never edited.
release_compose=$(mktemp "$PWD/compose.personal-emails.XXXXXX")
cleanup_release_compose() { rm -f "$release_compose"; }
trap cleanup_release_compose EXIT
sed -E "s|(https://github.com/valianktni1/bookingsystem2026\.git)(#[-A-Za-z0-9_./]+)?|\1#$RELEASE_COMMIT|g" \
  compose.yaml > "$release_compose"
grep -Fq "https://github.com/valianktni1/bookingsystem2026.git#$RELEASE_COMMIT" "$release_compose" || {
  echo 'STOP: the app is not configured to build this repository from GitHub. No changes made.'
  exit 1
}
live_compose=(docker compose -f compose.yaml)
build_compose=(docker compose -f "$release_compose")
"${live_compose[@]}" config --quiet
"${build_compose[@]}" config --quiet

backup_dir="$PWD/deployment-backups/before-personal-emails-$(date +%Y%m%d-%H%M%S)"
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
rollback_image="bookingapp-personal-emails-rollback:$(date +%Y%m%d-%H%M%S)"
docker image tag "$old_image" "$rollback_image"
cat > "$backup_dir/rollback.yaml" <<EOF
services:
  app:
    image: $rollback_image
    pull_policy: never
EOF

echo "Backup saved: $backup_dir/bookingapp.dump"
echo '2/5 Building personal email update while the current app stays running...'
"${build_compose[@]}" build --no-cache app

echo '3/5 Verifying the new image before touching the live container...'
"${build_compose[@]}" run --rm --no-deps --entrypoint python app -c '
from pathlib import Path
from app.main import app
from app.email_defaults import PERSONAL_EMAIL_DEFAULTS
from app.email_service import QUOTE_FOLLOWUP_KEYS
assert QUOTE_FOLLOWUP_KEYS == {"quote_followup_1", "quote_followup_final"}
assert "{payment_reference}" in PERSONAL_EMAIL_DEFAULTS["quote"][1]
assert "I am thrilled" not in PERSONAL_EMAIL_DEFAULTS["quote"][1]
assert "22px 5px" in Path("/app/app/email_service.py").read_text()
print("Personal email update imports and feature checks passed")
'

echo '4/5 Starting the updated app...'
"${build_compose[@]}" up -d --no-deps --no-build app

echo '5/5 Checking the live app...'
ready=0
for attempt in {1..30}; do
  if "${live_compose[@]}" exec -T app python -c '
import json, urllib.request
from pathlib import Path
health = json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=4))
assert health["status"] == "ok"
assert "22px 5px" in Path("/app/app/email_service.py").read_text()
from app.email_defaults import PERSONAL_EMAIL_DEFAULTS
assert "{payment_reference}" in PERSONAL_EMAIL_DEFAULTS["quote"][1]
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

echo 'Personal email update is responding. Check the quote and follow-up previews in Communications.'


