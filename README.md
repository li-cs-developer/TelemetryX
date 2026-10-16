# 📡 TelemetryX

> 💡 **A fleet telemetry and asset tracking platform that answers two questions in real time: *Where is every van right now?* and *What happened to it over the last 90 days?*

TelemetryX is a **polyglot-persistence** fleet-tracking platform built for logistics companies running hundreds of delivery vans. It combines **Django + DRF** for the management plane, **DynamoDB** for high-throughput telemetry ingestion, **MySQL** for relational metadata, **Channels + WebSockets** for live map updates, and **Celery + Redis** for async alerting and nightly rollups — all wrapped in a **no-build Alpine.js dashboard**.

The project demonstrates the actual architecture used by real IoT backends: two databases with different access patterns, a hot/cold storage split, a WebSocket push pipeline, per-device API key auth, geofencing with pure-Python haversine math, batched ingestion via Redis, and a containerized local stack that runs the whole six-service system with a single `docker compose` command.

---

## ✨ Features

### 🗺️ Live Fleet Tracking
- **Real-time fleet overview** — every van's position, speed, and status pushed over WebSocket
- **Live positions table** — plate, VIN, speed, lat/lng, status pill updated the instant a ping arrives
- **Recent pings feed** — the last 20 WebSocket messages, timestamped, scrolling as they land
- **Per-vehicle detail page** — 6-hour speed chart from raw telemetry, 30-day rollup chart from MySQL

### 📍 Geofencing
- **Circular zones** with configurable center (lat/lng) and radius (meters)
- **Restricted vs. approved** — entry alerts on restricted zones, exit alerts on approved zones
- **Pure-Python haversine** — no GIS library, ~15 lines of trig
- **State-transition tracking** — only fires on entry/exit, not every ping
- **Zone manager UI** — create and list geofences from the dashboard

### 🔑 Per-Vehicle API Keys
- **`X-Api-Key` header** required on the ingestion endpoint
- **SHA-256 hashed at rest** — raw keys shown once at creation, never stored
- **Vehicle-bound** — one key can't spoof another van's VIN (403 if mismatched)
- **Rotation** — `generate_vehicle_keys --rotate` replaces a key and prints the new raw value

### ⚡ High-Throughput Ingestion
- **Batch mode** — pings buffer in Redis, flushed via `batch_writer()` every second
- **25:1 ratio** — one DynamoDB round trip per 25 pings instead of 1:1
- **Optional sync mode** — toggle `BATCH_INGESTION_ENABLED` to compare
- **One WebSocket message per batch** — not per ping

### 🚨 Alerts & Async Work
- **Overspeed detection** — 80 mph threshold, `SafetyEvent` written to MySQL, driver safety score decremented
- **Geofence transitions** — `ZoneEvent` written on state change
- **Email stub** — `AlertEmail` rows written to the DB, printed in the Celery log, **not actually sent** (by design)

### 💳 Billing (Stub)
- **Plan / Subscription / UsageRecord** models
- **Plan enforcement** — vehicle cap and ingestion cap checked before writes
- **Demo-only** — no Stripe, no webhooks; swap `_stub_email` for a real provider when needed

### 🏢 Multi-Tenant by Default
- **`TenantManager.for_org()`** used on every queryset — org-scoped isolation isn't optional
- **Role-based access** — Owner / Manager / Viewer with `IsManager`, `IsOwner` permission classes
- **Zero cross-tenant leakage** — log in as org A, request org B's vehicle, get 404

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Web framework** | Django 5.2, Django REST Framework 3.16 |
| **ASGI server** | Daphne 4.2 |
| **Async tasks** | Celery 5.6, Celery Beat, Redis 6.4 as broker |
| **Real-time** | Django Channels 4.3, channels-redis 4.3, WebSocket push |
| **Hot-path storage** | AWS DynamoDB (local: `amazon/dynamodb-local`) |
| **Relational storage** | MySQL 8.0 |
| **Frontend** | Alpine.js 3, Leaflet 1.9 (imported but currently unused), Chart.js 4, Django Templates |
| **Static files** | WhiteNoise 6.8 |
| **Containerization** | Docker, Docker Compose |
| **Config** | django-environ 0.12, `.env` files |
| **Deployment (reference)** | Gunicorn + Uvicorn worker + Nginx (files present, not exercised) |

