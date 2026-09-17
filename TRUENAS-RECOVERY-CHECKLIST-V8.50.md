# TrueNAS recovery checklist

The Dockge stack directory is not the whole booking system. Protect all three
of these locations:

1. `/mnt/apps/dockge/data/bookingsystem2026` — application source, compose file,
   private environment and verified PostgreSQL dumps.
2. `/mnt/apps/bookingapp2026/data/postgres` — the live PostgreSQL data.
3. `/mnt/temp-tntermediate/bookingapp2026data/data` — uploaded client documents.

Before each deployment, run `scripts/verified-truenas-backup.sh`. It creates a
custom-format PostgreSQL dump, checks that it is non-empty, asks `pg_restore` to
read its catalogue, and prints its SHA-256 checksum. It never deletes an older
backup and it never changes the live database.

The in-app complete ZIP is an excellent human-readable archive. Continue making
it, but treat the verified PostgreSQL dump plus the uploaded-files dataset as
the fastest complete recovery route.

At least once after V8.50 is stable, restore a copy into an isolated temporary
database and confirm that booking, invoice, payment and document counts match.
Never perform a restore over the live `bookingapp` database as a test.
