#!/usr/bin/env bash
# Ivory Digital recurring billing. Back up, pin the build, preflight, then restart.
set -Eeuo pipefail

cd "${WBM_STACK_DIR:-/mnt/apps/dockge/data/bookingsystem2026}"
umask 077
RELEASE_COMMIT="5beb7765e94f6826b359035d149b2774414cb8c1"

if [[ ! -f .env ]]; then
  echo 'STOP: .env is missing. Run this in the existing live BookingSystem2026 stack.'
  exit 1
fi

# Pin the temporary build definition to the exact tested V8.89 source commit.
# The live compose.yaml is never edited.
release_compose=$(mktemp "$PWD/compose.ivory-recurring-v889.XXXXXX")
auth_compose=$(mktemp "$PWD/compose.ivory-recurring-auth.XXXXXX")
cleanup_release_compose() { rm -f "$release_compose" "$auth_compose"; unset WBM_BOOKING_GITHUB_TOKEN; }
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

backup_dir="$PWD/deployment-backups/before-v889-$(date +%Y%m%d-%H%M%S)"
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
rollback_image="bookingapp-v889-rollback:$(date +%Y%m%d-%H%M%S)"
docker image tag "$old_image" "$rollback_image"
cat > "$backup_dir/rollback.yaml" <<EOF
services:
  app:
    image: $rollback_image
    pull_policy: never
EOF

echo "Backup saved: $backup_dir/bookingapp.dump"
printf '\nRollback command if needed:\nsudo docker compose -f %q -f %q up -d --no-deps --no-build app\n' "$PWD/compose.yaml" "$backup_dir/rollback.yaml"
echo '2/5 Building V8.89 while the current app stays running...'
if ! curl -fsS --max-time 15 "https://raw.githubusercontent.com/valianktni1/bookingsystem2026/$RELEASE_COMMIT/Dockerfile" >/dev/null 2>&1; then
  if [[ -z "${WBM_BOOKING_GITHUB_TOKEN:-}" ]]; then
    printf 'Private booking repo: paste a GitHub token with repository Contents read access: ' >/dev/tty
    IFS= read -rs WBM_BOOKING_GITHUB_TOKEN </dev/tty
    printf '\n' >/dev/tty
  fi
  test -n "$WBM_BOOKING_GITHUB_TOKEN"
  export WBM_BOOKING_GITHUB_TOKEN
  cat > "$auth_compose" <<'AUTH_YAML'
services:
  app:
    build:
      secrets:
        - source: wbm_booking_git_auth
          target: GIT_AUTH_TOKEN
secrets:
  wbm_booking_git_auth:
    environment: WBM_BOOKING_GITHUB_TOKEN
AUTH_YAML
  docker compose -f "$release_compose" -f "$auth_compose" build --no-cache app
  unset WBM_BOOKING_GITHUB_TOKEN
else
  "${build_compose[@]}" build --no-cache app
fi

