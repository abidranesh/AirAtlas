-- Partition helpers resolved partition names through search_path. With a second schema holding
-- same-named tables (the integration tests' throwaway schema), ensure_weekly_partitions saw
-- public's partitions and skipped creating its own. Always qualify with the parent's schema.

create or replace function ensure_weekly_partitions(parent regclass, weeks_back int, weeks_ahead int)
returns int language plpgsql as $$
declare
    nsp text;
    rel text;
    wk timestamptz;
    part text;
    created int := 0;
begin
    select n.nspname, c.relname into nsp, rel
    from pg_class c join pg_namespace n on n.oid = c.relnamespace where c.oid = parent;
    for i in -weeks_back .. weeks_ahead loop
        wk := date_trunc('week', now() at time zone 'utc') at time zone 'utc' + make_interval(weeks => i);
        part := format('%s_w%s', rel, to_char(wk at time zone 'utc', 'IYYY_IW'));
        if to_regclass(format('%I.%I', nsp, part)) is null then
            execute format('create table %I.%I partition of %s for values from (%L) to (%L)',
                           nsp, part, parent, wk, wk + interval '7 days');
            created := created + 1;
        end if;
    end loop;
    return created;
end $$;

create or replace function drop_old_partitions(parent regclass, keep interval)
returns setof text language plpgsql as $$
declare
    r record;
    upper_bound timestamptz;
begin
    for r in
        select n.nspname::text as nsp, c.relname::text as name, pg_get_expr(c.relpartbound, c.oid) as bound
        from pg_inherits i
        join pg_class c on c.oid = i.inhrelid
        join pg_namespace n on n.oid = c.relnamespace
        where i.inhparent = parent
    loop
        upper_bound := substring(r.bound from 'TO \(''([^'']+)''\)')::timestamptz;
        if upper_bound is not null and upper_bound < now() - keep then
            execute format('drop table %I.%I', r.nsp, r.name);
            return next r.name;
        end if;
    end loop;
end $$;

-- Re-run partition creation for this schema (no-op where partitions already exist).
select ensure_weekly_partitions('readings', 13, 2);
select ensure_weekly_partitions('weather', 13, 2);
