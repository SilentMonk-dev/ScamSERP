"""Budgeted SerpApi collection. Retry attempts are reserved before network I/O."""
import hashlib
import json
import random
import time
from datetime import datetime, timedelta, timezone

import httpx

from .db import now
from .pipeline import redact
from .seed import STATES
from .extract import domain


class BudgetExceeded(Exception):
    pass


class Collector:
    def __init__(self, db, pipeline, transport=None, sleep=time.sleep):
        self.db, self.pipeline, self.transport, self.sleep = db, pipeline, transport, sleep

    def reserve(self, engine):
        today = datetime.now(timezone.utc).date().isoformat()
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            daily = c.execute("SELECT COUNT(*) FROM budget WHERE spent_at>=?", (today,)).fetchone()[0]
            monthly = c.execute("SELECT COUNT(*) FROM budget WHERE spent_at>=?", (today[:7] + "-01",)).fetchone()[0]
            if daily >= self.db.settings.daily_cap or monthly >= self.db.settings.monthly_cap:
                raise BudgetExceeded("Configured collection budget reached")
            c.execute("INSERT INTO budget(spent_at,engine) VALUES (?,?)", (now(), engine))

    def request(self, params):
        if not self.db.settings.api_key:
            raise ValueError("SERPAPI_API_KEY is not configured")
        if self.db.settings.mode != "live":
            raise ValueError("Live collection requires SCAMSERP_MODE=live; demo data is isolated")
        key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        cached = self.db.one("SELECT * FROM run WHERE cache_key=? AND status='success' AND fetched_at>? ORDER BY fetched_at DESC LIMIT 1", (key, cutoff))
        if cached:
            import gzip
            with gzip.open(self.db.settings.data_dir / cached["raw_ref"], "rt", encoding="utf-8") as f:
                return json.load(f), key, cached["id"]
        for attempt in range(3):
            self.reserve(params["engine"])
            try:
                with httpx.Client(timeout=30, transport=self.transport, follow_redirects=False) as client:
                    response = client.get("https://serpapi.com/search.json", params={**params, "api_key": self.db.settings.api_key})
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        self.sleep(min(8, 2 ** attempt + random.random()))
                        continue
                    raise RuntimeError("Provider rate limit or temporary failure")
                if response.status_code == 401:
                    raise RuntimeError("SerpApi rejected the configured API key. Update SERP_API_KEY in .env and restart the app.")
                if response.status_code >= 400:
                    raise RuntimeError("Provider rejected the request; check account configuration")
                data = response.json()
                if not isinstance(data, dict):
                    raise RuntimeError("Unexpected provider response")
                return redact(data), key, None
            except (httpx.HTTPError, ValueError):
                if attempt == 2:
                    raise RuntimeError("Provider request failed") from None
                self.sleep(min(8, 2 ** attempt + random.random()))
        raise RuntimeError("Provider request failed")

    def collect(self, query_id, state, engine="google"):
        if engine not in {"google", "google_autocomplete", "google_local"}:
            raise ValueError("Unsupported engine")
        q = self.db.one("SELECT * FROM query WHERE id=?", (query_id,))
        if not q or (state not in STATES and not (engine == "google_autocomplete" and state == "India")):
            raise ValueError("Unknown query or state")
        if engine == "google_autocomplete":
            state = "India"
        location = STATES.get(state, "India")
        hl = "hi" if q["language"] == "hinglish" else q["language"]
        params = {"engine": engine, "q": q["text"], "gl": "in", "hl": hl}
        if engine != "google_autocomplete":
            params["location"] = location
        try:
            payload, key, cached = self.request(params)
            if cached:
                return {"run_id": cached, "cached": True}
            result = self.pipeline.ingest(payload, query_id, engine, state, location, hl, cache_key=key)
            if engine == "google" and result["status"] == "success":
                self.enrich_ads(result["run_id"])
            return result
        except BudgetExceeded:
            raise
        except Exception as exc:
            self.pipeline.ingest({"error": "Collection unavailable", "search_metadata": {"status": "Error"}}, query_id, engine, state, location, hl)
            raise RuntimeError("Collection failed; recorded as a data gap") from None

    def enrich_ads(self, run_id):
        ads = self.db.rows("SELECT * FROM observation WHERE run_id=? AND kind='ad'", (run_id,))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        remaining = self.db.settings.ads_requests_per_run
        enriched = False
        def fetch(params):
            nonlocal remaining
            if remaining <= 0:
                raise BudgetExceeded("Per-run advertiser enrichment limit reached")
            remaining -= 1
            data, key, cached = self.request(params)
            result = {"run_id": cached} if cached else self.pipeline.ingest(data, None, "google_ads_transparency_center", "India", "India", "en", cache_key=key, rebuild=False)
            return data, result["run_id"]
        for ad in ads:
            aid = ad["advertiser_id"]
            try:
                candidates = []
                if not aid and ad["domain"]:
                    data, archive = fetch({"engine": "google_ads_transparency_center", "text": ad["domain"], "region": "2356"})
                    for creative in data.get("ad_creatives", []):
                        candidate = creative.get("advertiser_id")
                        if isinstance(candidate, str) and domain(creative.get("target_domain") or "") == ad["domain"] and candidate not in {c["id"] for c in candidates}:
                            candidates.append({"id": candidate, "name": creative.get("advertiser"), "target_domain": ad["domain"], "source_run_id": archive})
                    facts = json.loads(ad["facts_json"])
                    facts["advertiser_candidates"] = candidates[:10]
                    facts["advertiser_discovery"] = {"source_run_id": archive, "status": "candidate matches" if candidates else "no matching creatives", "note": "Domain matches are candidates, not attribution or verification of this observed ad."}
                    self.db.execute("UPDATE observation SET facts_json=? WHERE id=?", (json.dumps(facts), ad["id"]))
                    enriched = True
                ids = [aid] if aid else [c["id"] for c in candidates]
                for advertiser_id in ids:
                    if self.db.one("SELECT id FROM advertiser WHERE id=? AND checked_at>?", (advertiser_id, cutoff)):
                        continue
                    data, archive = fetch({"engine": "google_ads_transparency_center", "advertiser_id": advertiser_id, "get_advertiser": "true", "region": "2356"})
                    if data.get("error"):
                        continue
                    advertiser = data.get("advertiser", {})
                    first_shown = [x.get("first_shown") for x in data.get("ad_creatives", []) if isinstance(x.get("first_shown"), (int, float))]
                    status = advertiser.get("verification_status", "unknown")
                    if status not in {"verified", "unverified"}:
                        status = "unknown"
                    normalized = {"name": advertiser.get("legal_name") or advertiser.get("name"), "region": advertiser.get("country_code"), "verification_status": status, "ad_count": data.get("search_information", {}).get("total_results"), "first_seen": min(first_shown, default=None), "account_created_at": None, "source_run_id": archive, "search_id": data.get("search_metadata", {}).get("id"), "source_url": "https://adstransparency.google.com/advertiser/" + advertiser_id, "note": "Earliest sampled creative is not account creation. Missing verification status remains unknown."}
                    self.db.execute("INSERT OR REPLACE INTO advertiser VALUES (?,?,?)", (advertiser_id, json.dumps(normalized), now()))
                    enriched = True
                if not ids:
                    self.db.log("advertiser_gap", {"run_id": run_id, "observation_id": ad["id"], "reason": "No advertiser attribution available"})
                if remaining <= 0:
                    continue
            except (RuntimeError, BudgetExceeded):
                self.db.log("advertiser_gap", {"run_id": run_id, "reason": "Unavailable or budget capped"})
        if enriched:
            self.pipeline.rebuild()

    def targeted(self, value):
        data, key, cached = self.request({"engine": "google", "q": f'"{value}"', "gl": "in", "hl": "en", "location": STATES["Delhi"]})
        if cached:
            return {"run_id": cached, "cached": True}
        return self.pipeline.ingest(data, None, "google", "Delhi", STATES["Delhi"], "en", cache_key=key)

    def schedule_plan(self):
        clock = datetime.now(timezone.utc)
        successes = {(r["query_id"], r["state"], r["engine"]): r["latest"] for r in self.db.rows("SELECT query_id,state,engine,MAX(fetched_at) latest FROM run WHERE status='success' GROUP BY query_id,state,engine")}
        attempts = {(r["query_id"], r["state"], r["engine"]): r for r in self.db.rows("SELECT * FROM audit_task")}
        tasks = []
        for q in self.db.rows("SELECT * FROM query WHERE active=1"):
            surfaces = [(s, "google") for s in STATES] + [("India", "google_autocomplete")]
            if q["local_intent"]:
                surfaces += [(s, "google_local") for s in STATES]
            for state, engine in surfaces:
                key = (q["id"], state, engine)
                previous = successes.get(key)
                days = {1: 7, 2: 14, 3: 30}[q["tier"]]
                due = not previous or datetime.fromisoformat(previous) <= clock - timedelta(days=days)
                attempted = attempts.get(key)
                cooling = bool(attempted and attempted["last_status"] != "success" and datetime.fromisoformat(attempted["last_attempt"]) > clock - timedelta(hours=self.db.settings.schedule_hours))
                # Deterministic spreading avoids exhausting credits on one entity/language/city.
                spread = hashlib.sha256(":".join(key).encode()).hexdigest()
                tasks.append({"query_id": q["id"], "state": state, "engine": engine, "tier": q["tier"], "days": days, "latest": previous, "last_attempt": attempted["last_attempt"] if attempted else None, "due": due, "cooling": cooling, "spread": spread})
        tasks.sort(key=lambda t: (t["last_attempt"] or "", t["tier"], t["spread"]))
        return tasks

    def scheduled(self, limit=6):
        results = []
        self.db.execute("INSERT OR REPLACE INTO meta VALUES ('scheduler_last_tick',?)", (now(),))
        for task in self.schedule_plan():
            if not task["due"] or task["cooling"]:
                continue
            if len(results) >= limit:
                break
            try:
                result = self.collect(task["query_id"], task["state"], task["engine"])
                status = "success" if result.get("cached") else result["status"]
            except BudgetExceeded:
                self.db.log("scheduler_budget_pause", {"completed_tasks": len(results)})
                break
            except RuntimeError:
                result, status = {"status": "failed"}, "failed"
            self.db.execute("INSERT OR REPLACE INTO audit_task VALUES (?,?,?,?,?)", (task["query_id"], task["state"], task["engine"], now(), status))
            results.append({**result, "query_id": task["query_id"], "state": task["state"], "engine": task["engine"]})
        self.db.execute("INSERT OR REPLACE INTO meta VALUES ('scheduler_last_result',?)", (json.dumps({"completed_tasks": len(results), "finished_at": now()}),))
        return results
