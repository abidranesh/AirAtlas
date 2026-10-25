"""Insight pages, computed only from stored measurements.

Every function returns its numbers together with the data basis (stations, period, days) so the
page can say exactly what a statement rests on. Nothing here is hand-written: when the data is not
there, the result says so instead of filling in.
"""

from __future__ import annotations

import statistics
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from . import db

# ---------------------------------------------------------------------------------------------
# small statistics helpers (tested)


def spearman(x: list[float], y: list[float]) -> float | None:
    """Spearman rank correlation with average ranks for ties; None for fewer than 10 pairs."""
    if len(x) != len(y) or len(x) < 10:
        return None

    def ranks(v):
        a = np.asarray(v, dtype=float)
        order = a.argsort(kind="mergesort")
        r = np.empty(len(a))
        r[order] = np.arange(1, len(a) + 1)
        for val in np.unique(a):  # average ranks for ties
            idx = a == val
            r[idx] = r[idx].mean()
        return r

    rx, ry = ranks(x), ranks(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def median_or_none(v: list[float]) -> float | None:
    v = [x for x in v if x is not None]
    return float(statistics.median(v)) if v else None


KERALA_SEASONS = {  # India Meteorological Department seasons
    1: "Winter", 2: "Winter", 3: "Pre-monsoon", 4: "Pre-monsoon", 5: "Pre-monsoon",
    6: "Southwest monsoon", 7: "Southwest monsoon", 8: "Southwest monsoon", 9: "Southwest monsoon",
    10: "Northeast monsoon", 11: "Northeast monsoon", 12: "Northeast monsoon",
}


def heating_season(month: int) -> bool:
    """German heating season (Heizperiode), October to March."""
    return month >= 10 or month <= 3


# ---------------------------------------------------------------------------------------------
# Festivals

# Hour of the festival "night" relative to the local event date, for aligning curves:
# Deepavali fireworks peak in the evening; Bhogi bonfires burn at dawn; New Year's Eve at midnight.
FESTIVAL_ANCHOR_HOUR = {"deepavali": 20, "bhogi": 6, "new_years_eve": 24}
FESTIVAL_NAMES = {"deepavali": "Deepavali", "bhogi": "Bhogi", "new_years_eve": "New Year's Eve"}


def festival_kind(label: str) -> str:
    return label.rsplit("_", 1)[0]


def festivals() -> dict:
    holds = db.fetch("""select h.label, g.code as region, g.timezone, h.starts_at, h.ends_at
                        from retention_holds h join regions g on g.id = h.region_id
                        where h.ends_at < now() order by h.starts_at""")
    events = []
    for h in holds:
        kind = festival_kind(h["label"])
        # The window is the event day +-3 days, so the event date is the window start + 3 days (local).
        tz = ZoneInfo(h["timezone"])
        event_day = h["starts_at"].astimezone(tz).date() + timedelta(days=3)
        anchor = datetime.combine(event_day, time(0), tz) + timedelta(hours=FESTIVAL_ANCHOR_HOUR[kind])
        # Hourly means across the region's measured stations; current raw data plus the permanent archive.
        rows = db.fetch("""with r as (
                               select station_id, ts, pm25, pm10 from readings
                               where ts >= %(s)s and ts < %(e)s
                               union
                               select station_id, ts, pm25, pm10 from readings_archive
                               where ts >= %(s)s and ts < %(e)s)
                           select date_trunc('hour', r.ts) as hour, avg(r.pm25)::float8 as pm25, avg(r.pm10)::float8 as pm10,
                                  count(distinct r.station_id) filter (where r.pm25 is not null) as n
                           from r join stations s on s.id = r.station_id
                           where s.kind <> 'modeled' and s.region_id = (select id from regions where code = %(g)s)
                           group by 1 order by 1""",
                        {"s": h["starts_at"], "e": h["ends_at"], "g": h["region"]})
        series = [{"h": round((r["hour"] - anchor).total_seconds() / 3600), "pm25": r["pm25"], "pm10": r["pm10"], "n": r["n"]}
                  for r in rows if r["pm25"] is not None]
        baseline = median_or_none([p["pm25"] for p in series if -72 <= p["h"] <= -24])
        night = [p for p in series if -6 <= p["h"] <= 12]
        peak = max(night, key=lambda p: p["pm25"], default=None)
        # Daily comparison (works for years without hourly data): event day vs median of days -10..-4.
        daily = db.fetch_one("""select avg(d.pm25_mean) filter (where d.day = %(ev)s)::float8 as event_day,
                                       percentile_cont(0.5) within group (order by d.pm25_mean)
                                         filter (where d.day between %(ev)s - 10 and %(ev)s - 4)::float8 as before,
                                       count(distinct d.station_id) filter (where d.day = %(ev)s) as n
                                from readings_daily d join stations s on s.id = d.station_id
                                where s.kind <> 'modeled' and s.region_id = (select id from regions where code = %(g)s)
                                  and d.day between %(ev)s - 10 and %(ev)s + 1 and d.pm25_mean is not null""",
                             {"ev": event_day + (timedelta(days=1) if kind == "new_years_eve" else timedelta()), "g": h["region"]})
        events.append({
            "label": h["label"], "kind": kind, "name": FESTIVAL_NAMES[kind], "year": int(h["label"].rsplit("_", 1)[1]),
            "region": h["region"], "event_day": event_day, "anchor": anchor, "series": series,
            "hourly": {"baseline_pm25": baseline, "peak_pm25": peak["pm25"] if peak else None,
                       "peak_hour": peak["h"] if peak else None, "stations": max((p["n"] for p in series), default=0),
                       "ratio": (peak["pm25"] / baseline) if peak and baseline else None},
            "daily": {**daily, "ratio": (daily["event_day"] / daily["before"]) if daily["event_day"] and daily["before"] else None},
        })
    return {"events": events,
            "method": {"alignment": "hours from the festival night: Deepavali 20:00, Bhogi 06:00, New Year 00:00, local time",
                       "baseline": "median hourly PM2.5 from 72 to 24 hours before",
                       "peak": "highest hourly regional mean from 6 hours before to 12 hours after",
                       "daily": "event-day mean vs median of days 10 to 4 before (New Year: 1 January vs mid/late December)"}}


# ---------------------------------------------------------------------------------------------
# Kerala: monsoon washout


def kerala_monsoon() -> dict:
    daily = db.fetch("""with pm as (
                            select d.day, avg(d.pm25_mean)::float8 as pm25, avg(d.pm10_mean)::float8 as pm10,
                                   count(distinct d.station_id) as n
                            from readings_daily d join stations s on s.id = d.station_id
                            where s.region_id = 2 and s.kind <> 'modeled' and (d.n_hours is null or d.n_hours >= 18)
                            group by 1),
                        rain as (
                            select w.day, avg(w.precip_sum)::float8 as rain_mm
                            from weather_daily w join stations s on s.id = w.station_id
                            where s.region_id = 2 and s.kind = 'modeled' group by 1)
                        select pm.day, pm.pm25, pm.pm10, pm.n, rain.rain_mm
                        from pm join rain using (day) order by pm.day""")
    pairs = [d for d in daily if d["pm25"] is not None and d["rain_mm"] is not None]
    rainy = [d["pm25"] for d in pairs if d["rain_mm"] >= 10]
    dry = [d["pm25"] for d in pairs if d["rain_mm"] < 1]
    months: dict[str, dict] = {}
    for d in daily:
        key = d["day"].strftime("%Y-%m")
        m = months.setdefault(key, {"month": key, "pm25": [], "pm10": [], "rain": []})
        for k, src in (("pm25", "pm25"), ("pm10", "pm10"), ("rain", "rain_mm")):
            if d[src] is not None:
                m[k].append(d[src])
    monthly = [{"month": k, "season": KERALA_SEASONS[int(k[5:])],
                "pm25": float(np.mean(v["pm25"])) if v["pm25"] else None,
                "pm10": float(np.mean(v["pm10"])) if v["pm10"] else None,
                "rain_mm": float(np.sum(v["rain"])) if v["rain"] else None,
                "days": len(v["rain"])} for k, v in sorted(months.items())]
    by_season = {}
    for s in dict.fromkeys(KERALA_SEASONS.values()):
        vals = [d for d in pairs if KERALA_SEASONS[d["day"].month] == s]
        by_season[s] = {"pm25_median": median_or_none([d["pm25"] for d in vals]),
                        "rain_mm_per_day": float(np.mean([d["rain_mm"] for d in vals])) if vals else None, "days": len(vals)}
    return {
        "monthly": monthly, "by_season": by_season,
        "rain_vs_pm25": {"spearman": spearman([d["rain_mm"] for d in pairs], [d["pm25"] for d in pairs]),
                         "rainy_day_median": median_or_none(rainy), "rainy_days": len(rainy),
                         "dry_day_median": median_or_none(dry), "dry_days": len(dry)},
        "basis": {"days": len(pairs), "first": pairs[0]["day"] if pairs else None, "last": pairs[-1]["day"] if pairs else None,
                  "max_stations": max((d["n"] for d in pairs), default=0),
                  "pm": "daily means of Kerala PCB monitors (via OpenAQ), days with >= 18 hours",
                  "rain": "Open-Meteo ERA5 daily precipitation, averaged over Kerala's 14 district points"},
    }


# ---------------------------------------------------------------------------------------------
# UAE: desert dust


def uae_dust() -> dict:
    # Dust and wind are taken at the model point nearest each measured sensor, not the regional
    # maximum: somewhere in the desert there is always dust, which would make every day "dusty".
    daily = db.fetch("""with sensors as (
                            select id from stations where region_id = 3 and kind <> 'modeled' and active),
                        nearest as (
                            select distinct m.id from stations s
                            cross join lateral (select id from stations m where m.region_id = 3 and m.kind = 'modeled'
                                                order by m.geom <-> s.geom limit 1) m
                            where s.id in (select id from sensors)),
                        m as (
                            select (r.ts at time zone 'Asia/Dubai')::date as day, avg(r.pm25)::float8 as pm25,
                                   count(distinct r.station_id) as n
                            from readings r where r.station_id in (select id from sensors) and r.pm25 is not null group by 1),
                        md as (
                            select (r.ts at time zone 'Asia/Dubai')::date as day, avg(r.dust)::float8 as dust,
                                   max(r.dust)::float8 as dust_peak, avg(r.pm10)::float8 as model_pm10
                            from readings r where r.station_id in (select id from nearest) group by 1),
                        w as (
                            select (w.ts at time zone 'Asia/Dubai')::date as day, avg(w.wind_ms)::float8 as wind
                            from weather w where w.station_id in (select id from nearest) group by 1)
                        select md.day, m.pm25, m.n, md.dust, md.dust_peak, md.model_pm10, w.wind
                        from md left join m using (day) left join w using (day) order by md.day""")
    pairs = [d for d in daily if d["pm25"] is not None and d["dust"] is not None]
    # Dust near Dubai is never "absent" (daily means ~25-235 ug/m3 in summer), so fixed thresholds
    # would call every day dusty. Compare the dustiest quarter of days with the clearest quarter.
    q1, q3 = (np.percentile([d["dust"] for d in pairs], [25, 75]).tolist() if pairs else (None, None))
    dusty = [d["pm25"] for d in pairs if d["dust"] >= q3]
    clear = [d["pm25"] for d in pairs if d["dust"] <= q1]
    episodes = db.fetch("""select s.name as station, a.ts as peak_at, a.value as peak, a.baseline,
                                  (a.cause_hints->0->'evidence'->>'dust_max')::float8 as dust_max
                           from anomalies a join stations s on s.id = a.station_id
                           where s.region_id = 3 and a.cause_hints->0->>'kind' = 'dust'
                           order by a.value desc limit 10""")
    total = db.fetch_one("""select count(*) as n, count(*) filter (where a.cause_hints @> '[{"kind": "dust"}]') as dust
                            from anomalies a join stations s on s.id = a.station_id where s.region_id = 3""")
    return {
        "daily": daily,
        "dust_vs_pm25": {"spearman": spearman([d["dust"] for d in pairs], [d["pm25"] for d in pairs]),
                         "dusty_day_median": median_or_none(dusty), "dusty_days": len(dusty),
                         "clear_day_median": median_or_none(clear), "clear_days": len(clear),
                         "wind_vs_dust": spearman([d["wind"] for d in daily if d["wind"] is not None and d["dust"] is not None],
                                                  [d["dust"] for d in daily if d["wind"] is not None and d["dust"] is not None]),
                         "thresholds": {"dusty_q3": q3, "clear_q1": q1}},
        "spikes": {"total": total["n"], "with_dust_hint": total["dust"], "top": episodes},
        "basis": {"days": len(daily), "paired_days": len(pairs),
                  "measured": "PM2.5 from low-cost AirGradient sensors (OpenAQ); no open measured PM10 exists in the UAE",
                  "modeled": "CAMS dust and PM10 via Open-Meteo at the model points nearest the sensors (daily mean)",
                  "first": daily[0]["day"] if daily else None, "last": daily[-1]["day"] if daily else None},
    }


# ---------------------------------------------------------------------------------------------
# Germany: heating season, city vs rural

GERMANY_GROUPS = [("urban", "traffic"), ("urban", "background"), ("suburban", "background"), ("rural", "background")]


def germany_seasons() -> dict:
    rows = db.fetch("""select s.setting, s.station_type, date_trunc('month', d.day)::date as month,
                              avg(d.pm25_mean)::float8 as pm25, avg(d.pm10_mean)::float8 as pm10, avg(d.no2_mean)::float8 as no2,
                              count(distinct d.station_id) as stations
                       from readings_daily d join stations s on s.id = d.station_id
                       where s.region_id = 4 and s.kind = 'reference' and (s.setting, s.station_type) in
                             (('urban','traffic'), ('urban','background'), ('suburban','background'), ('rural','background'))
                       group by 1, 2, 3 order by 3""")
    monthly = [{"group": f"{r['setting']} {r['station_type']}", **{k: r[k] for k in ("month", "pm25", "pm10", "no2", "stations")}}
               for r in rows]
    comparison = []
    for setting, stype in GERMANY_GROUPS:
        g = [r for r in rows if r["setting"] == setting and r["station_type"] == stype]
        entry = {"group": f"{setting} {stype}", "stations": max((r["stations"] for r in g), default=0)}
        for p in ("pm25", "pm10", "no2"):
            heat = [r[p] for r in g if r[p] is not None and heating_season(r["month"].month)]
            summer = [r[p] for r in g if r[p] is not None and not heating_season(r["month"].month)]
            h, s = (float(np.mean(heat)) if heat else None), (float(np.mean(summer)) if summer else None)
            entry[p] = {"heating": h, "summer": s, "ratio": h / s if h and s else None}
        comparison.append(entry)
    span = db.fetch_one("""select min(d.day) as first, max(d.day) as last from readings_daily d
                           join stations s on s.id = d.station_id where s.region_id = 4 and s.kind = 'reference'""")
    return {"monthly": monthly, "comparison": comparison,
            "basis": {**span, "seasons": "heating season Oct-Mar vs summer Apr-Sep, means of monthly means",
                      "stations": "UBA classification of each station (setting x type)"}}


# ---------------------------------------------------------------------------------------------
# Tamil Nadu: industrial vs residential

# Land use is labelled only where the station's own name or a well-documented location says so;
# everything else is left unclassified rather than guessed.
TN_LAND_USE = [
    ("industrial", "SIPCOT Industrial Park", "named state industrial estate (SIPCOT)"),
    ("industrial", "SIDCO", "named small-industries estate (SIDCO)"),
    ("industrial", "Manali", "Manali petrochemical and refinery belt, north Chennai (AirAtlas label)"),
    ("residential", "Res. Area", "named residential area in the station name"),
]


def tn_land_use_of(name: str) -> tuple[str, str] | None:
    for use, needle, basis in TN_LAND_USE:
        if needle in name:
            return use, basis
    return None


def tamil_nadu_land_use() -> dict:
    stations = db.fetch("select id, name from stations where region_id = 1 and kind = 'reference' and active order by name")
    classified = {s["id"]: (*tn_land_use_of(s["name"]), s["name"]) for s in stations if tn_land_use_of(s["name"])}
    ids = list(classified)
    if not ids:
        return {"groups": [], "stations": [], "diurnal": [], "basis": {"note": "no classifiable stations"}}
    per_station = db.fetch("""select d.station_id, avg(d.pm25_mean)::float8 as pm25, avg(d.pm10_mean)::float8 as pm10,
                                     avg(d.so2_mean)::float8 as so2, avg(d.no2_mean)::float8 as no2, count(*) as days,
                                     min(d.day) as first, max(d.day) as last
                              from readings_daily d where d.station_id = any(%s) and d.day > current_date - 365
                              group by 1""", (ids,))
    diurnal = db.fetch("""select d.station_id, extract(hour from (r.ts at time zone 'Asia/Kolkata'))::int as hour,
                                 avg(r.so2)::float8 as so2, avg(r.pm25)::float8 as pm25, avg(r.no2)::float8 as no2
                          from readings r join (select unnest(%s::int[]) as station_id) d using (station_id)
                          group by 1, 2 order by 2""", (ids,))
    station_rows = [{"id": r["station_id"], "name": classified[r["station_id"]][2], "use": classified[r["station_id"]][0],
                     "basis": classified[r["station_id"]][1], **{k: r[k] for k in ("pm25", "pm10", "so2", "no2", "days", "first", "last")}}
                    for r in per_station]
    groups = []
    for use in ("industrial", "residential"):
        g = [r for r in station_rows if r["use"] == use]
        groups.append({"use": use, "stations": len(g),
                       **{p: median_or_none([r[p] for r in g]) for p in ("pm25", "pm10", "so2", "no2")}})
    use_of = {i: c[0] for i, c in classified.items()}
    profile: dict[tuple[str, int], list[dict]] = {}
    for r in diurnal:
        profile.setdefault((use_of[r["station_id"]], r["hour"]), []).append(r)
    diurnal_out = [{"use": use, "hour": hour, **{p: median_or_none([x[p] for x in v]) for p in ("so2", "pm25", "no2")}}
                   for (use, hour), v in sorted(profile.items(), key=lambda kv: (kv[0][0], kv[0][1]))]
    return {"groups": groups, "stations": sorted(station_rows, key=lambda r: (r["use"], r["name"])), "diurnal": diurnal_out,
            "basis": {"period": "last 365 days of daily means; diurnal profile from the last 90 days of hourly data",
                      "rules": [{"use": u, "matches": n, "basis": b} for u, n, b in TN_LAND_USE],
                      "unclassified": len(stations) - len(classified)}}
