# TelemetryX — Architecture Deep Dive

This document explains *why* TelemetryX is built the way it is. The README
covers *what* it does; this covers the trade-offs behind each decision.

## The core problem

A fleet of 300 delivery vans, each pinging GPS + speed + engine data every
3 seconds:

    300 vans × 1 ping / 3 seconds = 100 writes/second
    100 writes/second × 86,400 seconds = 8.64 million writes/day
    8.64M × 90 days = ~778 million rows in the hot window

If this stream went into MySQL:

- The disk would be saturated by write-ahead log flushes
- The indexes on `(vehicle_id, timestamp)` would need to be updated
  on every insert
- Every report query the ops team runs would contend with the ingestion
  write lock
- The 90-day retention would require a scheduled DELETE job that
  competes for I/O with live traffic

None of that is acceptable. The whole design flows from this constraint.

## Why DynamoDB for telemetry

DynamoDB's writes go to a distributed cluster. Each write is a single-digit-
millisecond operation against a partition key. There are no indexes to
maintain (only the primary key and optional LSIs/GSIs). There are no
foreign keys. There is no lock contention with readers. And TTL is a
first-class feature — items expire automatically.

**The single-table design:**

    pk = VEHICLE#<vin>
    sk = TS#<ISO8601>

This gives us:

- **Bounded partitions.** Each van's telemetry lives in one logical
  partition. 300 vans = 300 partitions, distributed across the cluster.
  No hot partition as long as a single van doesn't exceed ~1,000 writes/sec.
- **Range queries for free.** `Query(pk, sk BETWEEN t1 AND t2)` returns a
  route in chronological order. No sorting, no scanning.
- **Latest-ping query cheap.** `Query(pk, ScanIndexForward=False, Limit=1)`
  returns one item in one round trip.
- **TTL is a write-time attribute.** We never delete anything — DynamoDB
  does it for us.

## Why MySQL for metadata

Everything that isn't telemetry is relational and small:

- 1 row per organization
- ~10 rows per organization for users
- ~300 rows per organization for vehicles
- ~300 rows per organization for drivers
- Some thousands of rows for maintenance and safety events

At this scale MySQL is *massively* overpowered but that's fine. It's the
right tool because:

- **Foreign keys enforce invariants.** A driver can't be assigned to a
  vehicle that doesn't exist. A vehicle can't be assigned to an org that
  doesn't exist.
- **Transactions matter.** Creating a vehicle + its initial subscription
  + its first API key is one atomic operation, or none of it happens.
- **JOINs are natural.** "All safety events for drivers in this org in the
  last 30 days" is a three-way JOIN MySQL handles with a couple of indexes.
- **Multi-tenant isolation is a WHERE clause.** Every query is scoped by
  `organization_id`. There's no equivalent convenient pattern in DynamoDB.

## Why Channels + Redis for WebSockets

The dashboard needs to update every 3 seconds. Options considered:

1. **Polling.** Simple, stateless. But 50 ops users × 12 requests/min = 600
   req/min of pure overhead, and updates lag by up to the poll interval.
2. **Server-Sent Events.** Simpler than WS, one-way. But we want the
   browser to be able to send messages too (future: ping replay controls).
3. **WebSockets via Channels.** Push, bidirectional, integrates cleanly with
   Django's auth.

We picked WebSockets. Channels runs on the same ASGI server (Daphne in dev,
Uvicorn workers under Gunicorn in prod). The pub/sub layer is Redis — the
same Redis already running as the Celery broker. One infrastructure
dependency, two uses.

**The fan-out pattern:**

    Ingestion view → group_send("org_<id>", {payload})
                          ↓
    Redis pub/sub → every connected client for that org
                          ↓
    FleetLiveConsumer.telemetry_update → websocket.send()
                          ↓
    Alpine.js applyPing() → DOM updates

One message per ping regardless of how many dashboards are watching. That's
the whole point of Channels.

## Why the batch ingestion buffer

