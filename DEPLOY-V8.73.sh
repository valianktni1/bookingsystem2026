#!/usr/bin/env bash
# Run after pushing the complete update to GitHub. The live stack is not a git checkout.
set -Eeuo pipefail
cd "${WBM_STACK_DIR:-/mnt/apps/dockge/data/bookingsystem2026}"
umask 077
if [[ ! -f .env ]]; then echo 'STOP: .env is missing. Run this in your existing live repository.'; exit 1; fi
compose=(docker compose -f compose.yaml)
"${compose[@]}" config --quiet
# This installation builds directly from GitHub; no local git pull or source copy.
"${compose[@]}" config --format json | python3 -c 'import json,sys; c=json.load(sys.stdin)["services"]["app"].get("build",{}); c=c if isinstance(c,str) else c.get("context",""); ok=c in ("https://github.com/valianktni1/bookingsystem2026.git#main", "https://github.com/valianktni1/bookingsystem2026.git"); sys.exit(0 if ok else "STOP: app is not configured to build this repository from GitHub. No changes made.")' 
backup_dir="$PWD/deployment-backups/before-v873-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir"
echo '1/4 Backing up the running database...'
"${compose[@]}" exec -T database sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup_dir/bookingapp.dump"
test -s "$backup_dir/bookingapp.dump"
"${compose[@]}" exec -T database pg_restore --list < "$backup_dir/bookingapp.dump" > /dev/null
cp compose.yaml "$backup_dir/compose.yaml"
cp .env "$backup_dir/app.env"
app_container=$("${compose[@]}" ps -q app)
if [[ -z "$app_container" ]]; then echo 'STOP: cannot find the running app to preserve for rollback.'; exit 1; fi
old_image=$(docker inspect --format '{{.Image}}' "$app_container")
rollback_image="bookingapp-v873-rollback:$(date +%Y%m%d-%H%M%S)"
docker image tag "$old_image" "$rollback_image"
cat > "$backup_dir/rollback.yaml" <<EOF
services:
  app:
    image: $rollback_image
    pull_policy: never
EOF
printf 'Backup saved: %s\n' "$backup_dir/bookingapp.dump"
echo '2/4 Building V8.73 while the current app stays running...'
"${compose[@]}" build --no-cache app
echo '3/4 Starting the updated app...'
"${compose[@]}" up -d --no-deps app
echo '4/4 Checking the app...'
ready=0
for attempt in {1..30}; do
  if "${compose[@]}" exec -T app python -c 'import json,urllib.request; from pathlib import Path; d=json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=4)); assert d["status"]=="ok"; assert "2.8.73" in Path("/app/app/main.py").read_text()' > /dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
"${compose[@]}" ps
printf '\nRollback command if needed:\nsudo docker compose -f %q -f %q up -d --no-deps --no-build app\n' "$PWD/compose.yaml" "$backup_dir/rollback.yaml"
if [[ "$ready" != 1 ]]; then
  echo 'Health check did not pass. Use the rollback command above and share the app logs.'
  "${compose[@]}" logs --tail=60 app
  exit 1
fi
echo 'V8.73 is responding. Refresh your browser with Ctrl+F5.'

