"""Bundesagentur fuer Arbeit Jobsuche API (public client id, no account).
Docs (community): https://github.com/bundesAPI/jobsuche-api
The search endpoint version has moved over time (v4 -> v6), so we try both."""
import base64
import time

from radar.models import Job, get_json

BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
HEAD = {"X-API-Key": "jobboerse-jobsuche"}
SEARCH_VERSIONS = ("v6", "v4")


def _search_page(session, query, page, size, days):
    params = {"was": query, "angebotsart": 1, "page": page, "size": size,
              "veroeffentlichtseit": days, "pav": "false"}
    for v in SEARCH_VERSIONS:
        data = get_json(session, f"{BASE}/pc/{v}/jobs", params=params, headers=HEAD)
        if data is not None:
            return data
    return None


def collect(session, cfg):
    sc = cfg["sources"]["bundesagentur"]
    jobs = []
    for q in cfg["queries"]:
        for page in range(1, sc.get("pages_per_query", 1) + 1):
            data = _search_page(session, q, page, sc.get("page_size", 50), cfg["lookback_days"])
            items = (data or {}).get("stellenangebote") or []
            for s in items:
                ort = s.get("arbeitsort") or {}
                refnr = s.get("refnr", "")
                jobs.append(Job(
                    source="bundesagentur",
                    source_id=refnr,
                    title=s.get("titel") or s.get("beruf") or "",
                    company=s.get("arbeitgeber", ""),
                    location=", ".join(x for x in (ort.get("ort"), ort.get("region")) if x),
                    url=f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}",
                    apply_url=s.get("externeUrl", ""),
                    posted=(s.get("aktuelleVeroeffentlichungsdatum") or "")[:10],
                ))
            if len(items) < sc.get("page_size", 50):
                break
            time.sleep(0.5)
    print(f"  bundesagentur: {len(jobs)} raw")
    return jobs


def enrich(session, job):
    """Fetch the full description for one job (only called for jobs that pass the title gate)."""
    code = base64.b64encode(job.source_id.encode()).decode()
    data = get_json(session, f"{BASE}/pc/v4/jobdetails/{code}", headers=HEAD)
    if not data:
        return job
    from radar.models import clean_text
    job.description = clean_text(data.get("stellenangebotsBeschreibung")
                                 or data.get("stellenbeschreibung") or "")
    job.apply_url = job.apply_url or data.get("externeUrl") or data.get("allianzpartnerUrl") or ""
    time.sleep(0.3)
    return job
