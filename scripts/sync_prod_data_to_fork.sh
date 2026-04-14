#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
BACKUPS_ROOT=${BACKUPS_ROOT:-/home/Felipe/backups/plane-selfhost}
BACKUP_DIR=${1:-$(find "$BACKUPS_ROOT" -mindepth 1 -maxdepth 1 -type d | sort | tail -1)}
COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-plane-cde}
COMPOSE_FILES=(-f docker-compose-local.yml -f docker-compose.cde-local.yml)
ENV_FILE=${ENV_FILE:-.env}

if [[ -z "${BACKUP_DIR:-}" || ! -d "$BACKUP_DIR" ]]; then
  echo "Backup directory not found: $BACKUP_DIR" >&2
  exit 1
fi

cd "$ROOT_DIR"

echo "Using backup: $BACKUP_DIR"
export COMPOSE_PROJECT_NAME

docker compose --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" up -d plane-db plane-minio plane-redis plane-mq

docker compose --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" stop api worker beat-worker migrator || true

DB_CONTAINER=$(docker compose --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" ps -q plane-db)
if [[ -z "$DB_CONTAINER" ]]; then
  echo "Could not find plane-db container" >&2
  exit 1
fi

echo "Recreating target database..."
docker exec "$DB_CONTAINER" sh -lc 'export PGPASSWORD="$POSTGRES_PASSWORD"; psql -U "$POSTGRES_USER" -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '\''$POSTGRES_DB'\'' AND pid <> pg_backend_pid();" >/dev/null; dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"; createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'

echo "Copying database dump into DB container..."
docker cp "$BACKUP_DIR/plane-db.dump" "$DB_CONTAINER:/tmp/plane-db.dump"

echo "Restoring database dump into fresh DB..."
docker exec "$DB_CONTAINER" sh -lc 'export PGPASSWORD="$POSTGRES_PASSWORD"; pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner /tmp/plane-db.dump'
docker exec "$DB_CONTAINER" rm -f /tmp/plane-db.dump

echo "Syncing uploads volume..."
docker run --rm \
  -v ${COMPOSE_PROJECT_NAME}_uploads:/dst \
  -v "$BACKUP_DIR":/backup \
  busybox sh -lc 'rm -rf /dst/* && tar -C /dst -xzf /backup/plane-uploads.tar.gz'

echo "Running migrator and starting app services..."
docker compose --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" up -d migrator
# give migrator a moment to finish if it exits quickly
sleep 5
docker compose --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" up -d api worker beat-worker

echo "Done."
