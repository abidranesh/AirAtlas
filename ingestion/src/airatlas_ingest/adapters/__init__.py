"""One module per data source. Each exposes pure `parse_*` functions (tested against recorded
responses) and an adapter class that fetches through a rate-limited HttpClient.

Adapters only produce validated records (models.py); writing to the database is the job's work,
so an adapter can be exercised without a database (`python -m airatlas_ingest probe ...`).
"""

from datetime import timedelta, timezone

# UBA and EEA label German hours in fixed CET (UTC+1) all year, despite UBA's metadata saying
# "CET or CEST". Verified: UBA returns a 02:00 hour on the spring-forward day, and EEA's naive
# Start times match UBA labels at zero offset (MAE 0.24 ug/m3 over 240 hours, 2026-10-10..19).
CET_FIXED = timezone(timedelta(hours=1))
