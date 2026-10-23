#!/usr/bin/env bash
# Post-wedding review email. Back up, pin the build, preflight, then restart.
set -Eeuo pipefail

cd "${WBM_STACK_DIR:-/mnt/apps/dockge/data/bookingsystem2026}"
umask 077
RELEASE_COMMIT="504fd5eb10e499d7583871c6abba056accfd5959"

if [[ ! -f .env ]]; then
  echo 'STOP: .env is missing. Run this in the existing live BookingSystem2026 stack.'
  exit 1
fi

# Pin the temporary build definition to the exact tested post-wedding review email source commit.
# The live compose.yaml is never edited.
release_compose=$(mktemp "$PWD/compose.post-wedding-reviews.XXXXXX")
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

backup_dir="$PWD/deployment-backups/before-post-wedding-reviews-$(date +%Y%m%d-%H%M%S)"
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
rollback_image="bookingapp-post-wedding-reviews-rollback:$(date +%Y%m%d-%H%M%S)"
docker image tag "$old_image" "$rollback_image"
cat > "$backup_dir/rollback.yaml" <<EOF
services:
  app:
    image: $rollback_image
    pull_policy: never
EOF

echo "Backup saved: $backup_dir/bookingapp.dump"
echo '2/5 Building post-wedding review email while the current app stays running...'
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
awards = Path("/app/app/static/branding/weddings-by-mark-awards.jpg")
assert 0 < awards.stat().st_size <= 129000
assert awards.read_bytes().startswith(b"\xff\xd8")
from datetime import date
from types import SimpleNamespace
from app.post_wedding_reviews import TEMPLATE_KEY, GOOGLE_REVIEW_URL, review_template_values
from app.workflow_studio import WORKFLOW_DEFINITIONS
rule = next(row for row in WORKFLOW_DEFINITIONS if row["key"] == TEMPLATE_KEY)
assert rule["default_mode"] == "automatic" and rule["default_days"] == 14
example = SimpleNamespace(brand="wbm", event_date=date(2027, 4, 16))
assert "both vote separately" in review_template_values(example, today=date(2027, 4, 30))["county_brides_request"]
assert not review_template_values(example, today=date(2027, 5, 1))["county_brides_request"]
assert GOOGLE_REVIEW_URL == "https://g.page/r/CWXyai3xrskCEBM/review"
print("Post-wedding review email imports, 14-day timing and voting deadline checks passed")
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
awards = Path("/app/app/static/branding/weddings-by-mark-awards.jpg")
assert 0 < awards.stat().st_size <= 129000
assert awards.read_bytes().startswith(b"\xff\xd8")
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

"${live_compose[@]}" exec -T app python -c '
from app.config import get_settings
settings = get_settings()
print("Automatic reminder service: " + ("ON" if settings.reminders_enabled else "OFF (REMINDERS_ENABLED=false; automatic review emails will not send until enabled)"))
'
echo 'Post-wedding review email is ready. Find Married-life check-in & reviews in Communications > Workflow Studio.'


