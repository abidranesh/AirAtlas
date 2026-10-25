# Phase 8: Insight pages

Five pages under `/insights`, each computed by `api/airatlas_api/insights.py` from data AirAtlas has
stored, and served at `GET /api/v1/insights/{name}` (CDN-cached daily). **No number on these pages is
typed by hand.** The headline sentences are templates in `web/src/lib/insights.ts`, filled from the
response. They only make a directional claim ("rainier days had cleaner air", "higher in the heating
season") when the numbers show it, and they return nothing when the data isn't there (all tested).
Every page shows its sample size, period and method, plus a caveat box.

| Page | Endpoint | Question |
|---|---|---|
| Festival nights | `festivals` | How much does PM2.5 rise on Deepavali, Bhogi and New Year's Eve? |
| Kerala's monsoon washout | `kerala-monsoon` | Does rain lower particulate levels? |
| UAE dust days | `uae-dust` | Do modeled dust days show up in measured PM2.5? |
| Germany: heating season, city vs countryside | `germany-seasons` | Winter vs summer, traffic vs rural |
| Tamil Nadu: industrial vs residential | `tamil-nadu-land-use` | Do industrial monitors read higher? |

## Methods

**Festivals.** The windows come from `retention_holds`, the same table that keeps festival hours in
`readings_archive` beyond the 90-day retention. Each window is aligned to a local "festival hour":
Deepavali 20:00, Bhogi 06:00 and New Year 00:00. Then:

- **Baseline:** the median hourly regional mean PM2.5 from 72 to 24 h before.
- **Peak:** the highest hourly regional mean from 6 h before to 12 h after.
- **Daily comparison:** the event-day mean from `readings_daily` against the median of days −10 to −4.
  For New Year it compares 1 January with mid/late December.

Measured stations only. A window without data is listed as missing, never estimated.

**Kerala monsoon.** Inputs are daily Kerala PM means (OpenAQ, days with ≥ 18 hours) and ERA5 daily rain
(Open-Meteo), averaged over the 14 district points. The comparison uses three measures:

- the Spearman rank correlation between daily rain and PM2.5;
- the median PM2.5 on rainy days (≥ 10 mm) against dry days (< 1 mm);
- medians by India Meteorological Department season.

Spearman, not Pearson, because rain is heavily skewed: a few 80 mm days would dominate a linear fit.

**UAE dust.** Dust and wind are taken at the **model point nearest each sensor**, not the regional maximum.
Somewhere in the desert there is always dust, so the maximum made every day "dusty". Dust near Dubai never
drops to zero (daily means ~25–235 µg/m³), so fixed thresholds don't work either. The page compares the
dustiest quarter of days with the clearest quarter.

**Germany.** Monthly means are grouped by the Umweltbundesamt's own station classification (setting ×
type). The heating season (Oct–Mar) is compared with summer (Apr–Sep) as means of monthly means, so a
month with more stations reporting doesn't weigh more.

**Tamil Nadu land use.** CPCB publishes no land-use class per station, so a class is assigned **only** when:

- the station name states it ("SIPCOT Industrial Park", "SIDCO", "Res. Area"); or
- the station is in the documented Manali petrochemical belt. This one is labelled as an AirAtlas
  classification.

The other 12 stations stay unclassified rather than guessed. Inputs are 365-day station means (group
median) and a diurnal profile from the last 90 days of hourly data.

## What the data shows (as of 2026-10-25)

- **New Year's Eve, Germany.** The regional mean PM2.5 at midnight rose to 31× the pre-festival baseline
  in 2022/23, 24× in 2023/24, 8× in 2024/25 and 10× in 2025/26, across 250–320 stations. That is the
  clearest signal in the project.
- **Deepavali, Tamil Nadu.**
  - 2025: an hourly peak of 435 µg/m³, 13× baseline (14 stations); the daily mean was 84 vs 32 µg/m³.
  - 2024: a single station only, so it's an anecdote.
  - Kerala 2025: no clear rise (1.4×, 6 stations).
- **Kerala monsoon.** ρ = −0.68 between daily rain and PM2.5 over 581 days. The rainy-day median is
  22 µg/m³ against 43 µg/m³ on dry days, and the southwest-monsoon median is 23 against 45 in winter.
- **UAE dust.**
  - On the dustiest quarter of days, measured PM2.5 was *lower* (median 30 vs 51 µg/m³, ρ = −0.46).
    Dusty days are windy days (wind vs dust ρ = +0.69), and dust is coarse while the UAE's open sensors
    measure only PM2.5.
  - This finding changed the anomaly detector. The dust hint had fired on 210 of 216 UAE spikes because
    dust is always present. It now also needs modeled dust at ≥ 1.5× its own 7-day median, and fires on 70.
- **Germany.**
  - PM2.5 is 1.4–1.5× higher in the heating season in all four groups.
  - NO₂ at urban-traffic stations (22 µg/m³) is 4.6× the rural background level and flat across seasons,
    consistent with exhaust rather than heating.
- **Tamil Nadu.** Industrial monitors' median SO₂ is 32 µg/m³ against 16 at the one explicitly residential
  monitor, while PM2.5 is similar (30 vs 29). With n = 1 residential, the page says it is a comparison
  against a single site.

These numbers are a snapshot. The pages recompute daily and will change as history accumulates.

## Limits and honesty notes

- Correlations are not causes. Each page's caveat names the likely confounders: winter mixing height,
  monsoon winds, and weather on festival nights.
- UAE PM2.5 comes from low-cost sensors and the dust is a model. There is no open measured PM10 in the UAE.
- India's hourly festival history depends on OpenAQ's archive; the CPCB feed reports sub-indices, not
  concentrations. Bhogi has daily data at one station only, so it appears in the table but carries no
  hourly claim.
- The festivals query scans the archive and takes ~10 s cold, which is why the endpoint is cached daily.

## Tests

- `api/tests/test_insights.py`: Spearman (monotonic, ties checked by hand, too few points, constant input,
  noise), heating-season months, festival labels, and the land-use rules, including leaving an unnamed
  station unclassified.
- `api/tests/test_api.py::test_insights_endpoints`: a seeded New Year's Eve fireworks spike in
  `readings_archive` must come back as a 24× peak at hour 0; unclassified stations add nothing; unknown
  names give 422; empty data still returns a basis.
- `web/src/lib/insights.test.ts`: headline wording, and that no directional sentence appears when the data
  points the other way.
