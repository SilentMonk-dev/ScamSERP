# Source provenance

The seed registry in `scamserp/seed.py` is the source of candidate entities and verification dates. Four entities have assistant primary-source checks dated 9 October 2026, expiring 8 November 2026: SBI, UIDAI, Passport Seva and PM Kisan. Other candidates remain pending. This document does not claim independent human verification.

Primary source URLs are retained per record and shown in the registry/review UI. SBI, UIDAI and Passport have seeded phone records; PM Kisan's checked record is a domain. Operators must verify additional contacts and regional variations rather than infer them from Search results.

The query library has 1,393 active templates in seven language forms after migration, including refund, courier-tracking and passport-appointment intents. Templates require native-speaker review. Real Autocomplete suggestions create inactive review candidates and are never relabelled as manually validated queries.

Provider schemas checked during implementation:

- [SerpApi Ads Transparency documentation](https://serpapi.com/google-ads-transparency-center-api): text discovery, advertiser details, target domains and creative dates; no account-age inference.
- [SerpApi Autocomplete documentation](https://serpapi.com/google-autocomplete-api): country/language suggestions; national sampling is labelled accordingly.
- [SerpApi Google Local documentation](https://serpapi.com/google-local-api): localized listing collection.

`SERPAPI_VERIFICATION.json` records the successful Search/Maps connection. `PROVIDER_ENGINE_VERIFICATION.json` records successful Local, Autocomplete and Transparency tests. Archived source payloads include provider search IDs. The successful responses establish integration, not fraud-detection accuracy.

Boundary provenance and licensing are retained in `scamserp/data/geo-source.json`. Third-party source material retains its rights.
