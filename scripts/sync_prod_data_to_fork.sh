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

docker compose --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" stop api worker beat-worker || true

DB_CONTAINER=$(docker compose --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" ps -q plane-db)
if [[ -z "$DB_CONTAINER" ]]; then
  echo "Could not find plane-db container" >&2
  exit 1
fi

echo "Copying database dump into DB container..."
docker cp "$BACKUP_DIR/plane-db.dump" "$DB_CONTAINER:/tmp/plane-db.dump"

echo "Restoring database..."
docker exec "$DB_CONTAINER" sh -lc 'export PGPASSWORD="$POSTGRES_PASSWORD"; pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner /tmp/plane-db.dump'
docker exec "$DB_CONTAINER" rm -f /tmp/plane-db.dump

echo "Syncing uploads volume..."
docker run --rm \
  -v ${COMPOSE_PROJECT_NAME}_uploads:/dst \
  -v "$BACKUP_DIR":/backup \
  busybox sh -lc 'rm -rf /dst/* && tar -C /dst -xzf /backup/plane-uploads.tar.gz'

echo "Starting migrator and app services..."
docker compose --env-file "$ENV_FILE" "${COMPOSE_FILES[@]}" up -d migrator api worker beat-worker

echo "Done."
