# aqi-engine

Pluggable, stdlib-only AQI engine. Raw concentrations go in; any supported standard comes out.

| Code | Standard | Default for |
|------|----------|-------------|
| `in_cpcb_naqi` | India CPCB National AQI (0–500) | Tamil Nadu, Kerala |
| `de_uba_lqi` | Umweltbundesamt Luftqualitätsindex, 2025 bands (5 levels) | Germany |
| `eu_eaqi` | European AQI, EEA 2025 revision (6 levels) | common scale; secondary for Germany |
| `ae_eaqi` | Emirati AQI, NCM 2023 (0–500) | UAE |
| `who_2021_pm25` | PM2.5 vs WHO 2021 guideline and interim targets | common scale |

Breakpoint tables, sources and discrepancies: [docs/aqi-standards](../docs/aqi-standards/README.md) (generated from `src/airatlas_aqi/tables/*.json`).

## Usage

```python
from datetime import datetime, timezone
from airatlas_aqi import Averaging as A, Pollutant as P, get_standard, standard_for, convert

# From averaged concentrations (canonical units: ug/m3, CO in mg/m3)
r = get_standard("in_cpcb_naqi").compute({(P.PM25, A.H24): 34, (P.PM10, A.H24): 121, (P.NO2, A.H24): 8})
r.value, r.category.label, r.dominant        # (114, 'Moderately polluted', (P.PM10,))

# From hourly series keyed by UTC hour start; each standard applies its own averaging and completeness rules
r = standard_for("uae").evaluate({P.PM25: hourly_pm25, P.NO2: hourly_no2}, at=datetime(2026, 7, 1, 12, tzinfo=timezone.utc))

# Same data on the common scale
standard_for("uae", "eu_eaqi").evaluate(...)

convert(40, P.NO2, "ppb", temp_c=20)          # 76.5 ug/m3 at EU reference conditions
```

A result's `status` is `ok`, `partial` (computed without key pollutants), or `insufficient_data`. In the last case
`value` is `None` and the UI shows "data unavailable". The engine never returns a 0 for missing data.

## Adding a standard

1. Add `src/airatlas_aqi/tables/<code>.json` with sources, categories, breakpoints and rules. Use `method: step`,
   `continuous` or `segments`.
2. If the standard is purely banded, subclass `StepStandard` with just `code = "<code>"`. Otherwise implement
   `sub_indices()` (and `from_hourly()` if it has its own validation rules).
3. Register it in `registry.py` (`STANDARDS`, plus `LOCAL_STANDARD` if it is a region default).
4. Run `python -m airatlas_aqi.docgen`, then add tests against the standard's official worked examples.
   The shared invariant tests (monotonic sub-index, contiguous categories, invalid input rejected, docs not stale)
   run automatically for every registered standard.

## Tests

```bash
cd aqi-engine
python -m pytest -q
```

`tests/fixtures/uba_live_index.json` holds 755 (pollutant, value, UBA class) pairs and 400 station-hours from UBA's
live API. The German index is checked against the agency's own output, not just against a table we transcribed.
