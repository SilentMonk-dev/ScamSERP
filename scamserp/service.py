import csv
import hashlib
import hmac
import io
import json
import math
import random
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .db import PUBLIC_SQL, now
from .extract import domain, normalize_phone
from .seed import LANGUAGES, STATES
from .trust import RULE_VERSION, active
from .advertisers import joined_facts


def public_observation(row):
    facts = json.loads(row["facts_json"])
    return {k: row[k] for k in ("id", "run_id", "kind", "position", "title", "snippet", "url", "domain", "entity_id", "entity_name", "category", "risk", "verdict", "rule_version", "state", "location", "hl", "fetched_at", "search_id", "query_id", "query_text", "demo")} | {"phones": json.loads(row["phones_json"]), "signals": json.loads(row["signals_json"]), "registry_comparison": row.get("registry_comparison"), "advertiser_evidence": facts.get("advertiser_evidence"), "advertiser_candidates": facts.get("advertiser_candidates", []), "advertiser_discovery": facts.get("advertiser_discovery"), "advertiser_relationship_review": facts.get("advertiser_relationship_review")}


class Service:
    def __init__(self, db):
        self.db = db
        if not db.one("SELECT value FROM meta WHERE key='export_salt'"):
            db.execute("INSERT OR IGNORE INTO meta VALUES ('export_salt',?)", (secrets.token_hex(32),))

    def observations(self, where="", params=()):
        from .pipeline import Pipeline
        Pipeline(self.db).ensure_current()
        return self.decorate(self.db.rows(PUBLIC_SQL + where, params))

    def decorate(self, rows):
        advertisers = {r["id"]: r for r in self.db.rows("SELECT * FROM advertiser")}
        reviews = {r["observation_id"]: r for r in self.db.rows("SELECT * FROM advertiser_review")}
        registry = defaultdict(list)
        for record in self.registry():
            registry[record["entity_id"]].append(record)
        for row in rows:
            row["facts_json"] = json.dumps(joined_facts(row, advertisers, reviews))
            records = [r for r in registry[row["entity_id"]] if r["current"]]
            domains = [r for r in records if r["kind"] == "domain"]
            phones = [r for r in records if r["kind"] == "phone"]
            if row["verdict"] == "Verified Official" and not (any(r["value"] == row["domain"] for r in domains) and all(p in {r["value"] for r in phones} for p in json.loads(row["phones_json"]))):
                row.update(verdict="Unverified", risk=0, signals_json="[]")
            row["registry_comparison"] = {"domain_match": any(r["value"] == row["domain"] for r in domains), "official_domains": domains, "official_phones": phones, "unmatched_phones": [p for p in json.loads(row["phones_json"]) if p not in {r["value"] for r in phones}] if phones else [], "phone_registry_available": bool(phones)}
        return rows

    def registry(self, entity_id=None):
        rows = self.db.rows("SELECT r.*,e.name entity_name,e.category FROM registry r JOIN entity e ON e.id=r.entity_id" + (" WHERE entity_id=?" if entity_id else "") + " ORDER BY e.name,r.kind", (entity_id,) if entity_id else ())
        for row in rows:
            row["current"] = active(row)
        return rows

    def alternative(self, entity_id):
        records = [r for r in self.registry(entity_id) if r["current"]]
        return {"domains": [r for r in records if r["kind"] == "domain"], "phones": [r for r in records if r["kind"] == "phone"]}

    def lookup(self, kind, value):
        normalized = normalize_phone(value) if kind == "phone" else domain(value)
        if not normalized:
            raise ValueError("Enter a valid Indian phone number or website")
        if kind == "phone":
            rows = self.observations(" AND o.id IN (SELECT observation_id FROM phone_seen WHERE phone=?)", (normalized,))
        else:
            rows = self.observations(" AND o.domain=?", (normalized,))
        registry = self.db.rows("SELECT r.*,e.name entity_name FROM registry r JOIN entity e ON e.id=r.entity_id WHERE r.kind=? AND r.value=?", (kind, normalized))
        match = next((r for r in registry if active(r)), None)
        entity = match["entity_id"] if match else (rows[0]["entity_id"] if rows else (registry[0]["entity_id"] if registry else None))
        name = match["entity_name"] if match else (rows[0]["entity_name"] if rows else (registry[0]["entity_name"] if registry else None))
        evidence = sorted(rows, key=lambda r: (r["risk"], r["fetched_at"]), reverse=True)
        if match:
            verdict, risk, explanation = "Verified Official", 0, "Matches a current, source-checked registry entry. This verifies the contact, not any caller's identity."
            hi = "यह संपर्क वर्तमान सत्यापित रिकॉर्ड से मेल खाता है। इससे कॉल करने वाले की पहचान साबित नहीं होती।"
        elif evidence:
            verdict, risk = evidence[0]["verdict"], evidence[0]["risk"]
            explanation = "Based on published audit evidence. An unmatched number is not proof of wrongdoing."
            hi = "यह परिणाम प्रकाशित ऑडिट प्रमाण पर आधारित है। रिकॉर्ड में नंबर न होना गलत काम का प्रमाण नहीं है।"
        elif registry:
            verdict, risk, explanation = "Unverified", None, "This registry entry is pending review or has expired. Recheck the source before using it."
            hi = "इस रिकॉर्ड की समीक्षा बाकी है या इसकी अवधि खत्म हो गई है। मूल वेबसाइट पर दोबारा जांचें।"
        else:
            verdict, risk, explanation = "No data", None, "We have no published evidence for this item. No data does not mean safe."
            hi = "इस संपर्क का प्रकाशित प्रमाण उपलब्ध नहीं है। डेटा न होने का मतलब सुरक्षित होना नहीं है।"
        return {"type": kind, "normalized": normalized, "verdict": verdict, "risk": risk, "confidence": "Registry match" if match else ("Multiple evidence families" if evidence and len({s["family"] for s in json.loads(evidence[0]["signals_json"]) if s["points"] > 0}) >= 2 else "Limited evidence"), "confidence_note": "Evidence strength, not a probability of fraud.", "explanation": explanation, "explanation_hi": hi, "entity_id": entity, "entity_name": name, "registry_match": bool(match), "registry_source": match, "seen_count": len(rows), "locations": sorted({r["state"] for r in rows}), "first_seen": min((r["fetched_at"] for r in rows), default=None), "last_seen": max((r["fetched_at"] for r in rows), default=None), "evidence": [public_observation(r) for r in evidence[:5]], "official_alternative": self.alternative(entity) if entity else {"domains": [], "phones": []}, "demo": self.db.settings.mode == "demo", "live_available": self.db.settings.public_live and bool(self.db.settings.api_key) and self.db.settings.mode == "live"}

    def runs(self, category="all", language="all", window=30, entity_id=None, state="all", search=""):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=window)).isoformat()
        where, params = " AND r.fetched_at>=?", [cutoff]
        if category != "all":
            where += " AND e.category=?"
            params.append(category)
        if language != "all":
            where += " AND COALESCE(q.language,r.hl)=?"
            params.append(language)
        if entity_id:
            where += " AND o.entity_id=?"
            params.append(entity_id)
        if state != "all":
            where += " AND r.state=?"
            params.append(state)
        if search:
            where += " AND instr(lower(q.text),lower(?))>0"
            params.append(search)
        rows = self.observations(where + " AND o.kind IN ('organic','ad','local')", params)
        grouped = defaultdict(list)
        for row in rows:
            grouped[row["run_id"]].append(row)
        result = []
        # Exclude a complete run when any ranked result is withheld; do not make hidden findings look clean.
        private = PUBLIC_SQL.split("WHERE o.hidden=0")[0]
        withheld = {r["run_id"] for r in self.db.rows(private + " WHERE r.status='success' AND o.kind IN ('organic','ad','local') AND (o.hidden=1 OR (s.verdict='Likely Fraud' AND NOT EXISTS (SELECT 1 FROM campaign_member m JOIN campaign c ON c.id=m.campaign_id WHERE m.observation_id=o.id AND c.review_state='approved')))" + where, params)}
        for rid, entries in grouped.items():
            if rid in withheld:
                continue
            weights = [1.5 if r["kind"] == "ad" else 1 / r["position"] for r in entries]
            total = sum(weights)
            exposure = sum(w for w, r in zip(weights, entries) if r["verdict"] in {"Suspicious", "Likely Fraud"}) / total
            result.append({"id": rid, "state": entries[0]["state"], "language": entries[0]["query_language"] or entries[0]["hl"], "category": entries[0]["category"], "date": entries[0]["fetched_at"][:10], "fetched_at": entries[0]["fetched_at"], "query_id": entries[0]["query_id"], "intent_id": entries[0]["intent_id"], "entity_id": entries[0]["entity_id"], "engine": entries[0]["engine"], "exposure": exposure, "n": len(entries)})
        return result, len(withheld)

    def summarize(self, runs):
        n = sum(r["n"] for r in runs)
        if len(runs) < self.db.settings.min_runs:
            return {"exposure": None, "n": n, "n_runs": len(runs), "ci_low": None, "ci_high": None, "insufficient": True}
        mean = sum(r["exposure"] for r in runs) / len(runs)
        # Cluster bootstrap by query; avoids treating every result in a SERP as independent.
        blocks = defaultdict(list)
        for r in runs:
            blocks[r["query_id"] or r["id"]].append(r["exposure"])
        groups = list(blocks.values())
        estimates = []
        rng = random.Random(42)
        if len(groups) > 1:
            for _ in range(300):
                sampled = [x for group in rng.choices(groups, k=len(groups)) for x in group]
                estimates.append(sum(sampled) / len(sampled))
            estimates.sort()
        return {"exposure": round(mean * 100, 1), "n": n, "n_runs": len(runs), "ci_low": round(estimates[7] * 100, 1) if estimates else None, "ci_high": round(estimates[292] * 100, 1) if estimates else None, "insufficient": False, "ci_method": "Exploratory 95% query-cluster bootstrap; not population prevalence"}

    def map(self, category="all", language="all", window=30, state="all", search=""):
        runs, withheld = self.runs(category, language, window, state=state, search=search)
        states = [{"state": region, "location": loc, **self.summarize([r for r in runs if r["state"] == region])} for region, loc in STATES.items() if state == "all" or region == state]
        return {"states": states, "summary": self.summarize(runs), "demo": self.db.settings.mode == "demo", "coverage_note": "Six city proxies; unmeasured states have no data. Search results vary with location and personalization.", "withheld_runs": withheld}

    def trend(self, category="all", language="all", window=30, state="all", search=""):
        runs, _ = self.runs(category, language, window, state=state, search=search)
        dates = sorted({r["date"] for r in runs})
        return [{"date": d, **self.summarize([r for r in runs if r["date"] == d])} for d in dates]

    def equity(self, category="all", window=30, state="all", search=""):
        # Compare only common query entities, states and dates, not incomparable samples.
        runs, _ = self.runs(category, "all", window, state=state)
        lang_codes = list(LANGUAGES)[:6]
        keys = lambda r: (r["entity_id"], r["intent_id"], r["state"], r["date"], r["engine"])
        comparable = [r for r in runs if r["intent_id"]]
        if search:
            intents = {(q["entity_id"], q["intent_id"]) for q in self.db.rows("SELECT entity_id,intent_id FROM query WHERE instr(lower(text),lower(?))>0 AND intent_id IS NOT NULL", (search,))}
            comparable = [r for r in comparable if (r["entity_id"], r["intent_id"]) in intents]
        sets = [{keys(r) for r in comparable if r["language"] == lang} for lang in lang_codes]
        common = set.intersection(*sets) if sets else set()
        return {"matched_cells": len(common), "languages": [{"language": l, "name": LANGUAGES[l], **self.summarize([r for r in comparable if r["language"] == l and keys(r) in common])} for l in lang_codes], "note": "Matched entity, translated intent, city, day and search engine. Unmapped autocomplete and free-text queries are excluded. Synthetic differences are not language-equity findings."}

    def risk_matrix(self, category="all", language="all", window=30, state="all", query_id=None, limit=100, offset=0, search=""):
        runs, withheld = self.runs(category, language, window, state=state, search=search)
        grouped = defaultdict(list)
        for run in runs:
            if (state == "all" or run["state"] == state) and (not query_id or run["query_id"] == query_id):
                grouped[(run["query_id"], run["state"], run["language"], run["engine"])].append(run)
        clauses, params = ["(q.active=1 OR q.origin='map-search')"], []
        for column, value in [("e.category", category), ("q.language", language)]:
            if value != "all":
                clauses.append(column + "=?")
                params.append(value)
        if query_id:
            clauses.append("q.id=?")
            params.append(query_id)
        if search:
            clauses.append("instr(lower(q.text),lower(?))>0")
            params.append(search)
        queries = {q["id"]: q for q in self.db.rows("SELECT q.* FROM query q LEFT JOIN entity e ON e.id=q.entity_id WHERE " + " AND ".join(clauses), params)}
        cells = {}
        for q in queries.values():
            for region in STATES if state == "all" else [state]:
                for engine in ["google"] + (["google_local"] if q["local_intent"] else []):
                    cells[(q["id"], region, q["language"], engine)] = {"query_id": q["id"], "query": q["text"], "intent_id": q["intent_id"], "state": region, "language": q["language"], "engine": engine, "latest": None, "collection_status": "not collected", **self.summarize([])}
        cutoff = (datetime.now(timezone.utc) - timedelta(days=window)).isoformat()
        for r in self.db.rows("SELECT r.*,q.language audit_language FROM run r JOIN query q ON q.id=r.query_id WHERE r.fetched_at>=? AND r.engine IN ('google','google_local','google_maps') ORDER BY r.fetched_at", (cutoff,)):
            if r["query_id"] not in queries or (state != "all" and r["state"] != state):
                continue
            key = (r["query_id"], r["state"], r["audit_language"], r["engine"])
            q = queries[r["query_id"]]
            cell = cells.setdefault(key, {"query_id": q["id"], "query": q["text"], "intent_id": q["intent_id"], "state": r["state"], "language": r["audit_language"], "engine": r["engine"], **self.summarize([])})
            cell.update(latest=r["fetched_at"], collection_status=r["status"])
        for (qid, region, lang, engine), entries in grouped.items():
            if qid not in queries:
                continue
            q = queries[qid]
            key = (qid, region, q["language"], engine)
            cells.setdefault(key, {"query_id": qid, "query": q["text"], "intent_id": q["intent_id"], "state": region, "language": q["language"], "engine": engine, "latest": max(r["fetched_at"] for r in entries), "collection_status": "success"}).update(self.summarize(entries))
        for cell in cells.values():
            if cell["collection_status"] == "success" and cell["n_runs"] == 0:
                cell["collection_status"] = "withheld"
        items = sorted(cells.values(), key=lambda x: (x["latest"] or "", x["query"], x["state"]), reverse=True)
        return {"items": items[offset:offset + limit], "total": len(items), "offset": offset, "withheld_runs_in_category_language_window": withheld, "note": "Collected query/location/language cells, separated by engine. Fewer than the minimum audit runs returns no exposure estimate; this is not population prevalence."}

    def query(self, qid, state=None):
        query = self.db.one("SELECT q.*,e.name entity_name,e.category FROM query q JOIN entity e ON e.id=q.entity_id WHERE q.id=?", (qid,))
        if not query:
            return None
        runs = self.db.rows("SELECT * FROM run WHERE query_id=? ORDER BY fetched_at DESC LIMIT 30", (qid,))
        latest = next((r for r in runs if r["status"] == "success" and r["engine"] in {"google", "google_local", "google_maps"} and (not state or r["state"] == state)), None)
        entries = self.observations(" AND r.id=? ORDER BY CASE o.kind WHEN 'ad' THEN 0 ELSE 1 END,o.position", (latest["id"],)) if latest else []
        return {"query": query, "run": {k: latest[k] for k in latest if k not in {"raw_ref", "cache_key"}} if latest else None, "results": [public_observation(r) for r in entries], "runs": [{k: r[k] for k in ("id", "engine", "state", "hl", "fetched_at", "status", "search_id")} for r in runs], "withheld": self.db.one("SELECT COUNT(*) n FROM observation WHERE run_id=?", (latest["id"],))["n"] - len(entries) if latest else 0}

    def campaigns(self):
        from .pipeline import Pipeline
        Pipeline(self.db).ensure_current()
        return self.db.rows("SELECT id,first_seen,last_seen,size,review_state FROM campaign WHERE review_state='approved' ORDER BY size DESC")

    def export(self):
        salt = self.db.one("SELECT value FROM meta WHERE key='export_salt'")["value"].encode()
        def token(value):
            return hmac.new(salt, value.encode(), hashlib.sha256).hexdigest()[:24] if value else None
        return [{"observation_id": token(r["id"]), "entity": r["entity_name"], "category": r["category"], "state": r["state"], "language": r["hl"], "observed_date": r["fetched_at"][:10], "kind": r["kind"], "position": r["position"], "domain_token": token(r["domain"]), "phone_tokens": [token(p) for p in json.loads(r["phones_json"])], "risk": r["risk"], "verdict": r["verdict"], "signals": [s["code"] for s in json.loads(r["signals_json"])], "rule_version": r["rule_version"], "synthetic": bool(r["demo"])} for r in self.observations()]

    def evaluation(self):
        labels = self.db.rows("SELECT l.*,s.verdict predicted FROM evaluation_label l JOIN score s ON s.id=(SELECT MAX(s2.id) FROM score s2 WHERE s2.observation_id=l.observation_id)")
        real = [r for r in labels if not r["synthetic"]]
        def metrics(rows):
            predicted = [r for r in rows if r["predicted"] == "Likely Fraud"]
            actual = [r for r in rows if r["verdict"] == "Likely Fraud"]
            tp = sum(r["verdict"] == "Likely Fraud" for r in predicted)
            return {"n": len(rows), "precision": round(tp / len(predicted), 3) if predicted else None, "recall": round(tp / len(actual), 3) if actual else None, "official_false_accusations": sum(r["verdict"] == "Verified Official" and r["predicted"] in {"Suspicious", "Likely Fraud"} for r in rows)}
        return {"real": metrics(real), "synthetic": metrics([r for r in labels if r["synthetic"]]), "per_language": [{"language": l, **metrics([r for r in real if r["language"] == l])} for l in list(LANGUAGES)[:6]], "targets": {"precision": 0.9, "recall": 0.7, "human_labels": 300}, "rule_version": RULE_VERSION, "limitations": ["Independent real-world evaluation and human registry checks remain required.", "Query translations use seed templates and require native-speaker review.", "Missing Ads Transparency verification and account-creation fields remain unknown; sampled creative dates are not account age.", "RDAP domain age is optional; absence never adds risk.", "Six city proxies and national Autocomplete do not measure all search users. See collection coverage for freshness and budget gaps."]}


def csv_text(rows):
    out = io.StringIO(newline="")
    fields = list(rows[0]) if rows else ["observation_id", "entity", "category", "state", "language", "observed_date", "kind", "position", "domain_token", "phone_tokens", "risk", "verdict", "signals", "rule_version", "synthetic"]
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        safe = {}
        for key, value in row.items():
            value = json.dumps(value, ensure_ascii=False) if isinstance(value, list) else value
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                value = "'" + value
            safe[key] = value
        writer.writerow(safe)
    return out.getvalue()