echo '3/5 Verifying the new image before touching the live container...'
"${build_compose[@]}" run --rm --no-deps --entrypoint python app -c '
from pathlib import Path
from app.main import app
from app.quote_templates import public_quote_bank_details
assert app.version == "2.8.89"
assert "quote-bank-details-v8-77" in Path("/app/app/static/client.html").read_text()
assert "gallery-setup-v8-82" in Path("/app/app/static/index.html").read_text()
assert "quoteBankDetails" in Path("/app/app/static/client.js").read_text()
assert "gallery-setup-v8-82" in Path("/app/app/static/index.html").read_text()
assert "Gallery connection & package settings" in Path("/app/app/static/v880.js").read_text()
assert "v880-rules" in Path("/app/app/static/v880.css").read_text()
from app.enquiry_delivery import EnquiryEmailJob, enquiry_email_loop
assert EnquiryEmailJob.__tablename__ == "enquiry_email_jobs"
assert "enquiry-conversion-2026-11-17" in Path("/app/app/static/enquiry.html").read_text()
assert "queue_enquiry_email" in Path("/app/app/main.py").read_text()
from app.gallery_integration import WEDDINGS_AFTER
assert WEDDINGS_AFTER.isoformat() == "2026-12-01"
from app.gallery_integration import selected_items, requeue_configured_jobs
assert "missing_rule_keys" in Path("/app/app/gallery_integration.py").read_text()
assert "Save setup & resume waiting bookings" in Path("/app/app/static/v880.js").read_text()
assert any(route.path == "/api/gallery-connection/settings" for route in app.routes)
assert "EmailLog.sent_at.desc()" in Path("/app/app/mail_routes.py").read_text()
assert "quote-bank-details-v8-77" in Path("/app/app/static/quote-preview.html").read_text()
assert chr(92) + "n" not in Path("/app/app/static/index.html").read_text()
index = Path("/app/app/static/index.html").read_text()
extras = Path("/app/app/static/payment-extras.js").read_text()
styles = Path("/app/app/static/payment-extras.css").read_text()
assert "WBMPaymentExtras" in extras and "Add-ons / extras" in extras
assert "payment-extras.css?v=payment-extras-1" in index
assert index.index("/static/payment-extras.js") > index.index("/static/v848.js")
assert "grid-template-columns:minmax(0,1fr) auto" in styles
from app.ivory_quotes import IvoryOffer, STARTER
from app.ivory_pdf import ivory_invoice_pdf
assert IvoryOffer.__tablename__ == "ivory_offers"
assert STARTER["opening_paid"] == "599.50"
assert STARTER["opening_paid_date"] == "2026-10-19"
assert sum(float(x["amount"]) for x in STARTER["lines"]) == 1649
assert "ivory-quotes.js?v=889" in index
assert "ivoryquotes" in index
assert any(route.path == "/api/ivory-quotes/{offer_id}/accept" for route in app.routes)
assert any(route.path == "/api/public/ivory-quotes/{token}/accept" for route in app.routes)
assert "with_for_update" in Path("/app/app/services.py").read_text()
assert "storybooks" in index
from datetime import date
from app.ivory_recurring import RecurringPlan, RecurringCycle, cycle_start, run_due_cycles
assert RecurringPlan.__tablename__ == "ivory_recurring_plans"
assert RecurringCycle.__tablename__ == "ivory_recurring_cycles"
assert cycle_start(date(2027, 1, 31), 1, 2) == date(2027, 3, 31)
assert any(route.path == "/api/ivory-recurring" for route in app.routes)
assert "New recurring invoice" in Path("/app/app/static/ivory-quotes.js").read_text()
assert "recurring_loop()" in Path("/app/app/main.py").read_text()
print("V8.89 recurring billing, shared numbering and existing feature checks passed")
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
assert health["version"] == "2.8.89"
from sqlalchemy import inspect
from app.database import engine
assert {"ivory_recurring_plans", "ivory_recurring_cycles"}.issubset(inspect(engine).get_table_names())
with urllib.request.urlopen("http://127.0.0.1:8000/storybook-order", timeout=4) as response:
    assert b"storybook-public.js" in response.read()
assert "payment-extras.js?v=payment-extras-1" in Path("/app/app/static/index.html").read_text()
assert "quote-bank-details-v8-77" in Path("/app/app/static/client.html").read_text()
assert "gallery-setup-v8-82" in Path("/app/app/static/index.html").read_text()
' > /dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done

"${live_compose[@]}" ps
printf '\nRollback command if needed:\nsudo docker compose -f %q -f %q up -d --no-deps --no-build app\n' "$PWD/compose.yaml" "$backup_dir/rollback.yaml"

if [[ "$ready" != 1 ]]; then
  echo 'Health check did not pass. Restoring the previous app image.'
  "${live_compose[@]}" -f "$backup_dir/rollback.yaml" up -d --no-deps --no-build app
  "${live_compose[@]}" logs --tail=80 app
  exit 1
fi

echo 'V8.89 is responding. Open Ivory quotes & invoices > New recurring invoice or Recurring billing. Existing customers are not enrolled automatically; no email or payment is sent by this deployment.'
