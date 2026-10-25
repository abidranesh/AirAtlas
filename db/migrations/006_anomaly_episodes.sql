-- Anomalies are stored as episodes (consecutive anomalous hours), keyed by their start, with the
-- peak in ts/value/score. Detection re-runs replace episodes that end inside the re-run window.
alter table anomalies
    add column starts_at timestamptz,
    add column ends_at timestamptz,
    add column details jsonb not null default '{}';
update anomalies set starts_at = ts, ends_at = ts where starts_at is null;
alter table anomalies alter column starts_at set not null, alter column ends_at set not null;
alter table anomalies drop constraint anomalies_station_id_ts_pollutant_method_key;
alter table anomalies add constraint anomalies_episode_key unique (station_id, pollutant, method, starts_at);
create index anomalies_station_ends on anomalies (station_id, ends_at desc);

-- Fire pixels seen on many different days at (nearly) the same spot are industrial heat sources or
-- gas flares, not open burning. Cells of 0.02 deg (~2 km) absorb VIIRS geolocation jitter.
create or replace view fire_hotspots as
select round(lat * 50) / 50 as lat2, round(lon * 50) / 50 as lon2,
       count(distinct (detected_at at time zone 'utc')::date) as active_days
from fire_events
where detected_at > now() - interval '60 days'
group by 1, 2;

create or replace view fire_events_flagged as
select f.*, coalesce(h.active_days, 0) >= 10 as persistent
from fire_events f
left join fire_hotspots h on h.lat2 = round(f.lat * 50) / 50 and h.lon2 = round(f.lon * 50) / 50;