---

## 🏗️ Architecture

TelemetryX uses **polyglot persistence**: two databases, each shaped to the access pattern that actually uses it. The hot path (telemetry) is append-only, massive, and time-series. The relational path (metadata) is small, transactional, and join-heavy. Putting either in the wrong store is the mistake the design avoids.

### Why Two Databases?

| Data | Access pattern | Store | Why |
|------|---------------|-------|-----|
| Orgs, users, drivers, vans, maintenance, safety events, subscriptions | Relational, infrequent, joins, transactions | **MySQL** | ACID, foreign keys, JOIN-heavy reports |
| GPS / speed / engine pings | Append-only, ~100 writes/sec, time-range queries, auto-expire | **DynamoDB** | Millisecond writes, horizontal scale, TTL |

The rule of thumb: **if it needs a JOIN, MySQL. If it needs a millisecond append, DynamoDB.**

### System Architecture

```
┌──────────────┐    HTTPS/JSON     ┌──────────────────────────┐
│ Fleet Vans   │ ────────────────► │ /api/v1/telemetry/       │
│ (simulator)  │  X-Api-Key header │  (DRF ingestion)         │
└──────────────┘                   └────────────┬─────────────┘
                                                │
                                  ┌─────────────┴─────────────┐
                                  ▼                           ▼
                          ┌───────────────┐          ┌──────────────────┐
                          │   MySQL       │          │   DynamoDB       │
                          │ (metadata)    │          │ (FleetTelemetry) │
                          │               │          │  PK=VEHICLE#<vin>│
                          │               │          │  SK=TS#<iso>     │
                          │               │          │  TTL=90 days     │
                          └───────┬───────┘          └────────┬─────────┘
                                  │                           │
                                  └───────────┬───────────────┘
                                              ▼
                                  ┌───────────────────────┐
                                  │ Django + DRF + Alpine │
                                  │  + Channels (WS push) │
                                  │  + Celery (async)     │
                                  └───────────────────────┘
```

### Data Flow — Ingestion

```
[ Van device ]
      │
      │  POST /api/v1/telemetry/  (X-Api-Key + JSON payload)
      ▼
[ VehicleApiKeyAuthentication ]
      │  - looks up key hash
      │  - verifies VIN matches key's bound vehicle
      ▼
[ TelemetryIngestView.post ]
      │
      ├── if BATCH_INGESTION_ENABLED:
      │       └──▶ Redis list (rpush)          ◀── beat: flush_ping_buffer every 1s
      │                                               │
      │                                               ├──▶ DynamoDB batch_writer(25)
      │                                               ├──▶ evaluate_geofences()
      │                                               ├──▶ check_speed_violation.delay()
      │                                               └──▶ group_send("org_<id>")
      │
      └── else (sync path):
              ├──▶ DynamoDB.put_item()
              ├──▶ evaluate_geofences()  →  notify_zone_event.delay()
              ├──▶ check_speed_violation.delay()
              └──▶ channel_layer.group_send("org_<id>")
                          │
                          ▼
                  [ Browser WebSocket client ]
                          │
                          ▼
                  [ Alpine.js reactive table + chart ]
```

### Data Flow — Dashboard Read Path

```
[ Browser GET /dashboard/ ]
        │
        ▼
[ FleetOverview view ]
        │
        ├──▶ MySQL: vehicles for this org       (fast, indexed)
        ├──▶ DynamoDB: latest ping per VIN      (query with ScanIndexForward=False, Limit=1)
        └──▶ JSON serialized into a <script type="application/json"> block
                    │
                    ▼
        [ Alpine.geofenceManager() reads via JSON.parse ]
                    │
                    ▼
        [ Rendered table + WebSocket connect for live updates ]
```

### Data Flow — Geofence Evaluation

