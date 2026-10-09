import html
from pathlib import Path

from .db import now


def digest_content(service, format="markdown"):
    summary = service.map(window=7)
    score = summary["summary"]["exposure"]
    campaigns = service.campaigns()
    title = "ScamSERP weekly search audit"
    lines = [f"# {title}", "", f"Generated: {now()}", "", "SYNTHETIC DEMO — not an empirical report." if summary["demo"] else "Collected fixed-location search observations; not population prevalence.", "", f"Eligible query runs: {summary['summary']['n_runs']}", f"Published ranked observations: {summary['summary']['n']}", f"Position-weighted exposure: {str(score) + '%' if score is not None else 'Insufficient data'}", "", "## Highest exposure locations", ""]
    for state in sorted(summary["states"], key=lambda r: r["exposure"] or 0, reverse=True):
        if state["exposure"] is not None:
            lines.append(f"- {state['state']}: {state['exposure']}% ({state['n_runs']} runs; {state['n']} observations)")
    lines += ["", "## Published campaign clusters", ""]
    lines += [f"- {c['id']}: {c['size']} observations; last seen {c['last_seen'][:10]}" for c in campaigns[:10]] or ["No reviewed campaign clusters."]
    queries = service.db.rows("SELECT q.id,q.text FROM query q WHERE EXISTS(SELECT 1 FROM run r WHERE r.query_id=q.id AND r.engine='google' AND r.fetched_at>=?) LIMIT 100", (now()[:10],))
    # Exact seven-day grouping uses the same publication gate as the map.
    runs, _ = service.runs(window=7)
    grouped = {}
    for r in runs:
        grouped.setdefault(r["query_id"], []).append(r)
    ranked = sorted(((qid, sum(r["exposure"] for r in rs) / len(rs), len(rs)) for qid, rs in grouped.items()), key=lambda x: x[1], reverse=True)
    lines += ["", "## Highest exposure queries", ""]
    for qid, exposure, n in ranked[:10]:
        q = service.db.one("SELECT text FROM query WHERE id=?", (qid,))
        if q:
            lines.append(f"- {q['text']}: {exposure * 100:.1f}% ({n} runs)")
    lines += ["", "## Limitations", "", summary["coverage_note"], "Confidence intervals are exploratory query-cluster estimates. Failed, empty and withheld runs are not treated as clean.", "Do not share OTPs or PINs. For financial cybercrime, call 1930 and use https://cybercrime.gov.in/. For suspicious calls or messages, use Chakshu at https://sancharsaathi.gov.in/sfc/.", "", "Not an official government service. Not legal or financial advice."]
    text = "\n".join(lines)
    if format == "html":
        return "<!doctype html><html lang='en'><meta charset='utf-8'><title>ScamSERP weekly digest</title><body><main><h1>ScamSERP weekly digest</h1><pre style='white-space:pre-wrap;font:16px/1.6 system-ui;max-width:800px'>" + html.escape(text) + "</pre></main></body></html>"
    return text


def write_digest(service):
    directory = service.db.settings.data_dir / "digests"
    directory.mkdir(exist_ok=True)
    for format, extension in [("markdown", "md"), ("html", "html")]:
        (directory / f"digest-{now()[:10]}.{extension}").write_text(digest_content(service, format), encoding="utf-8")
