> Historical snapshot. Subsequent fixes and live verification are recorded in [IMPLEMENTATION_UPDATE.md](IMPLEMENTATION_UPDATE.md).

# Risk-map update — 9 October 2026

- Removed the live-collection headline from the page shell.
- Reworked the map into a full-width explorer inspired by the supplied Google Maps reference: floating search and location cards, category shortcuts, zoom controls, map/satellite layers, a legend, and a scrollable evidence panel.
- Added `POST /api/map/search` using SerpApi Search plus Maps. Queries are resolved to registry entities where possible; result coordinates come from public listing data. Only actual provider coordinates are pinned. Organic results remain inspectable web evidence rather than being assigned invented locations.
- Connected searches to existing credit reservations, retries, raw archives, cache, trust scores and campaign publication gates. Partial collection and withheld findings do not produce an apparently clean exposure result.
- Added persistent `watchPosition` tracking, a live blue dot and accuracy circle. Location updates stay in tab memory. Explicit map search rounds its search-area coordinates to two decimal places before sending them to the server/provider.
- Added a dedicated `SCAMSERP_MAP_SEARCH` switch and enabled it in the local `.env`. Existing API keys and the public citizen-lookup setting were preserved. Compose now forwards supported key aliases and Maps configuration.

## Verification

The backend suite passes 52 tests. Three separate JavaScript tests cover continuous updates, permission denial/retry and watcher cleanup. Browser checks confirmed map tiles and the new interface render. The device did not return a location fix in the test browser; the map shows a truthful waiting state.

A real SerpApi connection attempt was made. SerpApi's Account API returned HTTP 401 with “Invalid API key” for the current `.env` value. No key value was printed. Real Search/Maps result collection remains blocked until that local value is replaced with a valid SerpApi key and the server is restarted. The interface and API handle the error without inventing findings.

Reference implementations: [SerpApi Maps documentation](https://serpapi.com/google-maps-api), [Google Maps geolocation](https://developers.google.com/maps/documentation/javascript/geolocation), [browser watchPosition documentation](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation/watchPosition).