```
[ New ping arrives at (lat, lng) for vehicle V ]
        │
        ▼
[ evaluate_geofences(V, lat, lng) ]
        │
        │  for each active geofence G in V's org:
        │    now_inside = haversine(lat, lng, G.center) ≤ G.radius
        │
        │    last_event = most recent ZoneEvent(V, G)
        │    was_inside = (last_event.kind == "entered")
        │
        ├── if now_inside and not was_inside:  create ZoneEvent(kind="entered")
        ├── if not now_inside and was_inside:  create ZoneEvent(kind="exited")
        └── else:                               nothing (no state change)
        │
        ▼
[ for each ZoneEvent: notify_zone_event.delay(event.id) ]
        │
        ▼
[ Celery: _stub_email() writes AlertEmail row + prints to worker log ]
```

---

## 📁 Project Structure

```
TelemetryX/
├── docker-compose.yml                  ← dev stack (native-like)
├── docker-compose.local.yml            ← full Docker stack (MySQL+Redis+DynamoDB+web+worker+beat)
├── docker-compose.prod.yml             ← prod reference (external MySQL, real AWS)
├── Dockerfile                          ← dev image (daphne)
├── Dockerfile.prod                     ← prod image (gunicorn+uvicorn, non-root)
├── requirements.txt                    ← dev + base deps
├── requirements.prod.txt               ← adds gunicorn + uvicorn
├── nginx/
│   └── telemetryx.conf                 ← WS proxy + static files
├── .env                                ← dev config (MySQL, DynamoDB Local, Redis)
├── .env.prod.example                   ← prod config template
├── manage.py
│
├── telemetryx/                         ← Django project
│   ├── settings.py                     ← one settings file, env-driven
│   ├── urls.py                         ← root routing + favicon + healthz
│   ├── asgi.py                         ← ProtocolTypeRouter (HTTP + WebSocket)
│   ├── wsgi.py
│   └── celery.py                       ← Celery app + autodiscover
│
├── apps/
│   ├── accounts/                       ← Orgs, users, roles
│   │   ├── models.py                   ← Organization, User (with role)
│   │   ├── permissions.py              ← HasOrganization, IsManager, IsOwner
│   │   ├── mixins.py                   ← OrgRequiredMixin, ManagerRequiredMixin
│   │   └── admin.py                    ← Custom user admin
│   │
│   ├── fleet/                          ← Vehicles, drivers, geofences, API keys
│   │   ├── models.py                   ← Vehicle, Driver, MaintenanceLog,
│   │   │                                  Geofence, ZoneEvent, VehicleApiKey
│   │   ├── geofence.py                 ← Pure-Python haversine + is_inside()
│   │   └── admin.py                    ← 6 model admins
│   │
│   ├── billing/                        ← SaaS stub
│   │   ├── models.py                   ← Plan, Subscription, UsageRecord
│   │   ├── services.py                 ← get_or_create_subscription, can_add_vehicle, change_plan
│   │   ├── views.py                    ← BillingHome, ChangePlanView
│   │   └── management/commands/
│   │       └── init_plans.py           ← Idempotent plan seeding
│   │
│   ├── telemetry/                      ← The hot path
│   │   ├── dynamo.py                   ← Table creation + idempotent TTL enable
│   │   ├── services.py                 ← write_telemetry, get_latest_ping,
│   │   │                                  get_latest_for_all, get_route
│   │   ├── batcher.py                  ← Redis buffer + flush_ping_buffer Celery task
│   │   ├── auth.py                     ← VehicleApiKeyAuthentication (DRF)
│   │   ├── throttling.py               ← PerVinThrottle, PerIpThrottle
│   │   ├── zone_service.py             ← evaluate_geofences
│   │   ├── consumers.py                ← FleetLiveConsumer (Channels)
│   │   ├── routing.py                  ← ws/fleet/live/ route
│   │   ├── serializers.py              ← TelemetryPingSerializer, GeofenceSerializer
│   │   ├── views.py                    ← TelemetryIngestView, LivePositionsView,
│   │   │                                  GeofenceListCreateView, GeofenceDetailView,
│   │   │                                  HealthCheckView
│   │   ├── urls.py
│   │   ├── aggregation.py              ← rollup_yesterday (nightly hot→warm)
│   │   ├── models.py                   ← DailyDriverSummary (warm store)
│   │   └── management/commands/
│   │       ├── init_dynamo.py          ← Idempotent table creation
│   │       ├── run_aggregation.py      ← Manual rollup trigger
│   │       └── generate_vehicle_keys.py ← Raw key shown once
│   │
│   ├── alerts/                         ← Business events + email stub
│   │   ├── models.py                   ← SafetyEvent, AlertEmail
│   │   ├── tasks.py                    ← check_speed_violation, notify_zone_event,
│   │   │                                  _stub_email
│   │   └── admin.py
│   │
│   └── dashboard/                      ← Alpine-rendered templates
│       ├── views.py                    ← FleetOverview, VehicleDetail, GeofenceManagerView
│       ├── urls.py
│       └── templates/dashboard/
│           ├── base.html               ← Sidebar, Leaflet, Chart.js, Alpine CDN
│           ├── fleet_overview.html     ← Live table + pings feed over WS
│           ├── vehicle_detail.html     ← Speed chart + rollup chart + raw telemetry
│           └── geofences.html          ← Create + list zones
│
└── scripts/
    ├── simulate_van.py                 ← Fires telemetry every 3s with API key
    ├── seed.py                         ← Idempotent org/user/vehicle/driver/plan
    ├── seed_geofences.py               ← Two sample zones (Depot, Downtown)
    ├── verify_backend.py               ← 15-point PASS/FAIL smoke test
    ├── check_dynamo.py                 ← DynamoDB connectivity probe
    ├── dynamo_probe.py                 ← Raw TCP + HTTP test (debugging tool)
    └── manage_admin.py                 ← grant / superuser / list / unblock
```

