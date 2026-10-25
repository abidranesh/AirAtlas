# Phase 7: Fires, dust, and anomaly detection with cause hints

## Detection: `ml/src/airatlas_ml/anomaly.py`

For each measured station and pollutant (PM2.5, PM10, NO₂, SO₂, O₃), every hour is compared with a
**same-hour baseline**: the same clock hour ±1 h on each of the previous 7 days, 21 values in all.

    z = (x − median) / max(1.4826·MAD, 0.1·median, 2 µg/m³)

An hour is anomalous when **z ≥ 4**, **x ≥ 1.5 × median**, and x is above a health-relevant floor (PM2.5 25,
PM10 50, NO₂ 50, SO₂ 40, O₃ 120 µg/m³). Consecutive anomalous hours, allowing a one-hour gap, form an
**episode**, stored with its start, end, peak and z-score.

Why these choices:
- **Same hour, not a rolling 24 h median.** Evening NO₂ and afternoon O₃ are normal daily cycles; a
  rolling median would flag them every day (tested).
- **Median and MAD, not mean and standard deviation.** Last week's spike at the same hour must not hide this
  week's (tested). That's the point of a robust estimator.
- **Floors.** "6× the usual" in very clean air (3 → 20 µg/m³) is not a health event (tested).
- **Measured stations only.** Model output is smooth by construction, so a "spike" there says nothing.

Not used: Isolation Forest. With a per-station same-hour baseline, a univariate robust score is easier to
explain and test. A multivariate model would be justified for spotting sensor faults across pollutants;
that's noted as future work.

## Cause hints: `ml/src/airatlas_ml/causes.py`

Each rule returns a hint with a confidence and the evidence behind it. **Hints are correlations in
space and time, not attribution**, and the UI says so.

| Hint | Rule | Confidence |
|---|---|---|
| 🔥 Fires upwind | NASA FIRMS open-burning detections ≤ 150 km, in a 45° cone around the vector-mean wind (Open-Meteo, 6 h before the peak), wind ≥ 1 m/s | ≥ 10 detections or ≥ 50 MW: high · ≥ 3: medium · else low |
| 🏭 Industrial heat upwind | Same, but **persistent** hotspots (≥ 10 distinct days in 60 at a 0.02° cell) | low |
| 🏜️ Desert dust | Modeled CAMS dust at the nearest model point ≥ 40 µg/m³ (PM only) | ≥ 100: high, else medium |
| 🎆 Festival | Peak inside a Deepavali, Bhogi or New Year's Eve window (PM, SO₂) | high |
| 🌫️ Stagnant air | Mean wind < 1.5 m/s and < 0.5 mm rain | medium |
| 🗺️ Area-wide | ≥ 30% of stations **within 100 km** measuring the pollutant spiked within ±3 h | medium |
| 📍 Local | Only this station of ≥ 3 neighbours spiked | low |
| ⚠️ Possible artefact | A one-hour spike at ≥ 8× the usual level, at one station only | low |
| 🚗 Traffic site | NO₂ at a station classified "traffic" | low |

### What real data changed

The first run on 85 days of history exposed three problems, each now fixed and tested:

1. **Gas flares counted as wildfires.** Before the persistence filter, every UAE dust episode also got a fire
   hint. Measured: **93% of UAE detections and 75% of German detections are persistent** (oil and gas
   flares, steelworks), against **4% in Tamil Nadu** (open burning).
2. **"Regional" meant the whole region.** Völklingen and Trier spiked together on 15 August, but 2 of
   ~200 German PM2.5 stations is not "regional". A spike 600 km away also stopped Hamburg's industrial SO₂
   spike from being called "local". The rule now compares **neighbours within 100 km**.
3. **One small fire 150 km away was enough for "medium".** Confidence now scales with the number of
   detections and the fire radiative power.

Also fixed: a station whose baseline is 0 (SO₂ at the detection limit) produced a ratio of `Infinity`,
which is invalid JSON and crashed the German run. The ratio is now omitted.

## Results on live data (episodes ending in the last 85 days, as of 2026-10-25)

| Region | Episodes | Leading hints |
|---|---|---|
| Tamil Nadu | 541 | local 217, fires upwind 194, area-wide 159 |
| Kerala | 118 | area-wide 98, stagnation 17 |
| UAE | 216 | **desert dust 209**, area-wide 182, industrial heat 125 |
| Germany | ~4,200 | stagnation, industrial heat, traffic (NO₂) |

Examples:
- **Manali, Chennai:** SO₂ spikes of 200–430 µg/m³ against a ~10 µg/m³ baseline, hinted "local". Manali is
  Chennai's refinery and petrochemical belt.
- **Arabian Ranches, Dubai:** PM2.5 of 133 vs a baseline of 38, with modeled dust peaking at 269 µg/m³.

## Where it runs

- `.github/workflows/anomalies.yml`: every 3 h at :55, after the modeled, fire and weather ingestion; one job
  per region; re-detects episodes ending in the last 10 days. Episodes ending in that window are replaced,
  and detection starts 3 days earlier so an episode straddling the boundary is rebuilt whole. A Postgres
  test checks that re-runs are idempotent.
- API: `/api/v1/regions/{r}/anomalies?days=`, `/api/v1/stations/{id}/anomalies`, `/api/v1/regions/{r}/fires?hours=`
  (GeoJSON, `persistent` flag from the `fire_events_flagged` view).
- UI: a "Pollution spikes" card per region (a stacked daily timeline by leading hint, plus the latest
  episodes), a **Fires (48 h)** map layer (open burning filled, persistent heat sources hollow), and shaded
  spike windows on station trend charts.
