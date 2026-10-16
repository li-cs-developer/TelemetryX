# TelemetryX — Data Model

Complete schema reference for both databases.

## MySQL

All tables live in the `telemetryx` database. Multi-tenant isolation is
enforced by an `organization_id` foreign key on every org-owned table.

### accounts_organization

| Column | Type | Notes |
|--------|------|-------|
| id | bigint PK | |
| name | varchar(150) | |
| slug | varchar(50) UNIQUE | URL-safe identifier |
| created_at | datetime | |

### accounts_user

Extends `django.contrib.auth.models.AbstractUser`.

| Column | Type | Notes |
|--------|------|-------|
| id | bigint PK | |
| username | varchar(150) UNIQUE | |
| email | varchar(254) | |
| password | varchar(128) | Django password hash |
| is_staff | bool | Can access `/admin/` |
| is_superuser | bool | Full admin access |
| organization_id | bigint FK → accounts_organization | Nullable for superusers |
| role | varchar(20) | owner / manager / viewer |

### fleet_vehicle

| Column | Type | Notes |
|--------|------|-------|
| id | bigint PK | |
| organization_id | bigint FK → accounts_organization | |
| vin | varchar(17) UNIQUE | Vehicle Identification Number |
| license_plate | varchar(20) | |
| model_year | int | |
| make | varchar(50) | |
| model | varchar(50) | |
| is_active | bool | |
| created_at | datetime | |

### fleet_driver

| Column | Type | Notes |
|--------|------|-------|
| id | bigint PK | |
| organization_id | bigint FK → accounts_organization | |
| name | varchar(100) | |
| license_number | varchar(50) | |
| assigned_vehicle_id | bigint FK → fleet_vehicle UNIQUE | OneToOne |
| safety_score | int | Starts at 100, decremented by alerts |

### fleet_maintenancelog

| Column | Type | Notes |
|--------|------|-------|
| id | bigint PK | |
| vehicle_id | bigint FK → fleet_vehicle | |
| performed_at | datetime | |
| notes | text | |
| cost_usd | decimal(10,2) | |

### fleet_geofence

| Column | Type | Notes |
|--------|------|-------|
| id | bigint PK | |
| organization_id | bigint FK → accounts_organization | |
| name | varchar(100) | |
| center_lat | float | |
| center_lng | float | |
| radius_meters | float | |
| is_restricted | bool | True: alert on entry; False: alert on exit |
| is_active | bool | |
| created_at | datetime | |

### fleet_zoneevent

Append-only log of geofence transitions.

| Column | Type | Notes |
|--------|------|-------|
| id | bigint PK | |
| vehicle_id | bigint FK → fleet_vehicle | |
| geofence_id | bigint FK → fleet_geofence | |
| kind | varchar(10) | entered / exited |
| occurred_at | datetime | |
| lat | float | Position at transition |
| lng | float | |

Index recommendation: `(vehicle_id, geofence_id, occurred_at DESC)` for the
"most recent state" query.

### fleet_vehicleapikey

| Column | Type | Notes |
|--------|------|-------|
| id | bigint PK | |
| vehicle_id | bigint FK → fleet_vehicle UNIQUE | OneToOne |
| key_hash | varchar(64) UNIQUE | SHA-256 of the raw key |
| label | varchar(100) | |
| is_active | bool | |
| created_at | datetime | |
| last_used_at | datetime NULL | Updated on every authenticated request |

### alerts_safetyevent

| Column | Type | Notes |
|--------|------|-------|
| id | bigint PK | |
| driver_id | bigint FK → fleet_driver | |
| vehicle_id | bigint FK → fleet_vehicle | |
| kind | varchar(30) | overspeed / harsh_brake / idle |
| value | float | e.g. speed in mph |
| occurred_at | datetime | |

### alerts_alertemail

Stub email queue. Rows are written but never actually sent.

| Column | Type | Notes |
|--------|------|-------|
| id | bigint PK | |
| recipient | varchar(254) | |
| subject | varchar(200) | |
| body | text | |
| status | varchar(10) | queued / stub / sent / failed |
| related_kind | varchar(30) | overspeed / geofence |
| related_id | int NULL | FK to SafetyEvent or ZoneEvent |
| created_at | datetime | |
| sent_at | datetime NULL | |

### billing_plan

| Column | Type | Notes |
|--------|------|-------|
| id | bigint PK | |
| code | varchar(50) UNIQUE | trial / starter / scale |
| name | varchar(80) | |
| max_vehicles | int | |
| max_pings_per_second | int | |
| monthly_price_cents | int | |
| is_default | bool | |

### billing_subscription

| Column | Type | Notes |
|--------|------|-------|
| id | bigint PK | |
| organization_id | bigint FK → accounts_organization UNIQUE | OneToOne |
| plan_id | bigint FK → billing_plan | |
| status | varchar(20) | trialing / active / past_due / canceled |
| started_at | datetime | |
| current_period_end | datetime NULL | |

### billing_usagerecord

| Column | Type | Notes |
|--------|------|-------|
| id | bigint PK | |
| organization_id | bigint FK → accounts_organization | |
| date | date | |
| pings_ingested | int | |
| active_vehicles | int | |

Unique constraint: `(organization_id, date)`.

### telemetry_dailydriversummary

Warm-store rollup. Written nightly from DynamoDB.

| Column | Type | Notes |
|--------|------|-------|
| id | bigint PK | |
| organization_id | bigint FK → accounts_organization | |
| driver_id | bigint FK → fleet_driver | |
| date | date | |
| miles_driven | float | Haversine sum |
| avg_speed | float | |
| max_speed | float | |
| overspeed_count | int | |
| pings_seen | int | |

Unique constraint: `(driver_id, date)`.

## DynamoDB

**Table:** `TelemetryXTelemetry`

**Billing mode:** `PAY_PER_REQUEST`

**Key schema:**
- HASH: `pk` (String)
- RANGE: `sk` (String)

**TTL attribute:** `ttl_epoch` (Number)

**Attributes:**

| Name | Type | Required | Notes |
|------|------|----------|-------|
| pk | S | yes | `VEHICLE#<vin>` |
| sk | S | yes | `TS#<ISO8601 UTC>` |
| lat | N | yes | Decimal |
| lng | N | yes | Decimal |
| speed_mph | N | yes | Decimal |
| engine_temp_c | N | yes | Decimal |
| fuel_pct | N | no | Decimal |
| ttl_epoch | N | yes | Unix epoch seconds |

**Why Decimal and not float:** boto3 rejects Python floats for Number
attributes. All numerics must be wrapped via `Decimal(str(x))`.

**Why ISO8601 in the sort key:** lexicographic sort equals chronological
sort when the timezone is always UTC. That makes `BETWEEN` queries correct
without parsing.

**Access patterns:**

| Query | Key condition |
|-------|---------------|
| Latest ping for a van | `pk = VEHICLE#<vin>` with `ScanIndexForward=False, Limit=1` |
| Route between timestamps | `pk = VEHICLE#<vin> AND sk BETWEEN TS#<t1> AND TS#<t2>` |
| Latest ping for N vans | N parallel queries, one per VIN |
| Table-wide scan | Never in application code (admin only) |

**What we do NOT support:**

- Query by speed (would need a GSI)
- Query across vans in a time window (would need a GSI with a different
  partition key)
- Full-text search

If any of those become requirements, add a GSI. The current schema supports
the three patterns the app actually uses.