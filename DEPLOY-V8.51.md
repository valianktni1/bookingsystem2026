# Deploy BookingSystem2026 V8.51 on TrueNAS

After replacing the GitHub Desktop working folder with this release, commit and
push it to the public `main` branch. Then use Mark's normal TrueNAS deployment:

```sh
cd /mnt/apps/dockge/data/bookingsystem2026

BOOKING_BACKUP="/mnt/apps/dockge/data/bookingsystem2026/bookingapp-before-v851-$(date +%Y%m%d-%H%M%S).dump"

sudo sh -c "docker exec bookingsystem2026-db pg_dump -U bookingapp -d bookingapp -Fc > '$BOOKING_BACKUP'"

sudo ls -lh "$BOOKING_BACKUP"

sudo docker compose -f /mnt/apps/dockge/data/bookingsystem2026/compose.yaml build --no-cache app

sudo docker compose -f /mnt/apps/dockge/data/bookingsystem2026/compose.yaml up -d app

sudo docker compose -f /mnt/apps/dockge/data/bookingsystem2026/compose.yaml ps
```

The final output should show both `bookingsystem2026-db` and
`bookingsystem2026-app` as healthy. If GitHub reports that it cannot read a
username while the repository is public, verify the repository state with:

```sh
git ls-remote https://github.com/valianktni1/bookingsystem2026.git HEAD
```

## First check after deployment

1. Refresh the browser once.
2. Confirm the header says **BOOKINGSYSTEM2026 · COMPLETE V8.51**.
3. Open **Email & SMS templates**.
4. Confirm **Custom Workflow Studio** is at the top.
5. Do not press Save unless intentionally changing a workflow. The defaults
   already match the V8.50.2 live schedule.

No database migration or extra environment variable is required.
