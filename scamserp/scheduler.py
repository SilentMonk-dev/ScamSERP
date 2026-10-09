"""One scheduler owner per data directory, usable inside the web app or separately."""
import json
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from filelock import FileLock, Timeout

from .db import now
from .reports import write_digest


class SchedulerRunner:
    def __init__(self, db, collector, service):
        self.db, self.collector, self.service = db, collector, service
        self.lock = FileLock(db.settings.data_dir / "scheduler.lock")
        self.scheduler = None

    def start(self):
        if self.db.settings.mode != "live" or not self.db.settings.api_key:
            raise ValueError("Scheduled collection requires live mode and a SerpApi key")
        try:
            self.lock.acquire(timeout=0)
        except Timeout:
            return False
        try:
            self.scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
            self.scheduler.add_job(self.tick, "interval", hours=self.db.settings.schedule_hours, next_run_time=datetime.now(timezone.utc), max_instances=1, coalesce=True)
            self.scheduler.add_job(lambda: write_digest(self.service), "cron", day_of_week="mon", hour=8, minute=0, max_instances=1)
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('scheduler_state',?)", (json.dumps({"state": "running", "started_at": now(), "interval_hours": self.db.settings.schedule_hours}),))
            self.scheduler.start()
            return True
        except BaseException:
            self.lock.release()
            raise

    def tick(self):
        try:
            self.collector.scheduled(self.db.settings.schedule_limit)
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('scheduler_last_error','')")
        except Exception:
            # Do not persist exception strings that could contain credential URLs.
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('scheduler_last_error','Collection tick failed; inspect local operational logs')")
            self.db.log("scheduler_error", {"reason": "Collection tick failed"})

    def stop(self):
        if self.scheduler:
            self.scheduler.shutdown(wait=True)
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('scheduler_state',?)", (json.dumps({"state": "stopped", "stopped_at": now()}),))
            self.lock.release()
            self.scheduler = None


def coverage(db, collector):
    plan = collector.schedule_plan()
    values = {r["key"]: r["value"] for r in db.rows("SELECT * FROM meta WHERE key LIKE 'scheduler_%'")}
    state = json.loads(values.get("scheduler_state") or '{}')
    tick = values.get("scheduler_last_tick")
    recent = bool(tick and datetime.fromisoformat(tick) >= datetime.now(timezone.utc) - timedelta(hours=db.settings.schedule_hours * 2))
    baseline_month = sum(30 / t["days"] for t in plan)
    return {"scheduler": {**state, "last_tick": tick, "recent_heartbeat": recent, "last_error": values.get("scheduler_last_error") or None}, "active_queries": db.one("SELECT COUNT(*) n FROM query WHERE active=1")["n"], "planned_cells": len(plan), "measured_cells": sum(t["latest"] is not None for t in plan), "due_cells": sum(t["due"] for t in plan), "minimum_monthly_requests_for_full_cadence": round(baseline_month), "configured_monthly_cap": db.settings.monthly_cap, "configured_daily_cap": db.settings.daily_cap, "full_cadence_budget_sufficient": db.settings.monthly_cap >= baseline_month and db.settings.daily_cap >= baseline_month / 30, "engines": db.rows("SELECT engine,status,COUNT(*) runs,MAX(fetched_at) latest FROM run GROUP BY engine,status"), "note": "Budget estimate excludes retries, Ads Transparency enrichment and public searches. Autocomplete is sampled nationally; Search and Local use six city proxies. Collection rotates under existing caps; full coverage is not guaranteed."}
