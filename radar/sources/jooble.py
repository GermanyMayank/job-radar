"""Jooble API (aggregator, pulls from many German boards). Free key: https://jooble.org/api/about
Needs JOOBLE_API_KEY. Keys are issued per country site; set JOOBLE_HOST if yours is not de.jooble.org."""
import os
import time

import requests

from radar.models import UA, Job


def collect(session, cfg):
    key = (os.getenv("JOOBLE_API_KEY") or "").strip()
    if not key:
        print("  jooble: skipped (no JOOBLE_API_KEY)")
        return []
    sc = cfg["sources"].get("jooble", {})
    hosts = [os.getenv("JOOBLE_HOST", "de.jooble.org"), "jooble.org"]
    host, jobs = None, []
    for q in cfg["queries"]:
        for page in range(1, sc.get("pages_per_query", 1) + 1):
            body = {"keywords": q, "location": "Deutschland", "page": str(page)}
            data = None
            for h in ([host] if host else hosts):
                try:
                    r = session.post(f"https://{h}/api/{key}", json=body, timeout=30,
                                     headers={"User-Agent": UA, "Content-Type": "application/json"})
                except requests.RequestException as e:
                    print(f"  ! jooble {h}: {e}")
                    continue
                if r.status_code == 200:
                    host, data = h, r.json()
                    break
                print(f"  ! jooble {h} -> HTTP {r.status_code}")
            items = (data or {}).get("jobs") or []
            for s in items:
                jobs.append(Job(
                    source="jooble", source_id=str(s.get("id", "")), title=s.get("title", ""),
                    company=s.get("company", ""), location=s.get("location", ""),
                    url=s.get("link", ""), posted=(s.get("updated") or "")[:10],
                    description=s.get("snippet", ""),
                ))
            if len(items) < 20:
                break
            time.sleep(1.0)
        if host is None:      # key rejected on every host: stop early, don't burn quota
            break
    print(f"  jooble: {len(jobs)} raw")
    return jobs
