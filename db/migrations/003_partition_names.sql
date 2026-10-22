-- drop_old_partitions returned partition OIDs ("29482") instead of names. Applied migrations are
-- never edited, so the fix ships as a new migration.
create or replace function drop_old_partitions(parent regclass, keep interval)
returns setof text language plpgsql as $$
declare
    r record;
    upper_bound timestamptz;
begin
    for r in
        select c.relname::text as name, pg_get_expr(c.relpartbound, c.oid) as bound
        from pg_inherits i join pg_class c on c.oid = i.inhrelid
        where i.inhparent = parent
    loop
        upper_bound := substring(r.bound from 'TO \(''([^'']+)''\)')::timestamptz;
        if upper_bound is not null and upper_bound < now() - keep then
            execute format('drop table %I', r.name);
            return next r.name;
        end if;
    end loop;
end $$;