---

## 🚀 Quick Start

### Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| **Docker Desktop** | Latest | Recommended path; runs the whole stack |
| **Python** | 3.12 | Required for the simulator script |
| **Java** | 17+ | Only if you run DynamoDB Local natively instead of Docker |

### 🐳 Quick Start — Docker (recommended)

```bash
git clone https://github.com/li-cs-developer/TelemetryX.git
cd TelemetryX

# Bring up the entire stack (MySQL + Redis + DynamoDB + web + worker + beat)
docker compose -f docker-compose.local.yml up -d

# Wait ~20 seconds for MySQL and DynamoDB to become healthy
docker compose -f docker-compose.local.yml ps

# Seed the demo data (idempotent — safe to re-run)
docker compose -f docker-compose.local.yml exec web python scripts/seed.py
docker compose -f docker-compose.local.yml exec web python scripts/seed_geofences.py
docker compose -f docker-compose.local.yml exec web python manage.py generate_vehicle_keys
# ⚠️ Copy the raw API key it prints — shown once.

# Run the simulator (from your host, needs Python + requests)
pip install requests
python scripts/simulate_van.py 1HGCR2F83HA000000 8001 <YOUR_KEY>
```

Open `http://localhost:8001/dashboard/` and log in as `ops` / `ops12345`.

**Note on ports:** DynamoDB's host port is mapped to **18000** to avoid a known Windows WSL2 port reservation collision on 8000.

### 🖥️ Native Windows Development

If you prefer to run services directly (no Docker):

```powershell
# 1. Native MySQL on port 3306 with user telemetryx / pass telemetryx
# 2. Native Redis / Memurai on port 6379
# 3. Native DynamoDB Local on port 8000:
cd C:\path\to\dynamodb_local_latest
java -D"java.library.path=./DynamoDBLocal_lib" -jar DynamoDBLocal.jar -sharedDb

# 4. Django ASGI server:
cd C:\path\to\TelemetryX
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python manage.py migrate
python manage.py init_dynamo
python manage.py init_plans
python scripts/seed.py

daphne -b 127.0.0.1 -p 8001 telemetryx.asgi:application

# 5. In separate tabs:
celery -A telemetryx.celery:app worker -l info --pool=solo
celery -A telemetryx.celery:app beat -l info

# 6. Simulator:
python scripts/simulate_van.py 1HGCR2F83HA000000 8001 <YOUR_KEY>
```

---

## 🗄️ Database Schema

### MySQL — Relational Metadata

