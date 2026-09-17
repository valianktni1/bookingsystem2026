#!/usr/bin/env bash
set -Eeuo pipefail

STACK_DIR="/mnt/apps/dockge/data/bookingsystem2026"
COMPOSE_FILE="${STACK_DIR}/compose.yaml"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_FILE="${STACK_DIR}/bookingapp-verified-${STAMP}.dump"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "Booking compose file was not found at ${COMPOSE_FILE}" >&2
  exit 1
fi

sudo sh -c "docker exec bookingsystem2026-db pg_dump -U bookingapp -d bookingapp -Fc > '${BACKUP_FILE}'"

if [[ ! -s "${BACKUP_FILE}" ]]; then
  echo "The backup file is empty: ${BACKUP_FILE}" >&2
  exit 1
fi

# A readable archive catalogue proves that pg_restore can parse the dump.
sudo docker exec -i bookingsystem2026-db pg_restore --list < "${BACKUP_FILE}" >/dev/null

sudo ls -lh "${BACKUP_FILE}"
sudo sha256sum "${BACKUP_FILE}"
echo "Verified PostgreSQL backup: ${BACKUP_FILE}"
