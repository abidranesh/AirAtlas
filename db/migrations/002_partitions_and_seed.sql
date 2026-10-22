-- Weekly partitions (Monday 00:00 UTC). Weekly rather than monthly so a 90-day retention keeps at
-- most 97 days on disk instead of ~120.

create or replace function ensure_weekly_partitions(parent regclass, weeks_back int, weeks_ahead int)
returns int language plpgsql as $$
declare
    wk timestamptz;
    created int := 0;
    part text;
begin
    for i in -weeks_back .. weeks_ahead loop
        wk := date_trunc('week', now() at time zone 'utc') at time zone 'utc' + make_interval(weeks => i);
        part := format('%s_w%s', (select relname from pg_class where oid = parent),
                       to_char(wk at time zone 'utc', 'IYYY_IW'));
        if to_regclass(quote_ident(part)) is null then
            execute format('create table %I partition of %s for values from (%L) to (%L)',
                           part, parent, wk, wk + interval '7 days');
            created := created + 1;
        end if;
    end loop;
    return created;
end $$;

-- Drops partitions whose whole range ends before now() - keep. Returns dropped names.
create or replace function drop_old_partitions(parent regclass, keep interval)
returns setof text language plpgsql as $$
declare
    r record;
    upper_bound timestamptz;
begin
    for r in
        select c.oid::regclass as part, pg_get_expr(c.relpartbound, c.oid) as bound
        from pg_inherits i join pg_class c on c.oid = i.inhrelid
        where i.inhparent = parent
    loop
        upper_bound := substring(r.bound from 'TO \(''([^'']+)''\)')::timestamptz;
        if upper_bound is not null and upper_bound < now() - keep then
            execute format('drop table %s', r.part);
            return next r.part::text;
        end if;
    end loop;
end $$;

-- Backfill writes up to 13 weeks back; one week ahead covers the next run.
select ensure_weekly_partitions('readings', 14, 2);
select ensure_weekly_partitions('weather', 14, 2);

insert into regions (id, code, name, country_code, timezone, local_standard, bbox) values
    (1, 'tamil_nadu', 'Tamil Nadu', 'IN', 'Asia/Kolkata', 'in_cpcb_naqi', st_makeenvelope(76.2, 8.0, 80.4, 13.6, 4326)),
    (2, 'kerala',     'Kerala',     'IN', 'Asia/Kolkata', 'in_cpcb_naqi', st_makeenvelope(74.85, 8.17, 77.42, 12.8, 4326)),
    (3, 'uae',        'United Arab Emirates', 'AE', 'Asia/Dubai', 'ae_eaqi', st_makeenvelope(51.5, 22.6, 56.4, 26.1, 4326)),
    (4, 'germany',    'Germany',    'DE', 'Europe/Berlin', 'de_uba_lqi', st_makeenvelope(5.8, 47.2, 15.1, 55.1, 4326));

-- Priority: official monitoring > aggregator copy of official data > model.
insert into sources (id, code, name, kind, priority, license, attribution, url) values
    (1, 'cpcb',       'CPCB via data.gov.in',               'official',   90, 'Government Open Data License - India', 'Central Pollution Control Board, data.gov.in', 'https://www.data.gov.in/'),
    (2, 'uba',        'Umweltbundesamt Air Data API',       'official',   90, 'dl-de/by-2-0', 'Source: Umweltbundesamt', 'https://luftdaten.umweltbundesamt.de/api/air-data/v4/'),
    (3, 'eea',        'European Environment Agency',         'official',   80, 'CC BY 4.0', 'European Environment Agency', 'https://eeadmz1-downloads-api-appservice.azurewebsites.net/'),
    (4, 'openaq',     'OpenAQ',                              'aggregator', 70, 'Per provider (stored per station)', 'OpenAQ and the original data providers', 'https://openaq.org/'),
    (5, 'open_meteo', 'Open-Meteo (CAMS / weather models)',  'model',      10, 'CC BY 4.0', 'Weather and air quality data by Open-Meteo.com', 'https://open-meteo.com/'),
    (6, 'firms',      'NASA FIRMS (VIIRS active fires)',     'satellite',  50, 'NASA open data', 'NASA LANCE FIRMS', 'https://firms.modaps.eosdis.nasa.gov/');