| Table | Purpose |
|-------|---------|
| `accounts_organization` | Fleet companies (multi-tenant root) |
| `accounts_user` | Users with `organization` FK + `role` (owner/manager/viewer) |
| `fleet_vehicle` | VIN, plate, make, model, year, is_active |
| `fleet_driver` | Name, license, `assigned_vehicle` (OneToOne), `safety_score` |
| `fleet_maintenancelog` | Repair history per vehicle |
| `fleet_geofence` | Center (lat/lng), radius_meters, is_restricted, is_active |
| `fleet_zoneevent` | Entry/exit transitions per (vehicle, geofence) |
| `fleet_vehicleapikey` | SHA-256 hash, label, is_active, last_used_at |
| `alerts_safetyevent` | Overspeed / harsh-brake / idle events |
| `alerts_alertemail` | Stub outbound emails (status, related_kind, related_id) |
| `billing_plan` | Trial / Starter / Scale with vehicle caps |
| `billing_subscription` | OneToOne with org, status, period |
| `billing_usagerecord` | Daily pings/active vehicles snapshot |
| `telemetry_dailydriversummary` | Warm-store rollup: miles, avg/max speed, overspeed count |

### DynamoDB — Time-Series Telemetry

**Table:** `TelemetryXTelemetry`

**Key schema:**
- **Partition key (`pk`):** `VEHICLE#<vin>` — one physical partition per van
- **Sort key (`sk`):** `TS#<ISO8601>` — chronological ordering within a van

**Attributes per item:**

| Attr | Type | Purpose |
|------|------|---------|
| `pk` | S | `VEHICLE#1HGCR2F83HA000000` |
| `sk` | S | `TS#2026-10-16T13:30:57.123456+00:00` |
| `lat` | N | Decimal (via `Decimal(str(x))` — boto3 rejects floats) |
| `lng` | N | Decimal |
| `speed_mph` | N | Decimal |
| `engine_temp_c` | N | Decimal |
| `fuel_pct` | N | Decimal (optional) |
| `ttl_epoch` | N | Unix epoch seconds — 90 days from write time |

**TTL** is enabled on `ttl_epoch`. DynamoDB auto-deletes items when the timestamp passes — no cron job, no cleanup script, no archival logic.

**Access patterns supported:**

| Pattern | Query |
|---------|-------|
| Latest ping per van | `Query(pk=VEHICLE#<vin>, ScanIndexForward=False, Limit=1)` |
| 6-hour route | `Query(pk=VEHICLE#<vin>, sk BETWEEN TS#<t1> AND TS#<t2>)` |
| All vans' latest (fleet map) | N parallel `Query` calls (one per VIN in org) |

---

## 🔌 API Overview

All endpoints are under `/api/v1/`. Ingestion requires `X-Api-Key`. Everything else requires session auth (dashboard) or manager role.

### Ingestion

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/telemetry/` | `X-Api-Key` | Accept one ping; 202 if buffered, 200 if sync |

**Payload:**
```json
{
  "vin": "1HGCR2F83HA000000",
  "timestamp": "2026-10-16T13:30:57.123Z",
  "lat": 37.7749, "lng": -122.4194,
  "speed": 42.5,
  "engine_temp": 92.1,
  "fuel_pct": 63.2
}
```

**Response:** `{"ok": true, "queued": true}` (batch mode) or `{"ok": true}` (sync mode)

### Live & Fleet

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/live/` | session | Initial snapshot of all vans in the user's org |
| GET | `/api/v1/geofences/` | session | List geofences for the user's org |
| POST | `/api/v1/geofences/` | manager | Create a new geofence |
| GET | `/api/v1/geofences/<id>/` | session | Retrieve one geofence |
| PATCH | `/api/v1/geofences/<id>/` | manager | Update |
| DELETE | `/api/v1/geofences/<id>/` | manager | Delete |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/healthz/` | MySQL + DynamoDB check; 200 if both OK, 503 otherwise |

**Response:**
```json
{"status": "ok", "checks": {"mysql": "ok", "dynamodb": "ok"}}
```

### WebSocket

| URL | Description |
|-----|-------------|
| `ws://<host>/ws/fleet/live/` | Per-org channel. Authenticated by session cookie. |

