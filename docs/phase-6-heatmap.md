# Phase 6: Interpolated heatmap

`GET /api/v1/regions/{region}/heatmap.png?scale=…` returns a transparent PNG covering the region's bounding
box. Region pages show it through the **Heatmap** toggle.

## Method

1. **What is interpolated.** PM2.5, taken from each station exactly as the selected standard consumes
   it: the 24-hour rolling mean for CPCB, the UAE index and WHO, and the 1-hour value for UBA and the
   European AQI. The engine's own `from_hourly` produces it, with the same completeness rules (e.g. CPCB
   needs ≥ 16 valid hours). Stations without a valid value under that standard are left out, as are stale ones (> 24 h).
2. **Inverse distance weighting** over the k = 8 nearest points:
   `v = Σ qᵢ·vᵢ/dᵢ² / Σ qᵢ/dᵢ²`, with trust weights **q = 1.0** for official monitors, **0.6** for low-cost
   sensors and **0.25** for model points. Measurements dominate where they exist, and models fill gaps.
   A cell within 0.5 km of a point takes that point's value.
3. **No extrapolation.** Cells farther than the search radius from every point stay transparent (60 km in
   Germany and Tamil Nadu, 50 km in Kerala, and 100 km in the UAE, where sensors are sparse and the model
   grid is 0.75°). Cells outside the admin boundaries (buffered ~2 km for simplified coastlines) are masked.
4. **Colours come from the engine.** Each distinct interpolated value, rounded to 0.1 µg/m³, is classified
   with `standard.sub_indices`, so the overlay applies the same truncation and rounding as the markers and
   can never disagree with them.
5. **Projection.** Image rows are spaced evenly in Web Mercator y, not latitude. Leaflet stretches an image
   linearly between the bbox corners in Mercator, so rows spaced in latitude would drift by up to a cell or
   more across Germany's 47–55° N span.

| Region | Cell size | Grid | Radius |
|---|---|---|---|
| Germany | 5 km | 130 × 175 | 60 km |
| Tamil Nadu | 4 km | 115 × 155 | 60 km |
| Kerala | 3 km | 94 × 171 | 50 km |
| UAE | 5 km | 99 × 77 | 100 km |

## Cost

Pure numpy, in chunks of 4,096 cells against all points. The region mask is computed once per warm
function instance with PostGIS and memoised. Measured on live data: 0.6–1.9 s per region, with responses of
0.4–1 KB, because the PNG is mostly a few flat colours. Responses use the same CDN cache as the other live
data (until the next ingestion at :25).

## Limitations, stated on the page

- IDW is a deterministic smoother, not a physical model. It knows nothing about wind, terrain or sources,
  and it cannot exceed the range of the nearby observations: every estimate is a convex combination of
  observed values, which a test asserts.
- In India, until OpenAQ history is backfilled, the overlay is driven by model points (trust 0.25 still
  wins when they are the only data). The info header `X-Heatmap-Info` reports how many measured points were used.
- Only PM2.5 is interpolated. NO₂ and O₃ vary over much shorter distances than station spacing allows.

## Tests

`api/tests/test_idw.py` covers: exact at a station, the midpoint of two equal points is their mean, trust
weighting, no values beyond the radius, k-nearest locality, results bounded by the observed range, even
Mercator row spacing, PNG round trip with CRC checks, engine-based colouring, and the same 40 µg/m³ being
"Satisfactory" on CPCB but "Interim target 2" against WHO. `test_api.py::test_heatmap_png` checks the
endpoint against Postgres, including that a 30-hour-old station is excluded.
