# Running and operating ScamSERP

Use Python 3.11+ and the project launch scripts. The CLI loads the project `.env`; an already exported environment variable takes precedence. Restart after configuration changes. Credentials are never included in releases.

```powershell
.\scripts\start.ps1 -Port 8000
```

For continuous local collection, set `SCAMSERP_MODE=live`, a valid `SERP_API_KEY` or `SERPAPI_API_KEY`, and `SCAMSERP_SCHEDULER=true`. Keep the web process running; the application does not run after the computer shuts down or sleeps. One scheduler lock prevents duplicate owners. The first tick runs at startup; later ticks default to six hours. A tick collects at most six due surface tasks, respecting daily/monthly attempt reservations. Autocomplete is national, while Search and Local use six city proxies. Empty/failed tasks have a cooldown and do not prevent other engines being sampled.

Alternatively leave the web scheduler off and use a dedicated process:

```powershell
.\.venv\Scripts\python.exe -m scamserp.cli scheduler
.\.venv\Scripts\python.exe -m scamserp.cli coverage
```

Docker: `docker compose up --build -d` runs the web app. With the embedded scheduler off, `docker compose --profile scheduler up --build -d` also starts a dedicated scheduler. For unattended Windows operation, run the launch command with the project as working directory under an operator-managed service or scheduled task; use the configured account and protect its `.env`. No system startup task is installed automatically.

The current caps are safeguards, not sufficient research coverage. `/api/coverage` estimates the minimum requests for all active query/location/engine cells at their 7/14/30-day tiers. Set `SCAMSERP_SCHEDULE_LIMIT` and `SCAMSERP_SCHEDULE_HOURS` for the approved plan; check caps and actual provider credits. Enrichment is limited by `SCAMSERP_ADS_REQUESTS_PER_RUN` (default 2). Public map searches and explicitly confirmed targeted lookups share the same caps. Viewing stored dashboards does not spend provider credits.

Configure an enabled Maps JavaScript API browser key, restricted to the intended origins and API. Restrict the SerpApi key to server use. Geolocation needs HTTPS outside localhost and user/device permission; the continuous position stream stays in browser memory.

For public operation, place the app behind a TLS reverse proxy, keep admin endpoints protected, avoid multiple unsupervised web workers, and mount durable storage at `SCAMSERP_DATA_DIR`. Health probe: `/healthz`; collection status: `/api/coverage`; API schema: `/docs`. Monitor scheduler heartbeat, gaps, caps and review backlog. Raw evidence and database exports should not be exposed as static public files.

Back up the database using SQLite's backup API, alongside the compressed raw archive directory and generated digests. Do not copy an actively written SQLite database file alone: WAL contents may be omitted. Test restoration to a separate data directory before replacing live data. Additive schema migrations run on startup; back up before upgrading and avoid old application versions writing to the upgraded database.