**Message payload (broadcast on each ping or batch):**
```json
{
  "vin": "1HGCR2F83HA000000",
  "plate": "TX-4821",
  "lat": 37.7751,
  "lng": -122.4191,
  "speed": 62.4
}
```

---

## 🧪 Testing & Verification

TelemetryX ships with a comprehensive smoke test instead of a unit test suite:

```bash
python scripts/verify_backend.py
```

This runs 15 checks and prints a PASS/FAIL report:

| Check | What it verifies |
|-------|------------------|
| MySQL connection | Django can reach the configured database |
| Migrations | All apps' migrations are applied |
| Organization | Seed data present |
| Vehicle | Seed data present |
| Driver | Seed data present |
| Plans | `init_plans` ran successfully |
| Subscription | Auto-created on first vehicle save |
| Dashboard-capable user | A user exists with an org attached |
| Admin-capable user | A superuser exists |
| DynamoDB table | `FleetTelemetry` exists |
| DynamoDB TTL | `ttl_epoch` has TTL enabled |
| DynamoDB round-trip | Write → read one ping for the seeded vehicle |
| Geofences | At least one configured |
| Vehicle API keys | At least one active |
| Batch ingestion | Reports enabled/disabled |

Exit code 0 if all pass, 1 if any fail. Suitable for CI.

**Manual verification:** `scripts/dynamo_probe.py` does a raw TCP + HTTP request to DynamoDB Local with timing — useful when a higher-level check hangs.

---

## 🤖 AI-Assisted Development

AI tools (Gemini, Claude) were used throughout development to accelerate scaffolding and support learning. Effective uses included:

- **Architecture design** — the two-database split, the PK/SK pattern for DynamoDB, and the hot/warm rollup strategy were discussed and refined before any code was written.
- **Idempotency patterns** — `ensure_telemetry_table`, `init_plans`, and `seed.py` all follow the same "run it as many times as you want" shape that AI surfaced as a pattern.
- **Geofencing math** — the pure-Python haversine was drafted with AI assistance and then verified against known distances.
- **Batch ingestion design** — Redis list + Celery beat flusher was chosen after comparing three alternatives (asyncio task, in-process queue, Celery chord).
- **Windows/Docker debugging** — the WSL2 port reservation issue, DynamoDB Local's `/data` permission failure, and the `whitenoise` missing-from-requirements bug were all diagnosed with AI help.
- **Documentation** — this README, the inline comments, and the troubleshooting sections were drafted with AI assistance and reviewed for accuracy.

---

## 🐛 Troubleshooting

### DynamoDB Local

**Symptom:** `init_dynamo` hangs forever.

**Cause:** On Windows, WSL2 sometimes reserves ports (including 8000) for internal use. When Docker tries to bind them, requests hang or get aborted.

**Fix:** Move DynamoDB's host port to 18000. This is already done in `docker-compose.local.yml`. If you need 8000 back, run `wsl --shutdown` and restart Docker Desktop.

**Symptom:** `SQLiteException: unable to open database file` in DynamoDB container logs.

**Cause:** Named volume permissions. `amazon/dynamodb-local` runs as non-root and can't write to `/data`.

**Fix:** The `docker-compose.local.yml` uses `-dbPath /tmp` — data lives inside the container, wiped on restart, and reseeded via `docker compose exec`. That's the intended dev workflow.

### MySQL

**Symptom:** `Access denied for user 'telemetryx'@'localhost'`.

**Cause:** The MySQL user was never created, or the password in `.env` doesn't match.

**Fix:** Connect as root and recreate the user:
```sql
CREATE DATABASE telemetryx CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'telemetryx'@'localhost' IDENTIFIED BY 'telemetryx';
GRANT ALL PRIVILEGES ON telemetryx.* TO 'telemetryx'@'localhost';
FLUSH PRIVILEGES;
```

**Symptom:** `mysql` CLI prompts for a password every time.

**Fix:** Use `mysql_config_editor set --login-path=local --host=localhost --user=telemetryx --password`. Windows MySQL reads `%APPDATA%\MySQL\.mylogin.cnf`, not `.my.cnf`.

### Django

**Symptom:** `ImportError: cannot import name 'GeofenceManagerView'`.

**Cause:** A view file wasn't updated after its `urls.py` was.

