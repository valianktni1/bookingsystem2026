# Deploy V8.53 on TrueNAS

After replacing the GitHub Desktop repository contents with this complete repo,
committing and pushing to `main`, run:

```bash
cd /mnt/apps/dockge/data/bookingsystem2026

BOOKING_BACKUP="/mnt/apps/dockge/data/bookingsystem2026/bookingapp-before-v853-$(date +%Y%m%d-%H%M%S).dump"

sudo sh -c "docker exec bookingsystem2026-db pg_dump -U bookingapp -d bookingapp -Fc > '$BOOKING_BACKUP'"

sudo ls -lh "$BOOKING_BACKUP"

sudo docker compose -f /mnt/apps/dockge/data/bookingsystem2026/compose.yaml build --no-cache app

sudo docker compose -f /mnt/apps/dockge/data/bookingsystem2026/compose.yaml up -d app

sudo docker compose -f /mnt/apps/dockge/data/bookingsystem2026/compose.yaml ps
```

Expected health build: `2026.09.19-personal-studio-polish-v8.53`.
