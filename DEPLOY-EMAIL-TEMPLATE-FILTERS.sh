#!/usr/bin/env bash
# Email template filters. Back up, pin the build, preflight, then restart.
set -Eeuo pipefail

cd "${WBM_STACK_DIR:-/mnt/apps/dockge/data/bookingsystem2026}"
umask 077
RELEASE_COMMIT="8102705124af6fd5cc9c9acf23b838542ee84cac"

if [[ ! -f .env ]]; then
  echo 'STOP: .env is missing. Run this in the existing live BookingSystem2026 stack.'
  exit 1
fi

# Pin the temporary build definition to the exact tested email template filters source commit.
# The live compose.yaml is never edited.
release_compose=$(mktemp "$PWD/compose.email-template-filters.XXXXXX")
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

backup_dir="$PWD/deployment-backups/before-email-template-filters-$(date +%Y%m%d-%H%M%S)"
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
rollback_image="bookingapp-email-template-filters-rollback:$(date +%Y%m%d-%H%M%S)"
docker image tag "$old_image" "$rollback_image"
cat > "$backup_dir/rollback.yaml" <<EOF
services:
  app:
    image: $rollback_image
    pull_policy: never
EOF

echo "Backup saved: $backup_dir/bookingapp.dump"
echo '2/5 Building email template filters while the current app stays running...'
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
from datetime import timedelta
from app.main import template_preview_booking
from app.models import Brand
from app.business_time import business_today
preview_booking = template_preview_booking(None, Brand.WBM, TEMPLATE_KEY)
assert preview_booking.event_date == business_today() - timedelta(days=14)
filters_js = Path("/app/app/static/email-template-filters.js").read_text()
filters_css = Path("/app/app/static/email-template-filters.css").read_text()
index = Path("/app/app/static/index.html").read_text()
app_js = Path("/app/app/static/app.js").read_text()
assert "WBMEmailTemplateFilters" in filters_js and "Workflow actions" in filters_js
assert "min-height:48px" in filters_css and ":focus-visible" in filters_css
assert "/static/email-template-filters.css?v=email-template-filters-1" in index
assert index.index("/static/email-template-filters.js") < index.index("/static/app.js")
assert "window.WBMEmailTemplateFilters.wire" in app_js
print("Email template filter assets and existing email checks passed")
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
assert "email-template-filters-1" in Path("/app/app/static/index.html").read_text()
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
echo 'Email template filters are ready. Reload Communications and use the filter buttons above Email templates.'


