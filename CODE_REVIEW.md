> Historical snapshot. Subsequent fixes and live verification are recorded in [IMPLEMENTATION_UPDATE.md](IMPLEMENTATION_UPDATE.md).

# Current code inspection — 9 October 2026

Reviewed the current FastAPI/SQLite backend, collector, rule engine, frontend and deployment files in this directory. This review did not change application code, expose credentials, or spend SerpApi credits. Isolated reproduction databases and scripts are under the chat workspace's `work/qa` directory.

The implementation has a useful foundation, but the public launch requirements are not complete. Fix the publication and expiry issues before exposing real findings.

## Confirmed findings

### P1 — Changed evidence retains old campaign approval

`scamserp/pipeline.py:94` retains a campaign's review state when its identifier and member count are unchanged. It does not compare the reviewed scores, verdicts or signal evidence.

Reproduction: ingest a branded unofficial result without contact information; its verdict is Suspicious. Approve the campaign. Add independently supported recent domain-registration evidence and rebuild the scores. The verdict becomes Likely Fraud, the campaign remains approved, and public lookup publishes the new verdict without a fresh review.

Store an evidence/review fingerprint, and invalidate approval whenever membership, verdicts, relevant signals or rule version changes. Add a regression covering same-size evidence changes, not just cluster growth.

### P1 — Expired registry contacts remain Verified Official through cached observations

`scamserp/service.py:57–58` falls back to the latest stored observation verdict after the current registry match fails. `PUBLIC_SQL` in `scamserp/db.py` does not require that the stored verification is still current. There is no automatic expiry-triggered rescore.

Reproduction: collect an official SBI fixture, expire its registry entries, then look up `sbi.bank.in`. All corresponding records are inactive, but the answer remains Verified Official because the stored score is still verified.

Distinguish verification at collection time from current contact verification. Invalidate or rescore affected results when records expire, and prevent a historical Verified Official observation from overriding a current expired registry.

### P2 — Docker drops the configured key aliases

`scamserp/config.py:11–12` accepts both SerpApi key names and both Maps key names, but `compose.yaml:18` only passes `SERPAPI_API_KEY`; it passes neither Maps key. `.env` is correctly excluded from the Docker image, so the container cannot recover those omitted values from the file.

The current `.env` uses `SERP_API_KEY` and `Google_Maps_Api_Key`. Local CLI startup recognizes those aliases. Docker startup will receive an empty SerpApi key and no Maps key with that configuration.

Use canonical names consistently, or make Compose forward supported aliases. Add a configuration check that reports only whether required values are present.

### P2 — Advertiser enrichment is not connected to scoring

`scamserp/collector.py:108–110` stores normalized advertiser evidence in the `advertiser` table. The pipeline reads only `observation.facts_json`; no code joins the stored advertiser record into those facts or rescoring. Ad signals therefore depend on flags supplied in the original search result; synthetic fixtures provide these flags explicitly.

Map only explicitly supported provider fields into observation evidence, keep unknown verification unknown, retain field provenance, and rescore affected observations after enrichment. Do not infer advertiser verification from the presence of an account or from sample creative counts.

### P2 — Language comparisons collapse distinct query intents

`scamserp/service.py:130` matches only the entity prefix, location and date. It drops the query variant. A customer-care query in one language and an office-location query in another can be treated as the same matched sample.

Add a stable intent/variant identifier shared across translations, and match comparable intent and result surfaces before producing language comparisons. Autocomplete queries need explicit intent mapping rather than matching their `auto` identifier prefix.

### P2 — Filtered map reports unrelated withheld runs

`scamserp/service.py:87` counts withheld runs across the entire database, ignoring the selected category, language, window and entity.

Reproduction: one withheld banking run causes a logistics map with zero runs to report one withheld run. Apply the selected filters to the withheld count, or explicitly return a separate global count and a filtered count.

### P2 — Map implementation and release documentation disagree

`scamserp/static/app.js:125–126` renders Google Maps markers; the geographic `indiaSvg()` choropleth is no longer called. This does not fulfill the PRD's state choropleth requirement. Bootstrap still downloads the approximately 4.5 MB boundary file before rendering the first page, although the current marker map does not use it.

Restore the state choropleth, preferably with a local fallback, and load geographic data only when opening the map. If Google Maps is retained as an optional additional view, document its JavaScript API/billing configuration and browser-key restrictions. The README currently claims no map tile service is required.

The README also links to a `docs/` tree and `THIRD_PARTY_NOTICES.md` that are absent in the inspected checkout. Finish the referenced release files or remove inaccurate links before distributing it.

## Configuration status

- A project-root `.env` exists and contains a SerpApi key, Maps key, live-mode setting, public-live setting and admin token. Values were not printed.
- The local CLI calls `load_dotenv()` before creating settings, and the current settings class accepts the names used in that file.
- Direct `uvicorn scamserp.app:app` startup does not load `.env` by itself; use the supplied CLI/start script, pass `--env-file`, or export environment variables.
- Recognition of a key is not a successful provider connection. No real SerpApi request was made during this inspection.

## Verification

- JavaScript syntax check: passed (`node --check scamserp/static/app.js`).
- Extraction/trust tests: **26 passed**, with one dependency deprecation warning.
- Three isolated probes reproduced stale verification, approval retention after evidence change, and the unrelated withheld-run count.
- The complete suite collects 46 tests. API tests were blocked before application execution while Windows attempted to create the asyncio socket pair inside the sandbox. A timeout stack trace located the block in `socket.accept` during event-loop setup. The complete suite has not been reported as passing.
- Browser interaction, Google Maps configuration, Docker execution and live provider response shapes were not verified in this inspection.

## Remaining launch requirements

The registry contains 40 candidates but only four entities have assistant source checks; independent human verification remains required. The real-world labelled evaluation is absent, translations need native-speaker review, and automatic RDAP collection is absent. These are PRD gaps, not measured successes.

For a local supervised run, use Python 3.11+, install project dependencies, launch through the CLI/start script so `.env` is read, and keep a writable data directory. For real collection, use sufficient SerpApi credits and configured caps. The current Maps view additionally requires an enabled Maps JavaScript API and appropriate browser-key restrictions. A public deployment also needs TLS, durable storage/backups, a single scheduler, and completed review/evaluation requirements.
