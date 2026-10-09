import gzip
import hashlib
import json
import uuid
from pathlib import Path

import networkx as nx

from .db import now
from .extract import observations
from .trust import RULE_VERSION, active, score
from .advertisers import joined_facts


def registry_fingerprint(registry):
    entries = [{**r, "current": active(r)} for r in registry]
    return hashlib.sha256(json.dumps([RULE_VERSION, entries], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def redact(value):
    if isinstance(value, dict):
        return {k: ("[redacted]" if k.lower() in {"api_key", "apikey", "authorization", "access_token"} else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        import re
        return re.sub(r"(?i)(api_key=)[^&\s]+", r"\1[redacted]", value)
    return value


class Pipeline:
    def __init__(self, db):
        self.db = db

    def ingest(self, payload, query_id, engine, state, location, hl, demo=False, fetched_at=None, cache_key=None, rebuild=True):
        rid = uuid.uuid4().hex
        metadata = payload.get("search_metadata", {})
        error = payload.get("error")
        parsed = observations(payload, engine)
        status = "failed" if error or metadata.get("status") == "Error" else ("success" if parsed else "empty")
        if engine == "google_ads_transparency_center" and not error and metadata.get("status") != "Error" and (metadata.get("status") == "Success" or "ad_creatives" in payload or "advertiser" in payload):
            status = "success"
        root = self.db.settings.data_dir / "raw" / self.db.settings.mode
        root.mkdir(parents=True, exist_ok=True)
        ref = str(Path("raw") / self.db.settings.mode / (rid + ".json.gz"))
        with gzip.open(self.db.settings.data_dir / ref, "wt", encoding="utf-8") as f:
            json.dump(redact(payload), f, ensure_ascii=False)
        q = self.db.one("SELECT * FROM query WHERE id=?", (query_id,)) if query_id else None
        entities = self.db.rows("SELECT * FROM entity")
        with self.db.connect() as c:
            c.execute("INSERT INTO run VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (rid, query_id, engine, state, location, hl, fetched_at or now(), metadata.get("id"), ref, status, "Provider reported an error" if error else None, cache_key, int(demo)))
            for item in parsed if status == "success" else []:
                oid = uuid.uuid4().hex
                eid = q["entity_id"] if q else None
                if not eid:
                    text = (item["title"] + " " + (item["domain"] or "")).lower()
                    matches = [e["id"] for e in entities if any(len(a) >= 3 and a.lower() in text for a in json.loads(e["aliases"]))]
                    eid = matches[0] if len(set(matches)) == 1 else None
                c.execute("INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (oid, rid, item["kind"], item["position"], item["title"], item["snippet"], item["url"], item["domain"], eid, json.dumps(item["phones"]), item["advertiser_id"], json.dumps(item["facts"]), 0))
                c.executemany("INSERT INTO phone_seen VALUES (?,?)", [(oid, p) for p in item["phones"]])
                if engine == "google_autocomplete" and q:
                    new_id = "auto-" + hashlib.sha256(f"{eid}:{hl}:{item['title']}".encode()).hexdigest()[:20]
                    c.execute("INSERT OR IGNORE INTO query(id,entity_id,text,language,tier,active,origin) VALUES (?,?,?,?,?,0,'autocomplete')", (new_id, eid, item["title"], hl, 3))
        if rebuild:
            self.rebuild()
        return {"run_id": rid, "status": status, "observations": len(parsed) if status == "success" else 0}

    def rebuild(self):
        with self.db.scoring_lock:
            return self._rebuild()

    def ensure_current(self):
        # Expiry changes the fingerprint even when no registry edit was made.
        with self.db.scoring_lock:
            current = self.context_fingerprint()
            previous = self.db.one("SELECT value FROM meta WHERE key='scored_registry'")
            if not previous or previous["value"] != current:
                self._rebuild()

    def context_fingerprint(self, registry=None, advertisers=None, reviews=None):
        registry = self.db.rows("SELECT * FROM registry ORDER BY id") if registry is None else registry
        advertisers = self.db.rows("SELECT * FROM advertiser ORDER BY id") if advertisers is None else sorted(advertisers, key=lambda r: r["id"])
        reviews = self.db.rows("SELECT * FROM advertiser_review ORDER BY observation_id") if reviews is None else sorted(reviews, key=lambda r: r["observation_id"])
        reviews = [{**r, "current": active(r)} for r in reviews]
        return hashlib.sha256(json.dumps([registry_fingerprint(registry), advertisers, reviews], sort_keys=True).encode()).hexdigest()

    def _rebuild(self):
        all_obs = self.db.rows("SELECT o.*,r.fetched_at FROM observation o JOIN run r ON r.id=o.run_id")
        entities = {e["id"]: {**e, "aliases": json.loads(e["aliases"])} for e in self.db.rows("SELECT * FROM entity")}
        registry = self.db.rows("SELECT * FROM registry ORDER BY id")
        advertisers = {r["id"]: r for r in self.db.rows("SELECT * FROM advertiser")}
        reviews = {r["observation_id"]: r for r in self.db.rows("SELECT * FROM advertiser_review")}
        context_used = self.context_fingerprint(registry, list(advertisers.values()), list(reviews.values()))
        phone_domains = {}
        for o in all_obs:
            for p in json.loads(o["phones_json"]):
                if o["domain"]:
                    phone_domains.setdefault((o["entity_id"], p), set()).add(o["domain"])
        revision = uuid.uuid4().hex
        graph = nx.Graph()
        fingerprints = {}
        with self.db.connect() as c:
            for o in all_obs:
                item = {**o, "phones": json.loads(o["phones_json"]), "facts": joined_facts(o, advertisers, reviews)}
                verdict = score(item, entities.get(o["entity_id"]), [r for r in registry if r["entity_id"] == o["entity_id"]], reused=any(len(phone_domains.get((o["entity_id"], p), set())) >= 2 for p in item["phones"]))
                fingerprints[o["id"]] = {"observation": {k: item[k] for k in ("id", "title", "snippet", "url", "domain", "entity_id", "phones", "advertiser_id", "facts")}, "score": verdict}
                c.execute("INSERT INTO score(observation_id,rule_version,risk,verdict,signals_json,scored_at,revision) VALUES (?,?,?,?,?,?,?)", (o["id"], verdict["rule_version"], verdict["risk"], verdict["verdict"], json.dumps(verdict["signals"], ensure_ascii=False), now(), revision))
                if verdict["verdict"] not in {"Suspicious", "Likely Fraud"}:
                    continue
                node = "obs:" + o["id"]
                graph.add_node(node, observation=o)
                # Entity scoping prevents unrelated brands forming a campaign from a generic contact.
                scope = (o["entity_id"] or "unknown") + ":"
                for kind, values in [("phone", item["phones"]), ("domain", [o["domain"]] if o["domain"] else []), ("advertiser", [o["advertiser_id"]] if o["advertiser_id"] else [])]:
                    for v in values:
                        graph.add_edge(node, scope + kind + ":" + v)
            old = {r["id"]: r for r in c.execute("SELECT * FROM campaign")}
            c.execute("DELETE FROM campaign_member")
            c.execute("DELETE FROM campaign")
            for component in nx.connected_components(graph):
                members = [graph.nodes[n]["observation"] for n in component if n.startswith("obs:")]
                # Stable ID for same infrastructure; expanding a campaign invalidates prior approval.
                infrastructure = sorted(n for n in component if not n.startswith("obs:"))
                cid = "CMP-" + hashlib.sha256("|".join(infrastructure).encode()).hexdigest()[:10].upper()
                previous = old.get(cid)
                evidence_hash = hashlib.sha256(json.dumps([fingerprints[m["id"]] for m in sorted(members, key=lambda m: m["id"])], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                unchanged = previous and previous["evidence_hash"] == evidence_hash
                review = previous["review_state"] if unchanged else "pending"
                c.execute("INSERT INTO campaign(id,first_seen,last_seen,size,review_state,reviewer,reviewed_at,evidence_hash) VALUES (?,?,?,?,?,?,?,?)", (cid, min(m["fetched_at"] for m in members), max(m["fetched_at"] for m in members), len(members), review, previous["reviewer"] if unchanged else None, previous["reviewed_at"] if unchanged else None, evidence_hash))
                c.executemany("INSERT INTO campaign_member VALUES (?,?)", [(cid, m["id"]) for m in members])
            # Persist the input snapshot, not a possibly changed external context.
            c.execute("INSERT OR REPLACE INTO meta VALUES ('scored_registry',?)", (context_used,))
        self.db.log("rescore", {"revision": revision, "observations": len(all_obs)})
        return {"revision": revision, "observations": len(all_obs)}
