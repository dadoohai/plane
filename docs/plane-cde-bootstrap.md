# Plane CDE bootstrap

This repo is forked from `makeplane/plane` at tag `v1.2.3` and uses branch `cde-base` as the starting point for the CDE + agentic work.

## Local parallel stack

We keep the original production/self-host deployment untouched and run a parallel source-based stack from this fork.

### Local files used (not committed)

- `.env` → local compose env, copied from `.local/plane-cde.env`
- `.local/plane-cde.env` → derived from the running self-host config
- `apps/api/.env` → backend env for the source-based API stack

### Tracked files

- `docker-compose.cde-local.yml` → host-port overrides for the parallel stack

### Intended host ports

- API: `8001`
- Postgres: `5433`
- Redis: `6380`
- RabbitMQ: `5673` / `15673`
- MinIO: `9001` / `9091`

## Bring the stack up

```bash
cd /home/Felipe/work/plane-cde
cp .local/plane-cde.env .env
COMPOSE_PROJECT_NAME=plane-cde docker compose \
  --env-file .env \
  -f docker-compose-local.yml \
  -f docker-compose.cde-local.yml \
  up -d plane-db plane-redis plane-mq plane-minio migrator api worker beat-worker
```

## Notes

- The running containerized Plane instance is used only as a reference for configuration and architecture discovery.
- Product development should happen in this fork, not by editing vendor containers in place.
- Next step: map Plane modules for assets/versioning/storage provider/annotations/reviews and start the CDE domain implementation.
