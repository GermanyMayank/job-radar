"""Adzuna API, Germany endpoint. Free developer key: https://developer.adzuna.com
Descriptions are snippets, so scoring leans more on the title for these."""
import os
import time

from radar.models import Job, get_json

URL = "https://api.adzuna.com/v1/api/jobs/de/search/{page}"


def collect(session, cfg):
    app_id, app_key = os.getenv("ADZUNA_APP_ID"), os.getenv("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        print("  adzuna: skipped (no ADZUNA_APP_ID / ADZUNA_APP_KEY)")
        return []
    jobs = []
    for q in cfg["queries"]:
        for page in range(1, cfg["sources"]["adzuna"].get("pages_per_query", 1) + 1):
            data = get_json(session, URL.format(page=page), params={
                "app_id": app_id, "app_key": app_key, "what": q,
                "results_per_page": 50, "max_days_old": cfg["lookback_days"],
            })
            items = (data or {}).get("results") or []
            for s in items:
                jobs.append(Job(
                    source="adzuna", source_id=str(s.get("id", "")),
                    title=s.get("title", ""),
                    company=(s.get("company") or {}).get("display_name", ""),
                    location=(s.get("location") or {}).get("display_name", ""),
                    url=s.get("redirect_url", ""), posted=(s.get("created") or "")[:10],
                    description=s.get("description", ""),
                ))
            if len(items) < 50:
                break
            time.sleep(1.0)   # free tier is rate limited
    print(f"  adzuna: {len(jobs)} raw")
    return jobs
