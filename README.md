# ScamSERP

An evidence-led audit of search results for Indian help queries, with phone, website and message lookup, an India risk map, annotated search evidence, a source registry and a review workspace.

This is a runnable FastAPI + SQLite application with a responsive, dependency-free browser UI. The default demo uses **clearly labelled synthetic observations**. It is suitable for local demonstration and supervised pilot work; the public launch requirements in [docs/LAUNCH_GATES.md](docs/LAUNCH_GATES.md) remain open. The registry has 40 candidate entities, of which four have assistant source checks. It does not contain 40 independently hand-verified entities or a real-world labelled evaluation set.

## Start on Windows

Install Python 3.11 or newer. Open PowerShell in this project folder and run:

```powershell
.\scripts\start.ps1
```

If PowerShell blocks local scripts, use this one-process invocation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

The script creates `.venv`, installs dependencies, and serves the app at **http://127.0.0.1:8000**. The first demo launch builds its fixture database and may take longer. Keep the terminal open; use Ctrl+C to stop. Start on another port with `-Port 8001`. Once installed, `-NoInstall` skips package installation.

## Start on Linux or macOS

```sh
bash scripts/start.sh
```

Or use Docker:

```sh
docker compose up --build -d
```

Open **http://127.0.0.1:8000**. Docker keeps application data in the `scamserp-data` volume. `.env` is excluded from the image. [Deployment instructions](docs/DEPLOYMENT.md) cover live collection, the scheduler, TLS, backups and operational limits.

## Configure live mode

If `.env` already exists, edit it in place. Otherwise copy `.env.example` to `.env`. The application loads the project-root `.env`; environment variables supplied by the host take precedence. Never commit or distribute `.env`.

Set `SCAMSERP_MODE=live` and your `SERPAPI_API_KEY`. Set a long, random `SCAMSERP_ADMIN_TOKEN` to enable protected operations. Keep `SCAMSERP_PUBLIC_LIVE=false` until you intentionally want visitors to spend collection credits. Restart the server after configuration changes. Set SCAMSERP_SCHEDULER=true to start a single budgeted scheduler alongside the web app, or run a dedicated scheduler. The lock prevents duplicate scheduler owners. Check /api/coverage for heartbeat and coverage gaps.

Use the **Review workspace** at `http://127.0.0.1:8000/#admin` to collect a known query, or run:

```powershell
.\.venv\Scripts\python.exe -m scamserp.cli collect --query sbi-en-1 --state Delhi
```

On Linux, use `.venv/bin/python` in place of the Windows Python path. `demo.sqlite3` and `live.sqlite3` are separate; switching modes never relabels synthetic data as live evidence. The default limits reserve at most 20 provider attempts per UTC day and 200 per UTC month, including retries and advertiser enrichment.

## What is included

- Phone, domain and message lookup with evidence, official alternatives and English/Hindi verdict explanations.
- 1,393 seeded query variants, including refund, courier-tracking and passport-appointment intents, across 40 entities, six Indian languages and Hinglish; native-speaker validation remains required.
- Search, Autocomplete and Local collection, plus budgeted Ads Transparency advertiser/domain discovery and evidence-backed attribution review. Domain matches remain candidates; missing account-age and verification fields remain unknown.
- Compressed, credential-redacted provider archives, search IDs, conservative versioned rules, campaign graphs and historical rescoring.
- A geographic map, trends, matched language comparisons, query and entity reports, autocomplete watchlist, CSV/JSON exports and weekly digests.
- Protected registry editing, campaign approval, disputes, suggestion review, collection budgets and evaluation-label APIs.
- Tests, CI, Windows/Linux launch scripts and a non-root Docker image.

There is no automatic RDAP collector, no independent 300-observation evaluation and no claim that observed search exposure represents all residents of a state. The six sampled locations are city proxies. Missing evidence returns **No data** or **Unverified**, never a safety guarantee.

## Explore the demo

1. Try `1800 1234` or `sbi.bank.in` in lookup; inspect the registry source and expiry date.
2. Use the fictional demo message example to inspect rule explanations. Never call fixture numbers or submit synthetic reports.
3. Open the map, select a sampled state and inspect its annotated queries.
4. Open research, campaigns and evaluation; download the derived dataset.
5. Enter your admin token in the review workspace to inspect the review flow.

