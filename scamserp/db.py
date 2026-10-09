import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS entity(id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, aliases TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS registry(id INTEGER PRIMARY KEY, entity_id TEXT NOT NULL REFERENCES entity(id), kind TEXT NOT NULL CHECK(kind IN ('domain','phone','social','email','intermediary')), value TEXT NOT NULL, display TEXT NOT NULL, source_url TEXT NOT NULL, verifier TEXT NOT NULL, verified_at TEXT, expires_at TEXT, status TEXT NOT NULL CHECK(status IN ('pending','verified','rejected')), UNIQUE(entity_id,kind,value));
CREATE TABLE IF NOT EXISTS registry_history(id INTEGER PRIMARY KEY, record_id INTEGER, before_json TEXT, after_json TEXT NOT NULL, changed_at TEXT NOT NULL, actor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS query(id TEXT PRIMARY KEY, entity_id TEXT REFERENCES entity(id), text TEXT NOT NULL, language TEXT NOT NULL, tier INTEGER NOT NULL CHECK(tier BETWEEN 1 AND 3), active INTEGER NOT NULL DEFAULT 1, local_intent INTEGER NOT NULL DEFAULT 0, origin TEXT NOT NULL DEFAULT 'manual-v1', UNIQUE(entity_id,text,language));
CREATE TABLE IF NOT EXISTS run(id TEXT PRIMARY KEY, query_id TEXT REFERENCES query(id), engine TEXT NOT NULL, state TEXT NOT NULL, location TEXT NOT NULL, hl TEXT NOT NULL, fetched_at TEXT NOT NULL, search_id TEXT, raw_ref TEXT, status TEXT NOT NULL, error TEXT, cache_key TEXT, demo INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_run_filters ON run(state,hl,fetched_at,status);
CREATE INDEX IF NOT EXISTS idx_run_cache ON run(cache_key,fetched_at);
CREATE TABLE IF NOT EXISTS observation(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES run(id), kind TEXT NOT NULL, position INTEGER NOT NULL, title TEXT NOT NULL, snippet TEXT NOT NULL, url TEXT, domain TEXT, entity_id TEXT REFERENCES entity(id), phones_json TEXT NOT NULL, advertiser_id TEXT, facts_json TEXT NOT NULL, hidden INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_obs_domain ON observation(domain);
CREATE TABLE IF NOT EXISTS phone_seen(observation_id TEXT NOT NULL REFERENCES observation(id), phone TEXT NOT NULL, PRIMARY KEY(observation_id,phone));
CREATE INDEX IF NOT EXISTS idx_phone ON phone_seen(phone);
CREATE TABLE IF NOT EXISTS score(id INTEGER PRIMARY KEY, observation_id TEXT NOT NULL REFERENCES observation(id), rule_version TEXT NOT NULL, risk INTEGER NOT NULL, verdict TEXT NOT NULL, signals_json TEXT NOT NULL, scored_at TEXT NOT NULL, revision TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_score_obs ON score(observation_id,id);
CREATE TABLE IF NOT EXISTS advertiser(id TEXT PRIMARY KEY, data_json TEXT NOT NULL, checked_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS advertiser_review(observation_id TEXT PRIMARY KEY REFERENCES observation(id), advertiser_id TEXT NOT NULL, relationship TEXT NOT NULL CHECK(relationship IN ('linked','unlinked','unknown')), source_url TEXT NOT NULL, reviewer TEXT NOT NULL, verified_at TEXT NOT NULL, expires_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'verified');
CREATE TABLE IF NOT EXISTS domain_info(domain TEXT PRIMARY KEY, registered_at TEXT, checked_at TEXT NOT NULL, data_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS campaign(id TEXT PRIMARY KEY, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, size INTEGER NOT NULL, review_state TEXT NOT NULL DEFAULT 'pending', reviewer TEXT, reviewed_at TEXT);
CREATE TABLE IF NOT EXISTS campaign_member(campaign_id TEXT NOT NULL REFERENCES campaign(id), observation_id TEXT NOT NULL REFERENCES observation(id), PRIMARY KEY(campaign_id,observation_id));
CREATE TABLE IF NOT EXISTS dispute(id TEXT PRIMARY KEY, target_id TEXT NOT NULL REFERENCES observation(id), message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS suggestion(id TEXT PRIMARY KEY, entity_id TEXT NOT NULL REFERENCES entity(id), kind TEXT NOT NULL, value TEXT NOT NULL, source_url TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS budget(id INTEGER PRIMARY KEY, spent_at TEXT NOT NULL, engine TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_task(query_id TEXT NOT NULL REFERENCES query(id), state TEXT NOT NULL, engine TEXT NOT NULL, last_attempt TEXT NOT NULL, last_status TEXT NOT NULL, PRIMARY KEY(query_id,state,engine));
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evaluation_label(observation_id TEXT PRIMARY KEY REFERENCES observation(id), verdict TEXT NOT NULL, language TEXT NOT NULL, source_url TEXT NOT NULL, reviewer TEXT NOT NULL, synthetic INTEGER NOT NULL DEFAULT 0);
PRAGMA user_version=1;
"""


class Database:
    def __init__(self, settings):
        self.settings = settings
        self.scoring_lock = threading.RLock()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript(SCHEMA)
            # Additive migrations preserve existing evidence and source history.
            for table, column, definition in [
                ("query", "intent_id", "TEXT"),
                ("campaign", "evidence_hash", "TEXT"),
            ]:
                columns = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
                if column not in columns:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            con.execute("PRAGMA user_version=2")

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.settings.db_path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=30000")
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def rows(self, sql, params=()):
        with self.connect() as con:
            return [dict(r) for r in con.execute(sql, params)]

    def one(self, sql, params=()):
        rows = self.rows(sql, params)
        return rows[0] if rows else None

    def execute(self, sql, params=()):
        with self.connect() as con:
            return con.execute(sql, params).lastrowid

    def log(self, action, detail):
        self.execute("INSERT INTO audit_log(action,detail,created_at) VALUES (?,?,?)", (action, json.dumps(detail, ensure_ascii=False), now()))


# Publication gate is used consistently by lookup, map, exports, reports and watchlist.
PUBLIC_SQL = """
SELECT o.*, s.risk, s.verdict, s.signals_json, s.rule_version, r.state, r.location,
r.hl, r.fetched_at, r.search_id, r.demo, r.query_id, q.text query_text, q.language query_language, q.intent_id, r.engine, e.name entity_name, e.category
FROM observation o JOIN run r ON r.id=o.run_id
LEFT JOIN query q ON q.id=r.query_id LEFT JOIN entity e ON e.id=o.entity_id
JOIN score s ON s.id=(SELECT MAX(s2.id) FROM score s2 WHERE s2.observation_id=o.id)
WHERE o.hidden=0 AND r.status='success'
AND (s.verdict!='Likely Fraud' OR EXISTS (
  SELECT 1 FROM campaign_member m JOIN campaign c ON c.id=m.campaign_id
  WHERE m.observation_id=o.id AND c.review_state='approved'))
"""
