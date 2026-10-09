import hashlib
import hmac
import json
import secrets
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .collector import BudgetExceeded, Collector
from .config import Settings
from .db import Database, now
from .extract import domain, host, links, normalize_phone, phones
from .pipeline import Pipeline
from .map_search import MapSearch
from .seed import LANGUAGES, STATES, seed_demo, seed_registry
from .service import Service, csv_text, public_observation
from .trust import LABELS

STATIC = Path(__file__).parent / "static"


class TextLookup(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class MapSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    language: Literal["en", "hi", "ta", "te", "bn", "mr"] = "en"
    state: str = Field(default="India", max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    entity_id: str | None = Field(default=None, max_length=50)


class Dispute(BaseModel):
    target_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=10, max_length=2000)


class RegistryRecord(BaseModel):
    entity_id: str = Field(min_length=1, max_length=50)
    kind: Literal["domain", "phone", "social", "email", "intermediary"]
    value: str = Field(min_length=1, max_length=500)
    display: str = Field(min_length=1, max_length=500)
    source_url: str = Field(min_length=1, max_length=2048)
    verifier: str = Field(min_length=2, max_length=100)
    verified_at: str | None = None
    expires_at: str | None = None
    status: Literal["pending", "verified", "rejected"] = "pending"

    @field_validator("source_url")
    @classmethod
    def source_valid(cls, v):
        if not v.startswith("https://") or not host(v):
            raise ValueError("Use an HTTPS primary-source URL")
        return v


class Review(BaseModel):
    decision: Literal["approved", "rejected", "pending"]
    reviewer: str = Field(min_length=2, max_length=100)


class CampaignReview(Review):
    evidence_hash: str = Field(min_length=64, max_length=64)


class AdvertiserReview(BaseModel):
    observation_id: str = Field(min_length=1, max_length=64)
    advertiser_id: str = Field(pattern=r"^AR\d+$", max_length=40)
    relationship: Literal["linked", "unlinked", "unknown"]
    source_url: str = Field(min_length=8, max_length=2048)
    reviewer: str = Field(min_length=2, max_length=100)
    verified_at: str
    expires_at: str


class Collect(BaseModel):
    query_id: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    engine: Literal["google", "google_autocomplete", "google_local"] = "google"


class Label(BaseModel):
    observation_id: str = Field(min_length=1, max_length=64)
    verdict: Literal["Verified Official", "No Issue Found", "Unverified", "Suspicious", "Likely Fraud"]
    source_url: str = Field(min_length=8, max_length=2048)
    reviewer: str = Field(min_length=2, max_length=100)


def create_app(settings=None):
    settings = settings or Settings()
    db = Database(settings)
    pipeline = Pipeline(db)
    service = Service(db)
    collector = Collector(db, pipeline)
    map_searcher = MapSearch(db, pipeline, service, collector)

    @asynccontextmanager
    async def lifespan(app):
        seed_registry(db)
        seed_demo(db, pipeline)
        runner = None
        if settings.scheduler_enabled:
            from .scheduler import SchedulerRunner
            runner = SchedulerRunner(db, collector, service)
            runner.start()
        try:
            yield
        finally:
            if runner:
                runner.stop()

    app = FastAPI(title="ScamSERP", version="1.1.0", lifespan=lifespan)
    app.state.db, app.state.pipeline, app.state.service, app.state.collector = db, pipeline, service, collector
    app.state.map_searcher = map_searcher
    hits = defaultdict(deque)
    ip_salt = secrets.token_bytes(32)

    def admin(authorization: str = Header(default="")):
        if not settings.admin_token:
            raise HTTPException(503, "Admin access is disabled until SCAMSERP_ADMIN_TOKEN is configured")
        if not hmac.compare_digest(authorization, "Bearer " + settings.admin_token):
            raise HTTPException(401, "Admin authorization required", headers={"WWW-Authenticate": "Bearer"})

    @app.middleware("http")
    async def safeguards(request: Request, call_next):
        from starlette.responses import JSONResponse
        length = request.headers.get("content-length", "0")
        if not length.isdigit() or int(length) > 16384:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
        # Enforce a real byte cap even for streaming/chunked bodies; no body is logged or stored.
        if request.method in {"POST", "PUT", "PATCH"}:
            size = 0
            chunks = []
            async for chunk in request.stream():
                size += len(chunk)
                if size > 16384:
                    return JSONResponse({"detail": "Request too large"}, status_code=413)
                chunks.append(chunk)
            # Starlette's cached request replays this bounded body to downstream parsing.
            request._body = b"".join(chunks)
        if request.url.path.startswith("/api"):
            stamp = time.monotonic()
            key = hmac.new(ip_salt, (request.client.host if request.client else "local").encode(), hashlib.sha256).hexdigest()
            queue = hits[key]
            while queue and queue[0] < stamp - 60:
                queue.popleft()
            if len(queue) >= settings.rate_limit:
                return JSONResponse({"detail": "Too many requests; try again in a minute"}, status_code=429, headers={"Retry-After": "60"})
            queue.append(stamp)
            if len(hits) > 10000:
                for old_key in list(hits):
                    if not hits[old_key] or hits[old_key][-1] < stamp - 60:
                        del hits[old_key]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "geolocation=(self)"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' https://maps.googleapis.com https://maps.gstatic.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data: https://*.googleapis.com https://*.gstatic.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self' https://maps.googleapis.com https://*.googleapis.com; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api") else "public, max-age=300"
        return response

    @app.get("/healthz")
    def health():
        return {"status": "ok", "mode": settings.mode, "database": bool(db.one("SELECT 1 ok"))}

    @app.get("/api/meta")
    def meta():
        return {"mode": settings.mode, "languages": LANGUAGES, "states": STATES, "categories": sorted({e["category"] for e in db.rows("SELECT category FROM entity")}), "entities": db.rows("SELECT id,name,category FROM entity ORDER BY name"), "registry_current": db.one("SELECT COUNT(DISTINCT entity_id) n FROM registry WHERE status='verified' AND expires_at>?", (now(),))["n"], "queries": db.one("SELECT COUNT(*) n FROM query WHERE active=1")["n"], "observations": len(service.observations()), "live_available": settings.public_live and bool(settings.api_key) and settings.mode == "live", "google_maps_api_key": settings.google_maps_api_key, "map_search_available": settings.mode == "live" and settings.map_search_enabled and bool(settings.api_key), "min_runs": settings.min_runs}

    @app.get("/api/lookup")
    def lookup(type: Literal["phone", "domain"], value: str = Query(min_length=1, max_length=2048)):
        try:
            return service.lookup(type, value)
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.post("/api/lookup/text")
    def lookup_text(body: TextLookup):
        ps, ds = phones(body.text), links(body.text)
        if not ps and not ds:
            p, d = normalize_phone(body.text), domain(body.text)
            if p:
                ps = [p]
            elif d:
                ds = [d]
        return {"items": [service.lookup("phone", p.split(":")[-1]) for p in ps[:10]] + [service.lookup("domain", d) for d in ds[:10]], "empty": not ps and not ds, "note": "Lookup input is processed in memory and is not stored. Live searches are sent to SerpApi only when explicitly requested."}

    @app.post("/api/lookup/live")
    def live(body: TextLookup):
        if not settings.public_live or settings.mode != "live":
            raise HTTPException(403, "Public live checks are disabled")
        p, d = normalize_phone(body.text), domain(body.text)
        value = p.split(":")[-1] if p else d
        if not value:
            raise HTTPException(422, "Live check accepts a single number or domain")
        try:
            result = collector.targeted(value)
            return {"collection": result, "result": service.lookup("phone" if p else "domain", value), "privacy_note": "Targeted search terms may appear in provider search metadata retained for reproducibility."}
        except BudgetExceeded as exc:
            raise HTTPException(429, str(exc))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(503, str(exc))

    @app.get("/api/registry")
    def registry(entity_id: str | None = None):
        return {"records": service.registry(entity_id)}

    @app.get("/api/map")
    def risk_map(category: str = "all", language: str = "all", window: int = Query(30, ge=1, le=365), state: str = "all", search: str = Query("", max_length=200)):
        return service.map(category, language, window, state, search)

    @app.get("/api/risk/matrix")
    def risk_matrix(category: str = "all", language: str = "all", window: int = Query(30, ge=1, le=365), state: str = "all", query_id: str | None = None, limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0), search: str = Query("", max_length=200)):
        return service.risk_matrix(category, language, window, state, query_id, limit, offset, search)

    @app.get("/api/coverage")
    def audit_coverage():
        from .scheduler import coverage
        return coverage(db, collector)

    @app.post("/api/map/search")
    def map_search(body: MapSearchRequest):
        if settings.mode != "live" or not settings.map_search_enabled:
            raise HTTPException(403, "Live map search is disabled. Configure live mode and SCAMSERP_MAP_SEARCH=true.")
        if not settings.api_key:
            raise HTTPException(503, "SerpApi is not configured")
        if (body.latitude is None) != (body.longitude is None):
            raise HTTPException(422, "Supply both search-area coordinates or neither")
        try:
            return map_searcher.search(**body.model_dump())
        except BudgetExceeded as exc:
            raise HTTPException(429, str(exc))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        except RuntimeError as exc:
            raise HTTPException(503, str(exc))

    @app.get("/api/trend")
    def trend(category: str = "all", language: str = "all", window: int = Query(30, ge=1, le=365), state: str = "all", search: str = Query("", max_length=200)):
        return service.trend(category, language, window, state, search)

    @app.get("/api/equity")
    def equity(category: str = "all", window: int = Query(30, ge=1, le=365), state: str = "all", search: str = Query("", max_length=200)):
        return service.equity(category, window, state, search)

    @app.get("/api/queries")
    def queries(search: str = Query("", max_length=100), category: str = "all", language: str = "all", limit: int = Query(60, ge=1, le=200), offset: int = Query(0, ge=0)):
        clauses, params = ["q.active=1", "q.text LIKE ? ESCAPE '\\'"], ["%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"]
        if category != "all":
            clauses.append("e.category=?")
            params.append(category)
        if language != "all":
            clauses.append("q.language=?")
            params.append(language)
        base = " FROM query q JOIN entity e ON e.id=q.entity_id WHERE " + " AND ".join(clauses)
        total = db.one("SELECT COUNT(*) n" + base, params)["n"]
        items = db.rows("SELECT q.*,e.name entity_name,e.category,(SELECT COUNT(*) FROM run r WHERE r.query_id=q.id) runs" + base + " ORDER BY runs DESC,q.tier,q.id LIMIT ? OFFSET ?", [*params, limit, offset])
        return {"items": items, "total": total, "offset": offset}

    @app.get("/api/queries/{qid}")
    def query_detail(qid: str, state: str | None = None):
        item = service.query(qid, state)
        if not item:
            raise HTTPException(404, "Query not found")
        return item

    @app.get("/api/states/{state}/queries")
    def state_queries(state: str, category: str = "all", language: str = "all", window: int = Query(30, ge=1, le=365)):
        if state not in STATES:
            return {"items": [], "note": "This state is not yet sampled"}
        runs, _ = service.runs(category, language, window)
        grouped = {}
        for run in runs:
            if run["state"] == state and run["query_id"]:
                grouped.setdefault(run["query_id"], []).append(run)
        items = []
        for qid, rs in grouped.items():
            q = db.one("SELECT text,language,entity_id FROM query WHERE id=?", (qid,))
            items.append({"id": qid, **q, "exposure": round(sum(r["exposure"] for r in rs) / len(rs) * 100, 1), "n_runs": len(rs)})
        return {"items": sorted(items, key=lambda q: q["exposure"], reverse=True)[:12], "note": "Highest position-weighted exposure among eligible sampled queries"}

    @app.get("/api/entities/{eid}/report")
    def entity_report(eid: str):
        entity = db.one("SELECT id,name,category FROM entity WHERE id=?", (eid,))
        if not entity:
            raise HTTPException(404, "Entity not found")
        runs, _ = service.runs(entity_id=eid)
        return {"entity": entity, "summary": service.summarize(runs), "registry": service.registry(eid), "findings": [public_observation(r) for r in service.observations(" AND o.entity_id=? ORDER BY s.risk DESC LIMIT 20", (eid,))]}

    @app.get("/api/autocomplete/watchlist")
    def watchlist():
        rows = service.observations(" AND o.kind='autocomplete' ORDER BY r.fetched_at DESC LIMIT 200")
        grouped = {}
        for r in rows:
            key = (r["title"], r["hl"])
            if key not in grouped:
                grouped[key] = {"text": r["title"], "language": r["hl"], "entity": r["entity_name"], "first_seen": r["fetched_at"], "last_seen": r["fetched_at"], "seen": 0, "demo": r["demo"], "note": "Suggestion to monitor; wording alone is not a fraud verdict."}
            grouped[key]["seen"] += 1
            grouped[key]["first_seen"] = min(grouped[key]["first_seen"], r["fetched_at"])
        return {"items": list(grouped.values())}

    @app.get("/api/campaigns")
    def campaigns():
        return {"items": service.campaigns()}

    @app.get("/api/campaigns/{cid}")
    def campaign_detail(cid: str):
        campaign = next((c for c in service.campaigns() if c["id"] == cid), None)
        if not campaign:
            raise HTTPException(404, "Published campaign not found")
        rows = service.observations(" AND o.id IN (SELECT observation_id FROM campaign_member WHERE campaign_id=?) ORDER BY s.risk DESC LIMIT 20", (cid,))
        return {"campaign": campaign, "findings": [public_observation(r) for r in rows]}

    @app.post("/api/disputes", status_code=201)
    def dispute(body: Dispute):
        if not db.one("SELECT id FROM observation WHERE id=?", (body.target_id,)):
            raise HTTPException(404, "Finding not found")
        id = uuid.uuid4().hex
        with db.connect() as c:
            c.execute("INSERT INTO dispute(id,target_id,message,created_at) VALUES (?,?,?,?)", (id, body.target_id, body.message, now()))
            c.execute("UPDATE observation SET hidden=1 WHERE id=?", (body.target_id,))
        return {"id": id, "status": "pending", "message": "Finding hidden pending review"}

    @app.post("/api/registry/suggestions", status_code=201)
    def suggestion(body: RegistryRecord):
        if not db.one("SELECT id FROM entity WHERE id=?", (body.entity_id,)):
            raise HTTPException(404, "Entity not found")
        id = uuid.uuid4().hex
        db.execute("INSERT INTO suggestion(id,entity_id,kind,value,source_url,created_at) VALUES (?,?,?,?,?,?)", (id, body.entity_id, body.kind, body.value, body.source_url, now()))
        return {"id": id, "status": "pending", "message": "Suggestions require review and never alter verdicts automatically"}

    @app.get("/api/export")
    def export(format: Literal["json", "csv"] = "json"):
        rows = service.export()
        if format == "csv":
            return Response(csv_text(rows), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="scamserp-observations.csv"'})
        return {"license": "CC BY 4.0 for original derived findings; third-party source rights reserved", "provenance": settings.mode, "dictionary": "/api/data-dictionary", "observations": rows}

    @app.get("/api/data-dictionary")
    def dictionary():
        return json.loads((Path(__file__).parent / "data" / "dictionary.json").read_text(encoding="utf-8"))

    @app.get("/api/evaluation")
    def evaluation():
        return service.evaluation()

    @app.get("/api/digest")
    def digest(format: Literal["markdown", "html"] = "markdown"):
        from .reports import digest_content
        content = digest_content(service, format)
        return HTMLResponse(content) if format == "html" else Response(content, media_type="text/markdown; charset=utf-8")

    @app.get("/api/report/{oid}")
    def report(oid: str):
        rows = service.observations(" AND o.id=?", (oid,))
        if not rows:
            raise HTTPException(404, "Published finding not found")
        r = rows[0]
        text = f"{'SYNTHETIC DEMO — DO NOT SUBMIT TO AUTHORITIES. ' if r['demo'] else ''}ScamSERP evidence summary\nFinding: {r['id']}\nQuery: {r['query_text']}\nAs seen from: {r['location']}\nObserved: {r['fetched_at']}\nResult: {r['kind']} at position {r['position']}\nVerdict: {r['verdict']} ({r['risk']}/100; {r['rule_version']})\nSearch ID: {r['search_id']}\nSignals: " + "; ".join(s["reason"] for s in json.loads(r["signals_json"])) + "\nThis records indicators, not a legal determination. Check the evidence before submitting."
        return {"text": text, "channels": [{"name": "Cybercrime portal", "url": "https://cybercrime.gov.in/"}, {"name": "Chakshu", "url": "https://sancharsaathi.gov.in/sfc/"}], "demo": bool(r["demo"])}

    @app.get("/api/admin/overview", dependencies=[Depends(admin)])
    def admin_overview():
        pipeline.ensure_current()
        return {"mode": settings.mode, "api_configured": bool(settings.api_key), "budget": {"daily_cap": settings.daily_cap, "monthly_cap": settings.monthly_cap, "daily_used": db.one("SELECT COUNT(*) n FROM budget WHERE spent_at>=?", (now()[:10],))["n"], "monthly_used": db.one("SELECT COUNT(*) n FROM budget WHERE spent_at>=?", (now()[:7] + "-01",))["n"]}, "campaigns": db.rows("SELECT * FROM campaign ORDER BY last_seen DESC"), "disputes": db.rows("SELECT * FROM dispute WHERE status='pending'"), "suggestions": db.rows("SELECT * FROM suggestion WHERE status='pending'"), "registry_pending": db.rows("SELECT * FROM registry WHERE status!='verified' OR expires_at<=?", (now(),)), "failures": db.rows("SELECT id,engine,state,fetched_at,status,error FROM run WHERE status IN ('failed','empty') ORDER BY fetched_at DESC LIMIT 50"), "query_candidates": db.rows("SELECT * FROM query WHERE active=0 AND origin='autocomplete' LIMIT 50"), "advertisers": db.rows("SELECT * FROM advertiser LIMIT 200"), "ad_candidates": db.rows("SELECT id,title,advertiser_id,facts_json FROM observation WHERE kind='ad' ORDER BY rowid DESC LIMIT 100")}

    @app.post("/api/admin/registry", dependencies=[Depends(admin)])
    def update_registry(body: RegistryRecord):
        from datetime import datetime, timezone
        if not db.one("SELECT id FROM entity WHERE id=?", (body.entity_id,)):
            raise HTTPException(404, "Entity not found")
        data = body.model_dump()
        if body.kind in {"domain", "intermediary"}:
            data["value"] = domain(body.value)
            # Prevent authorizing a shared Google namespace rather than a single product.
            if data["value"] in {"google.com", "github.com", "wordpress.com", "blogspot.com"}:
                raise HTTPException(422, "Shared hosting/platform roots cannot be verified as an entity's domain")
        elif body.kind == "phone":
            data["value"] = normalize_phone(body.value)
        if not data["value"]:
            raise HTTPException(422, "Invalid registry value")
        if body.status == "verified":
            try:
                verified = datetime.fromisoformat(body.verified_at.replace("Z", "+00:00"))
                expiry = datetime.fromisoformat(body.expires_at.replace("Z", "+00:00"))
                if verified.tzinfo is None or expiry.tzinfo is None or not (verified <= datetime.now(timezone.utc) < expiry) or expiry <= verified:
                    raise ValueError()
                data["verified_at"] = verified.astimezone(timezone.utc).isoformat(timespec="seconds")
                data["expires_at"] = expiry.astimezone(timezone.utc).isoformat(timespec="seconds")
            except (AttributeError, ValueError, TypeError):
                raise HTTPException(422, "Verification and future expiry must be valid timezone-aware dates")
        before = db.one("SELECT * FROM registry WHERE entity_id=? AND kind=? AND value=?", (body.entity_id, body.kind, data["value"]))
        with db.connect() as c:
            c.execute("INSERT INTO registry(entity_id,kind,value,display,source_url,verifier,verified_at,expires_at,status) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(entity_id,kind,value) DO UPDATE SET display=excluded.display,source_url=excluded.source_url,verifier=excluded.verifier,verified_at=excluded.verified_at,expires_at=excluded.expires_at,status=excluded.status", tuple(data[k] for k in ("entity_id", "kind", "value", "display", "source_url", "verifier", "verified_at", "expires_at", "status")))
            record = c.execute("SELECT id FROM registry WHERE entity_id=? AND kind=? AND value=?", (body.entity_id, body.kind, data["value"])).fetchone()[0]
            c.execute("INSERT INTO registry_history(record_id,before_json,after_json,changed_at,actor) VALUES (?,?,?,?,?)", (record, json.dumps(before), json.dumps(data), now(), body.verifier))
        return {"record_id": record, "rescore": pipeline.rebuild()}

    @app.post("/api/admin/campaigns/{cid}/review", dependencies=[Depends(admin)])
    def review_campaign(cid: str, body: CampaignReview):
        pipeline.ensure_current()
        with db.scoring_lock, db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            campaign = c.execute("SELECT * FROM campaign WHERE id=?", (cid,)).fetchone()
            if not campaign:
                raise HTTPException(404, "Campaign not found")
            if not hmac.compare_digest(campaign["evidence_hash"] or "", body.evidence_hash):
                raise HTTPException(409, "Evidence changed. Reload and inspect the current campaign before reviewing.")
            c.execute("UPDATE campaign SET review_state=?,reviewer=?,reviewed_at=? WHERE id=?", (body.decision, body.reviewer, now(), cid))
        db.log("campaign_review", {"id": cid, **body.model_dump()})
        return {"id": cid, "review_state": body.decision}

    @app.get("/api/admin/campaigns/{cid}", dependencies=[Depends(admin)])
    def private_campaign(cid: str, limit: int = Query(200, ge=1, le=200), offset: int = Query(0, ge=0)):
        pipeline.ensure_current()
        row = db.one("SELECT * FROM campaign WHERE id=?", (cid,))
        if not row:
            raise HTTPException(404, "Campaign not found")
        from .db import PUBLIC_SQL
        # Admin query intentionally omits publication gates, and never exposes raw credentials.
        base = PUBLIC_SQL.split("WHERE o.hidden=0")[0]
        rows = db.rows(base + " WHERE o.id IN (SELECT observation_id FROM campaign_member WHERE campaign_id=?) ORDER BY s.risk DESC,o.id LIMIT ? OFFSET ?", (cid, limit, offset))
        return {"campaign": row, "findings": [public_observation(r) for r in service.decorate(rows)]}

    @app.post("/api/admin/advertisers/review", dependencies=[Depends(admin)])
    def review_advertiser(body: AdvertiserReview):
        from datetime import datetime, timezone
        observation = db.one("SELECT * FROM observation WHERE id=? AND kind='ad'", (body.observation_id,))
        if not observation or not db.one("SELECT id FROM advertiser WHERE id=?", (body.advertiser_id,)):
            raise HTTPException(404, "Collected ad or advertiser not found")
        if not body.source_url.startswith("https://") or not host(body.source_url):
            raise HTTPException(422, "Use an HTTPS evidence source")
        try:
            checked = datetime.fromisoformat(body.verified_at.replace("Z", "+00:00"))
            expiry = datetime.fromisoformat(body.expires_at.replace("Z", "+00:00"))
            if checked.tzinfo is None or expiry.tzinfo is None or not checked <= datetime.now(timezone.utc) < expiry:
                raise ValueError()
        except ValueError:
            raise HTTPException(422, "Use a current timezone-aware source check and future expiry")
        db.execute("INSERT OR REPLACE INTO advertiser_review(observation_id,advertiser_id,relationship,source_url,reviewer,verified_at,expires_at) VALUES (?,?,?,?,?,?,?)", (body.observation_id, body.advertiser_id, body.relationship, body.source_url, body.reviewer, checked.astimezone(timezone.utc).isoformat(), expiry.astimezone(timezone.utc).isoformat()))
        db.log("advertiser_review", body.model_dump())
        return {"rescore": pipeline.rebuild()}

    @app.post("/api/admin/suggestions/{sid}/review", dependencies=[Depends(admin)])
    def review_suggestion(sid: str, body: Review):
        if not db.one("SELECT id FROM suggestion WHERE id=?", (sid,)):
            raise HTTPException(404, "Suggestion not found")
        db.execute("UPDATE suggestion SET status=? WHERE id=?", (body.decision, sid))
        db.log("suggestion_review", {"id": sid, **body.model_dump()})
        return {"status": body.decision, "note": "Reviewing a suggestion does not verify a registry record; use the registry editor after source checks"}

    @app.post("/api/admin/queries/{qid}/review", dependencies=[Depends(admin)])
    def review_query(qid: str, body: Review):
        if not db.one("SELECT id FROM query WHERE id=?", (qid,)):
            raise HTTPException(404, "Query not found")
        db.execute("UPDATE query SET active=? WHERE id=?", (int(body.decision == "approved"), qid))
        db.log("query_review", {"id": qid, **body.model_dump()})
        return {"active": body.decision == "approved"}

    @app.post("/api/admin/disputes/{did}/review", dependencies=[Depends(admin)])
    def review_dispute(did: str, body: Review):
        row = db.one("SELECT * FROM dispute WHERE id=?", (did,))
        if not row:
            raise HTTPException(404, "Dispute not found")
        with db.connect() as c:
            c.execute("UPDATE dispute SET status=? WHERE id=?", (body.decision, did))
            # Rejecting a dispute restores only if no other pending/accepted dispute applies.
            other = c.execute("SELECT 1 FROM dispute WHERE target_id=? AND status IN ('pending','approved') LIMIT 1", (row["target_id"],)).fetchone()
            c.execute("UPDATE observation SET hidden=? WHERE id=?", (int(bool(other)), row["target_id"]))
        db.log("dispute_review", {"id": did, **body.model_dump()})
        return {"id": did, "status": body.decision}

    @app.post("/api/admin/collect", dependencies=[Depends(admin)])
    def collect(body: Collect):
        try:
            return collector.collect(body.query_id, body.state, body.engine)
        except BudgetExceeded as exc:
            raise HTTPException(429, str(exc))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(503, str(exc))

    @app.post("/api/admin/rescore", dependencies=[Depends(admin)])
    def rescore():
        return pipeline.rebuild()

    @app.post("/api/admin/evaluation/labels", dependencies=[Depends(admin)])
    def label(body: Label):
        row = db.one("SELECT o.id,r.hl,r.demo FROM observation o JOIN run r ON r.id=o.run_id WHERE o.id=?", (body.observation_id,))
        if not row or not host(body.source_url):
            raise HTTPException(422, "Use an existing observation and a valid official evidence URL")
        db.execute("INSERT OR REPLACE INTO evaluation_label VALUES (?,?,?,?,?,?)", (row["id"], body.verdict, row["hl"], body.source_url, body.reviewer, row["demo"]))
        return {"status": "saved"}

    @app.get("/api/admin/raw/{rid}", dependencies=[Depends(admin)])
    def raw(rid: str):
        row = db.one("SELECT raw_ref FROM run WHERE id=?", (rid,))
        if not row:
            raise HTTPException(404, "Run not found")
        return FileResponse(settings.data_dir / row["raw_ref"], media_type="application/gzip", filename=f"{rid}.json.gz")

    app.mount("/assets", StaticFiles(directory=STATIC), name="assets")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app


app = create_app()
