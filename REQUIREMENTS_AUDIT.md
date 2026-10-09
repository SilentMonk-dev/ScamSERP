> Historical snapshot. Subsequent fixes and live verification are recorded in [IMPLEMENTATION_UPDATE.md](IMPLEMENTATION_UPDATE.md).

# Audit against the ScamSERP product description

Checked 9 October 2026 against the current source, configured live database, previous successful provider verification, and fresh isolated regression probes. Application code and live evidence were not changed by this audit. No extra provider searches were made.

**Verdict: partially fulfilled. This is a working supervised prototype, not yet a complete continuously operating public-interest audit.** A valid SerpApi key establishes connectivity; it does not complete collection coverage, verification, or detection quality.

## Requirement-by-requirement findings

| Product claim | Status | Evidence and remaining work |
| --- | --- | --- |
| Maintains high-risk Indian queries in English, Hindi and other languages | Partial | There are 1,120 active seeds: 160 each in English, Hindi, Tamil, Telugu, Bengali, Marathi and Hinglish, across 40 entities. The seeds use four generic intents: customer care, helpline, complaint support and nearby office. Banking, government, utilities, logistics, payments, telecom and ecommerce are represented. Dedicated refund, courier-tracking and passport-appointment intents are absent from the current seeds. Translations need native-speaker validation. See `scamserp/seed.py:55`. |
| Runs queries continuously | Partial implementation; operation unproven | A separate CLI scheduler checks every six hours, with 7/14/30-day query tiers. Starting the web app does not start it. The default cap is 20 provider attempts/day and 200/month, including retries and enrichment: insufficient for comprehensive recurring coverage of 1,120 queries across six locations. No scheduler lock exists in the configured data directory. Process inspection was unavailable, so an active process cannot be ruled out conclusively. The live database has no recurring collection history. See `scamserp/cli.py:49` and `collector.py:122`. |
| Google Search | Live verified | The latest test returned HTTP 200 and a successful `google` collection with 21 normalized observations. |
| Google Local | Implemented; separate live engine unverified | The collector supports `google_local`, scheduled for local-intent queries. The live database has no run from that engine. The map's separate `google_maps` integration did pass a live test with 20 observations; that does not verify the `google_local` engine. |
| Google Ads Transparency | Incomplete | Enrichment only runs when the original Search ad supplies an advertiser ID. No reliable advertiser-discovery flow is implemented. Returned evidence is stored in the advertiser table but not joined into scoring. The map Search path does not call `enrich_ads`. The live database contains no Ads Transparency runs or advertiser records. See `collector.py:94` and `map_search.py:49`. |
| Autocomplete discovers scam-prone queries | Partial | Collection and parsing exist; suggestions become inactive candidates requiring review. There are no live Autocomplete runs or generated candidates in the configured database. Autocomplete requests omit the state location, so they do not establish state-specific suggestions. A suggestion is a discovery signal; this implementation supplies no actual query counts, search volume, or proof of what people typed. See `pipeline.py:55`. |
| Checks every result against a verified domain/phone registry | Partial | Results are extracted and scored; unknown entities remain Unverified. Only SBI, UIDAI, Passport Seva and PM Kisan have current assistant source checks. The other 36 entity candidates are pending. Only SBI, UIDAI and Passport have seeded phone records; PM Kisan has a checked domain but no seeded verified phone. Independent human verification of the complete registry remains open. |
| Flags unofficial/lookalike domains and mismatched snippet numbers | Implemented with coverage limits | Rules extract Indian numbers, compare current contacts, and identify brand/lookalike domains. Missing registry data is treated conservatively rather than as proof of fraud. Detection is therefore limited by the incomplete registry. There are no real evaluation labels, so accuracy, precision and recall have not been established. See `trust.py:31` and `service.py:153`. |
| Flags unverified or newly created advertisers via Ads Transparency | Not fulfilled end to end | Rules recognize explicit `advertiser_verified`, `advertiser_linked` and `advertiser_new` facts in original results. The enrichment path does not populate these facts from its stored advertiser evidence. No implemented age calculation establishes newly created advertiser accounts. A first observed creative date alone would not establish account creation. See `extract.py:105`, `trust.py:79`, and `collector.py:110`. |
| Produces a live risk map by query, state and language | Partial | Explicit map searches work through Search and Maps, with query, language and location selectors, evidence panels and real provider coordinates. Aggregation APIs support category/language filtering; query detail supports state. The initial map only shows six city proxies, not measurements throughout India, and the redesigned UI does not provide a complete combined query/state/language historical risk matrix. The live database has only two successful runs; the default five-run threshold prevents meaningful aggregate exposure. Searches happen on explicit actions rather than continuously refreshing audit coverage. |
| A user pastes a number/link and gets a verdict with evidence | Implemented with reliability gaps | Phone/domain/text lookup, evidence dates, source references, signals and official alternatives exist. Unknown items can return No data or Unverified. Public targeted live lookup is currently disabled by `SCAMSERP_PUBLIC_LIVE=false`; map search is enabled separately. Two confirmed bugs below prevent treating current verdicts as production-ready. |