The demo's regional and language variation is generated for interface testing. It is not a research finding. Registry records expire; source checks must be renewed to remain current.

## Development and verification

```sh
python -m venv .venv
# Windows: .venv\Scripts\python.exe; Linux/macOS: .venv/bin/python
python -m pip install -e ".[test]"
python -m pytest
python -m pip check
```

Run these commands with the virtual environment activated or replace `python` with its full virtual-environment path. If `requirements.lock` is included, install it first with `python -m pip install -r requirements.lock`. The launch scripts and Docker build automatically prefer that lockfile. See [verification notes](docs/VERIFICATION.md) for the scope of evidence and outstanding checks.

Interactive API schema: `/docs`; JSON schema: `/openapi.json`; health probe: `/healthz`. No Node build is required. The current risk-map view uses the Google Maps JavaScript API and requires a Google Maps key, API enablement and appropriate browser-key restrictions.

## Interactive risk-map search and live location

The risk map has a full-width map with a floating search panel, category shortcuts, result filters and local evidence panels. An explicit search calls SerpApi's `google` and `google_maps` engines, retaining compressed source evidence and using the existing credit caps and cache. Results with high-confidence fraud indicators remain hidden until campaign review. Set `SCAMSERP_MAP_SEARCH=true` to enable this feature in live mode; the separate `SCAMSERP_PUBLIC_LIVE` setting still controls targeted citizen lookups.

Set `SERPAPI_API_KEY` (or `SERP_API_KEY`) and `GOOGLE_MAPS_API_KEY` (or `Google_Maps_Api_Key`) in `.env`, then restart the server. Map searches are archived as audit queries. Device location updates are processed in the browser only. Submitting a search in the visible area sends coordinates rounded to two decimal places; it does not send the continuous location stream.

The map requests location permission automatically and uses `navigator.geolocation.watchPosition` to update a blue location dot and accuracy circle while the app remains open. Permission denial, unavailable positioning and timeouts are shown honestly. The watcher is released when the page closes. Production geolocation requires HTTPS; localhost is suitable for development. A browser or device that does not supply a location fix cannot be made to display a real position by the app.

## Project guide

| File or directory | Purpose |
| --- | --- |
| `scamserp/app.py` | API, input validation, public publication gates, protected operations |
| `scamserp/collector.py` | Budgeted provider calls, caching, retries and scheduling |
| `scamserp/extract.py`, `trust.py`, `pipeline.py` | Extraction, transparent scoring and campaign graph |
| `scamserp/service.py`, `reports.py` | Lookup, aggregates, exports and digest |
| `scamserp/seed.py` | Candidate registry, query templates and synthetic fixture generator |
| `scamserp/static/` | Browser UI and locally served boundary data |
| `var/` | Local runtime databases, raw archives and generated digests; private, excluded from release |
| `docs/` | Architecture, operations, provenance and PRD traceability |

Read [PRD traceability](docs/PRD_TRACEABILITY.md), [methodology](docs/METHODOLOGY.md), [privacy and operations](docs/SECURITY_PRIVACY.md), [source checks](docs/SOURCES.md) and [third-party notices](THIRD_PARTY_NOTICES.md) before publishing findings. Original software is MIT licensed. Original derived findings use CC BY 4.0; third-party source content and geographic data retain their own rights.

## Version 1.1 audit improvements

The separate Audit dashboard (#audits) restores the state choropleth and combines query, state, language, category and time filtering with trends, matched-intent language comparisons, and explicit collection gaps. Stored views refresh every minute without spending collection credits. Campaign approvals bind to evidence fingerprints; changed evidence and stale review submissions require a new review. Registry and advertiser-review expiry trigger rescoring.

The local .env now enables the web scheduler and explicit targeted lookups under the existing 20/day and 200/month caps. Scheduled work runs while the server and computer remain active. Full configured coverage requires substantially more credits and scheduler throughput; independent registry, translation and evaluation work remains open. See [implementation update](IMPLEMENTATION_UPDATE.md) for tested behavior and [launch gates](docs/LAUNCH_GATES.md) for the remaining external requirements.
