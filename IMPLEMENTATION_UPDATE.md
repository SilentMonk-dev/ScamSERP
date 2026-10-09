# ScamSERP 1.1 — implementation and verification

Completed 9 October 2026 following the requirements audit. Current preview: **http://127.0.0.1:8006/#audits**. Use this version rather than earlier preview ports. The project remains at `C:/Users/baisp/Documents/Codex/2026-10-09/bu/outputs/ScamSERP`.

## Changes

- Current registry expiry automatically refreshes scoring. Public evidence also checks current official contacts before displaying Verified Official. Historical verification no longer substitutes for current verification.
- Campaign approvals bind to fingerprints of members, content, scores, signal evidence and rule version. Changed evidence resets approval; stale review submissions return HTTP 409. The review interface loads the campaign's full evidence before recording the decision.
- Map withheld counts follow the selected filters. Language comparisons match entity, translated intent, city, day and engine rather than mixing customer-care and office queries.
- Added translated refund, courier-tracking and passport-appointment intents. The versioned migration preserves existing queries and registry edits. There are now **1,393 active seeds**, across 40 entities and seven language forms.
- Collection tasks are independent for Search, Local and national Autocomplete. Persistent task attempts, cooldowns, heartbeat/status and request caps prevent missing engines being suppressed by a fresh Search run. A data-directory lock permits one scheduler owner across web/dedicated processes. The local `.env` enables scheduling and explicitly requested targeted lookups; the caps remain 20/day and 200/month.
- Ads Transparency supports domain discovery when Search lacks advertiser IDs. Domain matches remain candidates. Attributed advertiser evidence is joined into scoring and evidence views, with protected source-backed relationship review and expiry. Missing verification/account-age fields remain unknown. The map's Search path now runs the same bounded enrichment.
- The requested Google-style map remains available. A separate Audit dashboard restores the lazy-loaded state choropleth and combines query, state, category, language and time filtering with trends, matched language comparisons and a paginated query/state/language/engine table. Uncollected, empty, failed and withheld data are visible. Stored views refresh every minute without extra provider searches.
- Added source-check and advertiser-review controls, completed the missing deployment/methodology/provenance/launch documentation, declared dotenv/file-lock runtime dependencies, updated CI script checks and built a distributable wheel.

Schema changes are additive. Existing compressed archives and source histories are retained. Rule version is `rules-1.1.0`. Back up before upgrades and stop older application versions before a production restart; do not mix old writers with an upgraded database. The earlier local preview processes were retained because stopping them was previously blocked by automatic approval review. The active scheduler lock prevents duplicate owners; restart from the updated project for sustained use of all latest code.

## Verified

| Check | Result |
| --- | --- |
| Backend suite | **65 passed**, one dependency deprecation warning |
| Geolocation watcher suite | **3 passed** |
| Every browser script | JavaScript syntax passed |
| Installed dependency consistency | No broken requirements |
| Distribution | `scamserp-1.1.0-py3-none-any.whl` built successfully |
| Live Search and Maps | Both succeeded; earlier combined check published 28 results with 19 mapped places |
| Live Google Local | Succeeded; 20 listing observations |
| Live Autocomplete | Succeeded; 15 suggestion observations |
| Live Ads Transparency | Succeeded; 40 creatives returned and archived |
| Scheduler | One owner active, recent heartbeat, first six tasks completed, no recorded tick error |
| Final app | Version 1.1.0 health/database check passed; map and targeted lookup enabled |
| Final filters | Aadhaar/Delhi/English returned two eligible runs and six matrix cells, consistently across map/table |
| Browser | Dashboard and map loaded without console errors; query/state/language filters worked; small-viewport document width did not overflow; temporary viewport reset |
| Live location | Watcher remains implemented and tested; actual browser/device supplied no fix and displays Waiting for location |

Safe connection/inventory results are retained in `SERPAPI_VERIFICATION.json`, `PROVIDER_ENGINE_VERIFICATION.json` and `FINAL_VERIFICATION.json`. No credentials are included in these reports. The final verification counted 16 reserved attempts that day, including previous failures, inside the existing daily cap.

## Remaining launch gates

This update completes the identified implementation fixes, but does not certify a public fraud-detection service. Only four entities have current assistant source checks; independent human contact verification for the full registry, native-speaker query review and independently labelled real evaluation remain open. Accuracy targets have not been measured.

At current query/location/tier settings, full cadence requires approximately **24,535 requests/month**, excluding retries, advertiser enrichment and citizen searches, versus the configured cap of **200**. Scheduler throughput must also match an approved collection plan. The app rotates within the current caps and exposes its gaps; it does not claim comprehensive continuous coverage.

The documented Ads Transparency schema supplies advertiser details and creative dates, not proof of account creation. Do not describe recent sampled creatives as newly created accounts. Provider-side verification and official relationships remain unknown unless supported by explicit evidence or a reviewed source. See [provider documentation](https://serpapi.com/google-ads-transparency-center-api).

See [launch gates](docs/LAUNCH_GATES.md) and [deployment instructions](docs/DEPLOYMENT.md). Full national coverage, production hosting/restore checks and independently supported novelty/loss claims still require external work.
