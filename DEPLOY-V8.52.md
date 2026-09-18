# Deploy BookingSystem2026 V8.52 on TrueNAS

After committing and pushing the V8.52 files through GitHub Desktop, run:

```sh
cd /mnt/apps/dockge/data/bookingsystem2026

BOOKING_BACKUP="/mnt/apps/dockge/data/bookingsystem2026/bookingapp-before-v852-$(date +%Y%m%d-%H%M%S).dump"

sudo sh -c "docker exec bookingsystem2026-db pg_dump -U bookingapp -d bookingapp -Fc > '$BOOKING_BACKUP'"

sudo ls -lh "$BOOKING_BACKUP"

sudo docker compose -f /mnt/apps/dockge/data/bookingsystem2026/compose.yaml build --no-cache app

sudo docker compose -f /mnt/apps/dockge/data/bookingsystem2026/compose.yaml up -d app

sudo docker compose -f /mnt/apps/dockge/data/bookingsystem2026/compose.yaml ps
```

Both containers should report healthy. Refresh once and confirm the header says
**BOOKINGSYSTEM2026 · COMPLETE V8.52**.

Open **Email & SMS templates → Custom Workflow Studio → ＋ Add workflow**.
Nothing is created or activated merely by deployment. Existing V8.51 settings
remain exactly as configured.

Open **Business settings → Email signature** to review the Weddings By Mark
signature, logo and awards panel. The one small database addition is applied
automatically during startup; no separate migration command is needed.