DynamoDB's `put_item` costs one network round trip per call. 100 writes/sec
means 100 round trips/sec. Each round trip is ~5-15ms. That's fine at 100/sec,
but at 10,000/sec it becomes the bottleneck.

The `batch_writer()` API does up to 25 items per call — one HTTP request
instead of 25. We buffer in Redis because it's already there, and because
Redis's `RPUSH`/`LPOP` is atomic and fast.

The flow:

    POST /api/v1/telemetry/
      → validate payload
      → RPUSH telemetryx:ping_buffer <json>
      → return 202 immediately

    Celery beat, every 1 second:
      → LPOP up to 25 items
      → batch_writer() writes them to DynamoDB in one call
      → group_by_vin, evaluate geofences, queue speed checks
      → group_send one WS message per vehicle

The HTTP response is now decoupled from the DynamoDB write latency. A slow
DynamoDB doesn't slow down the van device — it slows down the buffer drain,
which Celery handles asynchronously.

## Why the aggregation job

The 90-day TTL deletes raw telemetry. Without a rollup, historical trends
are lost. The nightly `rollup_yesterday` task:

1. For each active vehicle, query DynamoDB for yesterday's pings
2. Compute miles driven (haversine over consecutive points), avg/max speed,
   overspeed count, ping count
3. `update_or_create` a `DailyDriverSummary` row in MySQL

Now the 30-day trend chart on the vehicle detail page queries MySQL only.
Zero DynamoDB reads for long-term views. The raw data is a cache that
expires; the summary is the durable record.

## Why per-vehicle API keys

Options:

- **No auth.** Anyone can post any VIN. Obvious no.
- **Shared org-level key.** Better, but one leaked key compromises the whole
  fleet, and rotation is disruptive.
- **Per-vehicle key, hash-stored, VIN-bound.** This is what we use.

The keys are `secrets.token_urlsafe(32)` — 256 bits of entropy. They're
SHA-256 hashed before storage; the raw value is shown once. The
`VehicleApiKeyAuthentication` class resolves the header to a
`VehicleApiKey` row and the view verifies the payload's VIN matches the
key's bound vehicle. A stolen key can only spoof one van, and rotating it
doesn't affect the rest of the fleet.

## Why pure-Python geofencing

We could use PostGIS (needs Postgres), Shapely, or GeoDjango (needs a
spatial database). All are heavyweight for what we need:

- Circular geofences
- Point-in-circle test
- ~15 lines of trig

The haversine formula is the standard way to compute great-circle distance
between two lat/lng points. It's ~10 lines in Python, exact enough for
any geofence radius (error is <0.5% at the scale of a city), and has zero
dependencies.

**The transition logic is the interesting part, not the math.** We don't
write a `ZoneEvent` on every ping — only when the inside/outside state
changes. That's the difference between 100 rows/sec and ~2 rows/sec per
vehicle. The state is derived from the most recent `ZoneEvent` for
each `(vehicle, geofence)` pair.

## Why Alpine.js instead of React

The dashboard is:
- One map (Leaflet — CDN)
- Two charts (Chart.js — CDN)
- Two or three tables fed by WebSocket
- One form

This is not an SPA. There's no routing, no shared state beyond what the
WebSocket pushes, no complex component tree. Alpine.js gives reactivity in
a script tag with no build step, no bundler, no node_modules. The whole
frontend is Django templates + a few hundred lines of vanilla JS.

For this project, anything more would be architectural astronautics.

## What's deliberately missing

- **Real billing.** The stub enforces plan limits but doesn't charge.
- **Real email.** `_stub_email` writes a row to MySQL and prints to the log.
- **Automated tests.** The `verify_backend.py` script is a smoke test, not
  a proper test suite.
- **Historical archival.** The TTL deletes raw telemetry after 90 days with
  no S3 export. Rollups preserve the aggregates, not the raw points.
- **A production deployment.** The `Dockerfile.prod`, `nginx/`, and
  `docker-compose.prod.yml` are written and correct but require real AWS
  credentials and an external MySQL to exercise.

Each is a one-file change when needed. The architecture supports all of them.