-- AirAtlas schema v1.
-- Conventions: every timestamp is timestamptz in UTC. Hourly rows are keyed by the START of the
-- hour as the source reports it (India's hours start at :30 UTC). Concentrations are in canonical
-- units: ug/m3 for everything except co (mg/m3). Indices are computed from these at read time.

create extension if not exists postgis;

create table regions (
    id              smallint primary key,
    code            text not null unique,
    name            text not null,
    country_code    char(2) not null,
    timezone        text not null,           -- IANA zone used for local days and display
    local_standard  text not null,           -- airatlas_aqi standard code
    bbox            geometry(Polygon, 4326) not null
);

create table admin_areas (
    id          serial primary key,
    region_id   smallint not null references regions on delete cascade,
    level       text not null check (level in ('district', 'emirate', 'state')),
    name        text not null,
    source      text not null,               -- e.g. 'geoBoundaries IND ADM2 (ODbL)'
    geom        geometry(MultiPolygon, 4326) not null,
    unique (region_id, level, name)
);
create index admin_areas_geom on admin_areas using gist (geom);

create table sources (
    id           smallint primary key,
    code         text not null unique,
    name         text not null,
    kind         text not null check (kind in ('official', 'aggregator', 'model', 'satellite')),
    priority     smallint not null,          -- higher wins when two sources write the same station-hour
    license      text not null,
    attribution  text not null,
    url          text not null
);

-- One row per physical location (monitor, low-cost sensor or model grid point).
create table stations (
    id             serial primary key,
    region_id      smallint references regions,     -- null until assigned by boundary lookup
    admin_area_id  integer references admin_areas,
    name           text not null,
    city           text,
    geom           geometry(Point, 4326) not null,
    kind           text not null check (kind in ('reference', 'low_cost', 'modeled')),
    setting        text,                     -- urban / suburban / rural (where the source says)
    station_type   text,                     -- background / traffic / industry
    first_seen_at  timestamptz not null default now(),
    last_seen_at   timestamptz not null default now(),
    active         boolean not null default true,
    meta           jsonb not null default '{}'
);
create index stations_geom on stations using gist (geom);
create index stations_region on stations (region_id) where active;

-- Each source's identity for a station. Lets CPCB's and OpenAQ's copy of one monitor share a row.
create table station_sources (
    source_id    smallint not null references sources,
    external_id  text not null,
    station_id   integer not null references stations on delete cascade,
    license      text,
    meta         jsonb not null default '{}',     -- e.g. OpenAQ sensor ids and units
    primary key (source_id, external_id)
);
create index station_sources_station on station_sources (station_id);

-- Hourly concentrations (source of truth). Wide layout: see docs/storage_budget.py.
create table readings (
    station_id   integer not null,
    ts           timestamptz not null,
    source_id    smallint not null,
    pm25 real, pm10 real, no2 real, o3 real, so2 real, co real, nh3 real, dust real,
    ingested_at  timestamptz not null default now(),
    primary key (station_id, ts)
) partition by range (ts);

-- Hourly rows kept forever for festival windows (copied out before partitions are dropped).
create table readings_archive (like readings including defaults, primary key (station_id, ts));

create table retention_holds (
    id         serial primary key,
    label      text not null,
    region_id  smallint not null references regions,
    starts_at  timestamptz not null,
    ends_at    timestamptz not null,
    unique (label, region_id)
);

-- Daily aggregates, keyed by the station's LOCAL calendar day. Kept forever.
create table readings_daily (
    station_id  integer not null,
    day         date not null,
    source_id   smallint not null,
    n_hours     smallint,                    -- hours with any value; null for source-provided dailies
    pm25_mean real, pm25_max real, pm10_mean real, pm10_max real,
    no2_mean real, no2_max real, o3_mean real, o3_max real,
    so2_mean real, so2_max real, co_mean real, co_max real,
    nh3_mean real, dust_mean real, dust_max real,
    primary key (station_id, day)
);

-- CPCB's published sub-index values (data.gov.in). These are index values, NOT concentrations.
create table official_aqi (
    station_id   integer not null,
    reported_at  timestamptz not null,
    pollutant    text not null,
    sub_min      real, sub_avg real, sub_max real,
    primary key (station_id, reported_at, pollutant)
);

create table weather (
    station_id    integer not null,
    ts            timestamptz not null,
    temp_c real, rh_pct real, precip_mm real, wind_ms real, wind_dir_deg real, pressure_hpa real,
    primary key (station_id, ts)
) partition by range (ts);

create table weather_daily (
    station_id  integer not null,
    day         date not null,
    temp_mean real, rh_mean real, precip_sum real, wind_mean real,
    primary key (station_id, day)
);

create table fire_events (
    id           bigserial primary key,
    region_id    smallint not null references regions,
    detected_at  timestamptz not null,
    lat          numeric(8, 5) not null,
    lon          numeric(8, 5) not null,
    geom         geometry(Point, 4326) generated always as (st_setsrid(st_makepoint(lon::float8, lat::float8), 4326)) stored,
    frp          real,                       -- fire radiative power, MW
    confidence   text,
    satellite    text not null,
    instrument   text,
    daynight     char(1),
    unique (detected_at, satellite, lat, lon)
);
create index fire_events_region_time on fire_events (region_id, detected_at);
create index fire_events_geom on fire_events using gist (geom);

create table forecasts (
    station_id  integer not null,
    model       text not null,
    pollutant   text not null,
    issued_at   timestamptz not null,
    target_ts   timestamptz not null,
    value       real not null,
    lower real, upper real,
    primary key (station_id, model, pollutant, issued_at, target_ts)
);

create table anomalies (
    id           bigserial primary key,
    station_id   integer not null,
    ts           timestamptz not null,
    pollutant    text not null,
    value        real not null,
    baseline     real,
    score        real,
    method       text not null,
    cause_hints  jsonb not null default '[]',
    created_at   timestamptz not null default now(),
    unique (station_id, ts, pollutant, method)
);

create table ingestion_runs (
    id             bigserial primary key,
    job            text not null,
    region         text,
    source         text,
    started_at     timestamptz not null default now(),
    finished_at    timestamptz,
    status         text not null default 'running' check (status in ('running', 'success', 'partial', 'failed')),
    rows_fetched   integer not null default 0,
    rows_written   integer not null default 0,
    rows_rejected  integer not null default 0,
    error          text,
    details        jsonb not null default '{}'
);
create index ingestion_runs_recent on ingestion_runs (source, region, started_at desc);

-- Resumable backfills: how far each (source, station, kind) has been fetched.
create table backfill_progress (
    source_id   smallint not null,
    station_id  integer not null,
    kind        text not null check (kind in ('hourly', 'daily', 'weather_daily', 'event')),
    done_from   timestamptz not null,
    done_until  timestamptz not null,
    updated_at  timestamptz not null default now(),
    primary key (source_id, station_id, kind)
);
