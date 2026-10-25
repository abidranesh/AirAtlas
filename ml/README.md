# ml

Anomaly detection with cause hints (Phase 7, [docs](../docs/phase-7-anomalies.md)) and forecasting (Phase 9).

```bash
pip install -e ../aqi-engine -e ../ingestion -e ".[dev]"
python -m airatlas_ml detect --region germany --days 10
python -m pytest -q   # set TEST_DATABASE_URL for the Postgres job test
```