## Confirmed reliability issues

1. **Expired verification can remain public.** In a fresh isolated fixture, expiring all matching registry records still left lookup returning Verified Official from historical scored observations. `scamserp/service.py:57` allows this fallback. Current registry validity must govern current verification.
2. **Changed evidence can retain approval.** In another isolated fixture, adding a recent-registration fact changed Suspicious to Likely Fraud. The campaign stayed approved, and lookup published the changed verdict. `scamserp/pipeline.py:94` retains approval based only on campaign ID and size. Review must bind to the actual evidence, verdict and rule version.
3. **Filtered map metadata is inconsistent.** A logistics map with zero runs reported one withheld banking run. The withheld count ignores map filters in `scamserp/service.py:87`.
4. **Language comparisons mix intents.** `scamserp/service.py:130` matches entity, city and day, dropping query intent. Comparable translated queries must share an intent identifier before language comparisons are presented as findings.

## Current live evidence

`SERPAPI_VERIFICATION.json` records successful Search and Maps tests: 28 published results, 19 mapped places, one finding withheld for review, and no provider gaps. `REQUIREMENTS_AUDIT_DATA.json` records the subsequent read-only database inventory: one successful run per engine, no successful Local/Autocomplete/Ads Transparency runs, four current registry entities, and no evaluation labels. Historical failed key checks are retained as gaps.

The earlier test suite used synthetic/mocked responses. Passing those checks does not establish real-world fraud-detection accuracy or validate untested live provider engines.

## What must happen before the description is fully accurate

1. Fix expired-verification fallback and approval retention; correct filtered metadata and intent matching.
2. Human-check and maintain official domains and numbers for all supported entities, including regional contact variations.
3. Add validated refund, tracking and appointment queries and translations.
4. Connect documented Ads Transparency fields to observation scoring with field provenance and unknown states; verify advertiser resolution and account-age feasibility against actual provider responses.
5. Verify Local, Autocomplete and Ads Transparency live responses within an agreed credit budget.
6. Operate one persistent scheduler with monitoring, a fair coverage plan, sufficient credits and explicit sampling/freshness targets.
7. Populate and review enough real query/location/language samples, complete the combined risk views, and evaluate detection on independently labelled real observations.

The opening statements about national losses and nobody systematically auditing this space are research/novelty claims. This code audit does not establish them. They need external sources and a review of existing work before use in a public pitch.

An accurate current description is: **ScamSERP is a prototype for auditing Indian support-related search results, with multilingual query seeds, conservative registry checks, live Search/Maps checks, and evidence-based contact lookup. Broader collection, registry verification, advertiser analysis and real-world evaluation remain incomplete.**
