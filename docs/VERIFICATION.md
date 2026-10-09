# Verification scope

Backend regressions exercise expiry, evidence-bound campaign approval, stale review submissions, filtered exposure, translated-intent matching, budget concurrency, provider caching, advertiser discovery/attribution, publication/disputes and single scheduler ownership. JavaScript syntax checks and geolocation watcher tests cover browser scripts and cleanup.

Live tests on 9 October 2026 succeeded for Search and Maps, then Local (20 listings), Autocomplete (15 suggestions) and Ads Transparency (40 creatives). Those counts describe individual integration tests, not national coverage or confirmed scams. The first scheduler tick collected six tasks under existing caps.

The browser dashboard loaded without console errors. Its query/state/language table showed the selected Aadhaar/Delhi/English evidence with explicit uncollected and withheld cells. Desktop/mobile checks and final test totals are recorded in `IMPLEMENTATION_UPDATE.md` after verification finishes.

Run `python -m pytest`, `node --check` for each static JavaScript file, `node --test tests/location-tracker.test.cjs`, and `python -m pip check`. Build a wheel with `python -m pip wheel --no-deps . --wheel-dir dist`. CI defines Python 3.11/3.12 checks on Windows/Linux and a container build; the existence of CI configuration does not mean those hosted jobs ran here.

Independent real labels, native-speaker validation, complete human registry verification, container execution and production restore/load tests remain separate launch gates.
