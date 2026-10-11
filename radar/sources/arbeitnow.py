"""Arbeitnow free job board API (Germany focused, many English postings). No key."""
import time
from datetime import datetime, timezone

from radar.models import Job, get_json

URL = "https://www.arbeitnow.com/api/job-board-api"


def collect(session, cfg):
    jobs = []
    for page in range(1, cfg["sources"]["arbeitnow"].get("pages", 5) + 1):
        data = get_json(session, URL, params={"page": page})
        items = (data or {}).get("data") or []
        for s in items:
            ts = s.get("created_at")
            posted = datetime.fromtimestamp(ts, timezone.utc).date().isoformat() if ts else ""
            jobs.append(Job(
                source="arbeitnow", source_id=s.get("slug", ""),
                title=s.get("title", ""), company=s.get("company_name", ""),
                location=s.get("location", "") + (" (remote)" if s.get("remote") else ""),
                url=s.get("url", ""), posted=posted, description=s.get("description", ""),
            ))
        if not items or not (data or {}).get("links", {}).get("next"):
            break
        time.sleep(0.5)
    print(f"  arbeitnow: {len(jobs)} raw")
    return jobs
