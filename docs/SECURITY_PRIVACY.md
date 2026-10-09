# Security and privacy

SerpApi credentials stay in server configuration. `.env`, local databases and raw archives are excluded from source/release images. Provider evidence is compressed and credential fields/URLs are redacted. Public exports replace contact identifiers with salted tokens and omit snippets; CSV formula-leading values are escaped.

Ordinary contact/message lookup is processed in memory. Explicit targeted lookup and map searches transmit the requested search terms to SerpApi and archive provider metadata. Their UI describes this before collection. Map searches send a rounded search area; continuous device positions are not sent to the backend or saved in local storage.

Admin authorization uses a bearer token and constant-time comparison. The browser stores the token only in tab memory. Request size and per-process rate limits apply; provider budgets use SQLite transactions across concurrent requests. Use TLS and an operator-controlled reverse proxy for public deployment, with appropriate global rate limiting and protected private data directories.

Disputes, source suggestions, reviews and raw search records are retained operational records. Operators must set retention and access policies before public use. No automatic messages, reports to authorities, or external publishing occur. Users inspect and submit report summaries themselves.

Do not use the bundled demo contacts as real contacts or report synthetic findings. A published risk indicator is evidence to inspect, not a legal determination.
