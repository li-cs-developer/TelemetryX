# TelemetryX — Runbook

Everything you need to start, stop, debug, and recover the stack.

## Starting the stack (Docker — recommended)

    cd C:\Users\tonko\Documents\TelemetryX
    docker compose -f docker-compose.local.yml up -d

Wait for all six containers to show `Up` or `Up (healthy)`:

    docker compose -f docker-compose.local.yml ps

## Starting the stack (native Windows)

Six PowerShell tabs. Every tab needs `.\.venv\Scripts\Activate.ps1` before
running its command.

| Tab | Command |
|-----|---------|
| 0 | `cd C:\Users\tonko\Documents\dynamodb_local_latest && java -D"java.library.path=./DynamoDBLocal_lib" -jar DynamoDBLocal.jar -sharedDb` |
| 1 | `memurai` (or `redis-server`) |
| 2 | `daphne -b 127.0.0.1 -p 8001 telemetryx.asgi:application` |
| 3 | `celery -A telemetryx.celery:app worker -l info --pool=solo` |
| 4 | `celery -A telemetryx.celery:app beat -l info -s /tmp/celerybeat-schedule` |
| 5 | `python scripts/simulate_van.py 1HGCR2F83HA000000 8001 <API_KEY>` |

## Seeding a fresh environment

    # Docker
    docker compose -f docker-compose.local.yml exec web python scripts/seed.py
    docker compose -f docker-compose.local.yml exec web python scripts/seed_geofences.py
    docker compose -f docker-compose.local.yml exec web python manage.py generate_vehicle_keys
    # ⚠️ Copy the key — shown once.

    # Native
    python scripts/seed.py
    python scripts/seed_geofences.py
    python manage.py generate_vehicle_keys

## Health check

    curl http://localhost:8001/healthz/

Expected:

    {"status":"ok","checks":{"mysql":"ok","dynamodb":"ok"}}

A 503 with a `degraded` status means one of the two dependencies is down.

## Common tasks

### Rotate an API key

    python manage.py generate_vehicle_keys --rotate

The old key is invalidated immediately. The new raw key is printed once.

### Run the nightly rollup manually

    python manage.py run_aggregation

Writes `DailyDriverSummary` rows for yesterday. Idempotent — safe to re-run.

### Verify the whole backend

    python scripts/verify_backend.py

Runs 15 checks, exits 0 if all pass, 1 otherwise.

### Inspect DynamoDB locally

    aws dynamodb list-tables --endpoint-url http://localhost:8000

    aws dynamodb scan --table-name TelemetryXTelemetry \
        --endpoint-url http://localhost:8000 --max-items 5

Note: if running under Docker, DynamoDB's host port is 18000, not 8000.

### Reset all data

Docker:

    docker compose -f docker-compose.local.yml down -v
    docker compose -f docker-compose.local.yml up -d
    # Re-seed as above.

Native:

    # MySQL
    mysql -u root -p -e "DROP DATABASE telemetryx; CREATE DATABASE telemetryx;"
    python manage.py migrate
    python manage.py init_plans
    python scripts/seed.py

    # DynamoDB Local — stop Java, delete shared-local-instance.db, restart Java
    python manage.py init_dynamo

## Stopping

Docker:

    docker compose -f docker-compose.local.yml down

Native: Ctrl+C in each tab.

## Logs

Docker:

    docker compose -f docker-compose.local.yml logs -f web
    docker compose -f docker-compose.local.yml logs -f worker
    docker compose -f docker-compose.local.yml logs -f beat
    docker compose -f docker-compose.local.yml logs -f dynamodb

Native: the log is the tab's stdout.

## Troubleshooting index

| Symptom | Section |
|---------|---------|
| `init_dynamo` hangs | README → Troubleshooting → DynamoDB Local |
| `Access denied for user 'telemetryx'` | README → Troubleshooting → MySQL |
| `curl localhost:8001` returns "Empty reply" | README → Troubleshooting → Docker Compose (WSL relay) |
| `beat-1 Restarting (1)` | README → Troubleshooting → Celery |
| Simulator prints 401 | Rotate the key (see above) |
| Simulator prints `ConnectionAbortedError(10053)` | README → Troubleshooting → Simulator |