**Fix:** Files come in pairs. If you edited `urls.py` to import a view, the view must exist in `views.py`. This is the most common mistake when applying patches.

**Symptom:** `ImproperlyConfigured: settings.DATABASES is improperly configured`.

**Cause:** `.env` missing or `DATABASE_URL` not set.

**Fix:** Copy `.env.example` to `.env` and fill in the values.

### WebSocket / Channels

**Symptom:** WS pill shows "disconnected" in the dashboard.

**Cause:** Daphne isn't running, or Channels can't reach Redis.

**Fix:** Confirm Daphne is on the expected port and Redis responds to `redis-cli ping`.

### Celery

**Symptom:** `celerybeat-schedule: Permission denied` on restart.

**Cause:** On Windows-mounted volumes, Celery can't delete its own schedule file.

**Fix:** Run beat with `-s /tmp/celerybeat-schedule` (already in `docker-compose.local.yml`).

**Symptom:** Worker doesn't pick up tasks.

**Fix:** Confirm `CELERY_BROKER_URL` points at Redis and the worker was started with `--pool=solo` on Windows (prefork doesn't work there).

### Docker Compose

**Symptom:** `web-1 exited with code 1 (restarting)` immediately after `up`.

**Cause:** Various — check `docker compose logs web`. The most common are:
- Stale `__pycache__` in the mounted directory
- A missing dependency in `requirements.txt` (rebuild with `--build`)
- Stale volume from a previous run (delete with `down -v`)

**Symptom:** `curl http://localhost:8001/healthz/` returns "Empty reply from server" but the container log shows `Listening on TCP address 0.0.0.0:8001`.

**Cause:** The WSL relay (`wslrelay.exe`) is intercepting host port 8001 the same way it did 8000.

**Fix:** Move the port mapping in `docker-compose.local.yml` from `8001:8001` to `18001:8001` and connect to `http://localhost:18001/dashboard/`.

### Simulator

**Symptom:** Simulator prints `400` or `401` on every ping.

- `400` → VIN isn't in MySQL or payload is malformed
- `401` → API key is wrong or has been rotated; run `generate_vehicle_keys --rotate` and paste the new key

**Symptom:** Simulator prints `ConnectionAbortedError(10053)`.

**Cause:** Same WSL relay issue. Change the port.

---

## 🔒 Security Notes

- **API keys are SHA-256 hashed at rest.** The raw key is shown exactly once at `generate_vehicle_keys` output, then unrecoverable.
- **VIN binding prevents spoofing.** A valid key can only post pings for its bound vehicle's VIN — mismatched VINs return 403.
- **Multi-tenant isolation is enforced at the manager layer.** `TenantManager.for_org()` is used on every queryset that touches org-owned data.
- **Role checks on write endpoints.** Geofence creation and plan changes require `role in ("owner", "manager")`.
- **The prod secrets you commit must be unique per environment.** `.env` files are git-ignored; `.env.prod.example` contains placeholders only.
- **The billing system is a stub.** It enforces plan limits but does not charge anyone. No Stripe, no webhooks, no PCI scope.

---

## 📊 What This Project Demonstrates

For anyone reading the code:

- **Polyglot persistence done deliberately** — two databases, each chosen for its access pattern
- **DynamoDB single-table design** with a documented PK/SK schema and TTL
- **WebSocket push at scale** — Django Channels + Redis as the layer, one group per org
- **Custom DRF authentication** — API keys tied to resources, not users
- **Rate limiting at the edge** — per-VIN and per-IP throttles
- **Async everywhere it matters** — Celery for alerts and rollups, Redis as broker and buffer
- **Batch ingestion pattern** — Redis buffer drained by a fast Celery beat task, 25:1 compression
- **Pure-Python geospatial** — haversine + state-transition logic without a GIS library
- **Idempotent everything** — `init_dynamo`, `init_plans`, `seed.py`, and the DynamoDB table creation all run safely multiple times
- **Verification tooling** — a 15-point smoke test that exits non-zero on failure, suitable for CI
- **Windows/Docker troubleshooting** — this README documents real issues encountered and fixed

---

## 📄 License

MIT — see `LICENSE`.