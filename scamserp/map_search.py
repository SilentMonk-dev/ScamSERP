"""Explicit, budgeted map searches. Continuous device location is never ingested."""
import hashlib
import json
import re
import threading

from .collector import BudgetExceeded
from .seed import STATES
from .service import public_observation

CENTERS = {"Maharashtra": (19.076, 72.8777), "Uttar Pradesh": (26.8467, 80.9462), "Tamil Nadu": (13.0827, 80.2707), "Telangana": (17.385, 78.4867), "West Bengal": (22.5726, 88.3639), "Delhi": (28.6139, 77.209), "India": (21.5, 79.0)}


class MapSearch:
    def __init__(self, db, pipeline, service, collector):
        self.db, self.pipeline, self.service, self.collector = db, pipeline, service, collector
        self.lock = threading.Lock()

    def search(self, query, language="en", state="India", latitude=None, longitude=None, entity_id=None):
        query = " ".join(query.split()).strip()
        if not query:
            raise ValueError("Enter a support query to search")
        if state not in CENTERS:
            raise ValueError("Choose a supported location or the current map area")
        if entity_id and not self.db.one("SELECT id FROM entity WHERE id=?", (entity_id,)):
            raise ValueError("Unknown entity")
        if not entity_id:
            matches = []
            for entity in self.db.rows("SELECT * FROM entity"):
                aliases = [entity["id"], *json.loads(entity["aliases"])]
                if any(len(alias) >= 3 and re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", query, re.I) for alias in aliases):
                    matches.append(entity["id"])
            entity_id = matches[0] if len(set(matches)) == 1 else None
        # Queries are retained only after an explicit Search action, as audit evidence.
        existing = self.db.one("SELECT id FROM query WHERE entity_id IS ? AND text=? AND language=?", (entity_id, query, language))
        qid = existing["id"] if existing else "map-" + hashlib.sha256(f"{entity_id}:{language}:{query}".encode()).hexdigest()[:20]
        self.db.execute("INSERT OR IGNORE INTO query(id,entity_id,text,language,tier,active,origin) VALUES (?,?,?,?,3,0,'map-search')", (qid, entity_id, query, language))
        lat, lon = CENTERS[state]
        if latitude is not None and longitude is not None:
            lat, lon = round(latitude, 2), round(longitude, 2)
        location = STATES.get(state, "India")
        plans = [("google", {"engine": "google", "q": query, "gl": "in", "hl": language, "location": location}), ("google_maps", {"engine": "google_maps", "type": "search", "q": query, "hl": language, "ll": f"@{lat:.2f},{lon:.2f},12z"})]
        runs, gaps = [], []
        # Prevent identical concurrent map submissions from duplicating provider spend.
        with self.lock:
            for engine, params in plans:
                try:
                    data, key, cached = self.collector.request(params)
                    if cached:
                        runs.append({"run_id": cached, "engine": engine, "cached": True, "status": "success"})
                    else:
                        result = self.pipeline.ingest(data, qid, engine, state, location, language, cache_key=key, rebuild=False)
                        if engine == "google" and result["status"] == "success":
                            self.collector.enrich_ads(result["run_id"])
                        runs.append({**result, "engine": engine, "cached": False})
                        if result["status"] != "success":
                            gaps.append({"engine": engine, "reason": "Provider returned no usable results or an error"})
                except BudgetExceeded:
                    if not runs:
                        raise
                    gaps.append({"engine": engine, "reason": "Collection budget reached; this surface was not fetched"})
                    break
                except (RuntimeError, ValueError) as exc:
                    result = self.pipeline.ingest({"error": "Map collection unavailable"}, qid, engine, state, location, language, rebuild=False)
                    runs.append({**result, "engine": engine, "cached": False})
                    gaps.append({"engine": engine, "reason": str(exc)})
                    if "rejected the configured API key" in str(exc):
                        break
            if any(not r["cached"] for r in runs):
                self.pipeline.rebuild()
        if not runs or all(r["status"] == "failed" for r in runs):
            raise RuntimeError(gaps[0]["reason"] if gaps else "Search could not be collected. Check SerpApi configuration or retry later.")
        ids = [r["run_id"] for r in runs]
        slots = ",".join("?" for _ in ids)
        rows = self.service.observations(f" AND r.id IN ({slots}) ORDER BY CASE o.kind WHEN 'local' THEN 0 WHEN 'ad' THEN 1 ELSE 2 END,o.position", ids)
        results = []
        alternatives = {}
        for row in rows:
            if row["kind"] not in {"organic", "ad", "local"}:
                continue
            facts = json.loads(row["facts_json"])
            if row["entity_id"] not in alternatives:
                alternatives[row["entity_id"]] = self.service.alternative(row["entity_id"]) if row["entity_id"] else {"domains": [], "phones": []}
            results.append({**public_observation(row), "coordinates": facts.get("gps_coordinates"), "address": facts.get("address"), "rating": facts.get("rating"), "official_alternative": alternatives[row["entity_id"]], "engine": next(r["engine"] for r in runs if r["run_id"] == row["run_id"])})
        total = self.db.one(f"SELECT COUNT(*) n FROM observation WHERE run_id IN ({slots}) AND kind IN ('organic','ad','local')", ids)["n"]
        withheld = total - len(results)
        entity = self.db.one("SELECT id,name,category FROM entity WHERE id=?", (entity_id,)) if entity_id else None
        # A two-surface spot check is not a state-level prevalence measurement.
        eligible = [r for r in results if r["engine"] == "google"]
        weighted = sum(1.5 if r["kind"] == "ad" else 1/r["position"] for r in eligible)
        flagged = sum(1.5 if r["kind"] == "ad" else 1/r["position"] for r in eligible if r["verdict"] in {"Suspicious", "Likely Fraud"})
        return {"query": query, "query_id": qid, "entity": entity, "location": location, "state": state, "runs": runs, "results": results[:60], "withheld": withheld, "gaps": gaps, "summary": {"published": len(results), "flagged": sum(r["verdict"] in {"Suspicious", "Likely Fraud"} for r in results), "verified": sum(r["verdict"] == "Verified Official" for r in results), "spot_exposure": round(flagged/weighted*100, 1) if weighted and not withheld and not gaps else None}, "official_alternative": self.service.alternative(entity_id) if entity_id else {"domains": [], "phones": []}, "note": "Google Search uses the selected city proxy or India. Maps uses the selected map area. Live search terms and coarse search-area parameters are archived; device location updates are not sent to this server."}
