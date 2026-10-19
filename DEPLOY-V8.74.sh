#!/usr/bin/env bash
# Safe frontend-only release for the Final Wedding Timings admin review.
set -Eeuo pipefail

cd "${WBM_STACK_DIR:-/mnt/apps/dockge/data/bookingsystem2026}"
umask 077

if [[ ! -f .env ]]; then
  echo 'STOP: .env is missing. Run this in the existing live BookingSystem2026 stack.'
  exit 1
fi

compose=(docker compose -f compose.yaml)
"${compose[@]}" config --quiet

# This installation builds directly from the GitHub repository.
"${compose[@]}" config --format json | python3 -c '
import json, sys
build = json.load(sys.stdin)["services"]["app"].get("build", {})
context = build if isinstance(build, str) else build.get("context", "")
allowed = {
    "https://github.com/valianktni1/bookingsystem2026.git#main",
    "https://github.com/valianktni1/bookingsystem2026.git",
}
sys.exit(0 if context in allowed else "STOP: the app is not configured to build this repository from GitHub. No changes made.")
'

backup_dir="$PWD/deployment-backups/before-v874-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir"

echo '1/5 Backing up and verifying the running database...'
"${compose[@]}" exec -T database sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup_dir/bookingapp.dump"
test -s "$backup_dir/bookingapp.dump"
"${compose[@]}" exec -T database pg_restore --list < "$backup_dir/bookingapp.dump" > /dev/null
cp compose.yaml "$backup_dir/compose.yaml"
cp .env "$backup_dir/app.env"

app_container=$("${compose[@]}" ps -q app)
if [[ -z "$app_container" ]]; then
  echo 'STOP: cannot find the running app to preserve for rollback.'
  exit 1
fi

old_image=$(docker inspect --format '{{.Image}}' "$app_container")
rollback_image="bookingapp-v874-rollback:$(date +%Y%m%d-%H%M%S)"
docker image tag "$old_image" "$rollback_image"
cat > "$backup_dir/rollback.yaml" <<EOF
services:
  app:
    image: $rollback_image
    pull_policy: never
EOF

echo "Backup saved: $backup_dir/bookingapp.dump"
echo '2/5 Building V8.74 while the current app stays running...'
"${compose[@]}" build --no-cache app

echo '3/5 Verifying the new image before touching the live container...'
"${compose[@]}" run --rm --no-deps --entrypoint python app -c '
from pathlib import Path
root = Path("/app/app/static")
script = (root / "v874.js").read_text()
style = (root / "v874.css").read_text()
index = (root / "index.html").read_text()
assert "Technical calculation details" in script
assert "Contacts & important notes" in script
assert "_calculation" in script
assert "final-timings-review-v8-74" in index
assert "@media(max-width:760px)" in style
print("V8.74 static checks passed")
'

echo '4/5 Starting the updated app...'
"${compose[@]}" up -d --no-deps app

echo '5/5 Checking the live app...'
ready=0
for attempt in {1..30}; do
  if "${compose[@]}" exec -T app python -c '
import json, urllib.request
from pathlib import Path
health = json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=4))
assert health["status"] == "ok"
assert "final-timings-review-v8-74" in Path("/app/app/static/index.html").read_text()
' > /dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done

"${compose[@]}" ps
printf '\nRollback command if needed:\nsudo docker compose -f %q -f %q up -d --no-deps --no-build app\n' "$PWD/compose.yaml" "$backup_dir/rollback.yaml"

if [[ "$ready" != 1 ]]; then
  echo 'Health check did not pass. Use the rollback command above and share the app logs.'
  "${compose[@]}" logs --tail=80 app
  exit 1
fi

echo 'V8.74 is responding. Final Timings now opens with the run-sheet summary; all answers and technical workings are collapsed.'
