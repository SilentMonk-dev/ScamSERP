import argparse
import os
import json
import time
from pathlib import Path

from .collector import Collector
from .config import Settings
from .db import Database
from .pipeline import Pipeline
from .reports import write_digest
from .seed import seed_demo, seed_registry
from .service import Service


def main():
    from dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser(description="ScamSERP audit operations")
    parser.add_argument("command", choices=["serve", "init", "collect", "schedule-once", "scheduler", "coverage", "rescore", "digest"])
    parser.add_argument("--query", default="sbi-en-1")
    parser.add_argument("--state", default="Delhi")
    parser.add_argument("--engine", choices=["google", "google_autocomplete", "google_local"], default="google")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    settings = Settings()
    if args.command == "serve":
        import uvicorn
        # Number/domain inputs never appear in access logs.
        uvicorn.run("scamserp.app:app", host=args.host, port=args.port, access_log=False)
        return
    db = Database(settings)
    pipeline = Pipeline(db)
    seed_registry(db)
    seed_demo(db, pipeline)
    service = Service(db)
    collector = Collector(db, pipeline)
    if args.command == "init":
        print(f"Initialized {settings.mode} database at {settings.db_path}")
    elif args.command == "collect":
        print(collector.collect(args.query, args.state, args.engine))
    elif args.command == "rescore":
        print(pipeline.rebuild())
    elif args.command == "digest":
        write_digest(service)
        print(f"Digest saved in {settings.data_dir / 'digests'}")
    elif args.command == "coverage":
        from .scheduler import coverage
        print(json.dumps(coverage(db, collector), indent=2))
    elif args.command in {"schedule-once", "scheduler"}:
        if settings.mode != "live" or not settings.api_key:
            parser.error("Scheduler requires live mode and SERPAPI_API_KEY")
        limit = settings.schedule_limit
        if args.command == "schedule-once":
            print(collector.scheduled(limit))
        else:
            from .scheduler import SchedulerRunner
            runner = SchedulerRunner(db, collector, service)
            if not runner.start():
                parser.error("A scheduler already holds the data-directory lock")
            print("Audit scheduler active; weekly digest Monday 08:00 Asia/Kolkata")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            finally:
                runner.stop()


if __name__ == "__main__":
    main()
