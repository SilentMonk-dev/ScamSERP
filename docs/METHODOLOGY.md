# Methodology

The rule engine checks claimed entities against current official-contact records. It extracts Indian phone formats and normalized domains, records source snippets, and scores explainable identity, contact, infrastructure, ad and local signals. A score of at least 75 needs two independent positive signal families for Likely Fraud. Official domain and displayed phones must match current records for the observation override.

Pending/expired records are not verified. Public reads refresh scoring after registry/advertiser-review expiry. An additional current-registry check prevents stale official observation labels being reused as current verification. Phone-only lookup verifies a contact record, not an incoming caller.

Each campaign approval binds to a fingerprint of its actual members, content, scoring evidence, verdicts and rule version. Changed evidence resets review to pending. Review submissions carry the fingerprint; stale submissions are rejected. Disputes hide affected findings. Any hidden or unreviewed Likely Fraud result withholds its complete ranked run from exposure calculations.

Ads have weight 1.5; ranked organic/local results have weight 1/rank. Weighted flagged shares are averaged across eligible runs. Fewer than the configured minimum runs produces no exposure estimate. Intervals are exploratory query-cluster bootstrap intervals, not estimates of population fraud incidence.

Language comparisons match entity, translated intent, city, collection date and engine. Unmapped suggestions/free-text queries are excluded. Search and Local query/state/language matrix cells remain separated by engine. Autocomplete is a national suggestion-discovery surface, excluded from ranked exposure and not a search-volume metric.

Ads Transparency domain matches remain advertiser candidates. Direct Search advertiser IDs or evidence-backed human attribution permit joining stored advertiser evidence. Names, countries and sampled creative dates alone do not establish verification, account creation or an official entity relationship. Unknown fields never add risk. Human relationship checks require sources and expire. Missing automatic RDAP evidence likewise never contributes a domain-age signal.

Coverage is six city proxies plus explicit visible-area Maps searches. It does not represent every resident or every personalized search. Synthetic fixtures are isolated from live evidence. Independent labels and native-speaker review remain necessary before presenting comparative research findings.
