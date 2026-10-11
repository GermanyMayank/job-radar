"""Company careers pages via their public ATS job feeds (Personio, Greenhouse, Lever,
Recruitee, SmartRecruiters). For each company in config we probe the candidate slugs on each
ATS and use the first that answers; the log shows which companies resolved.
Companies on Workday/SAP/own systems won't resolve here; their jobs still reach us via
Bundesagentur, Adzuna, Jooble and the email alerts."""
import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import date

from radar.models import UA, Job, clean_text, get_json

FOREIGN = ("spain", "españa", "france", "italy", "italia", "netherlands", "nederland", "united kingdom",
           " uk", "poland", "polska", "austria", "österreich", "switzerland", "schweiz", "portugal",
           "sweden", "usa", "united states", "denmark", "belgium", "greece", "romania", "india")


def _german(loc):
    low = f" {(loc or '').lower()}"
    return not any(f in low for f in FOREIGN) or "germany" in low or "deutschland" in low


def _personio(session, slug):
    for tld in ("de", "com"):
        try:
            r = session.get(f"https://{slug}.jobs.personio.{tld}/xml", timeout=20, headers={"User-Agent": UA})
        except Exception:
            continue
        if r.status_code != 200 or b"<position" not in r.content:
            continue
        root, jobs = ET.fromstring(r.content), []
        for p in root.iter("position"):
            pid = p.findtext("id", "")
            desc = " ".join((d.findtext("value") or "") for d in p.iter("jobDescription"))
            jobs.append(dict(id=pid, title=p.findtext("name", ""), location=p.findtext("office", ""),
                             url=f"https://{slug}.jobs.personio.{tld}/job/{pid}",
                             posted=(p.findtext("createdAt") or "")[:10], description=desc))
        return jobs
    return None


def _greenhouse(session, slug):
    d = get_json(session, f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", params={"content": "true"}, retries=1, quiet=True)
    if not d or "jobs" not in d:
        return None
    return [dict(id=str(j.get("id")), title=j.get("title", ""), location=(j.get("location") or {}).get("name", ""),
                 url=j.get("absolute_url", ""), posted=(j.get("updated_at") or "")[:10],
                 description=j.get("content", "")) for j in d["jobs"]]


def _lever(session, slug):
    d = get_json(session, f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"}, retries=1, quiet=True)
    if not isinstance(d, list) or not d:
        return None
    from datetime import datetime, timezone
    return [dict(id=j.get("id", ""), title=j.get("text", ""), location=(j.get("categories") or {}).get("location", ""),
                 url=j.get("hostedUrl", ""),
                 posted=datetime.fromtimestamp(j["createdAt"] / 1000, timezone.utc).date().isoformat() if j.get("createdAt") else "",
                 description=j.get("descriptionPlain", "")) for j in d]


def _recruitee(session, slug):
    d = get_json(session, f"https://{slug}.recruitee.com/api/offers/", retries=1, quiet=True)
    if not d or not d.get("offers"):
        return None
    return [dict(id=str(j.get("id")), title=j.get("title", ""), location=j.get("location", ""),
                 url=j.get("careers_url", ""), posted=(j.get("published_at") or "")[:10],
                 description=j.get("description", "")) for j in d["offers"]]


def _smartrecruiters(session, slug):
    d = get_json(session, f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", params={"limit": 100}, retries=1, quiet=True)
    if not d or not d.get("content"):
        return None
    return [dict(id=j.get("id", ""), title=j.get("name", ""),
                 location=", ".join(x for x in ((j.get("location") or {}).get("city"), (j.get("location") or {}).get("country")) if x),
                 url=f"https://jobs.smartrecruiters.com/{slug}/{j.get('id', '')}",
                 posted=(j.get("releasedDate") or "")[:10], description="") for j in d["content"]]


ATS = {"personio": _personio, "greenhouse": _greenhouse, "lever": _lever,
       "recruitee": _recruitee, "smartrecruiters": _smartrecruiters}


CACHE = os.path.join("data", "ats_cache.json")   # remembers which ATS/slug each company uses
REPROBE_DAYS = 7                                 # companies not found are re-checked weekly


def collect(session, cfg):
    jobs, resolved, missing = [], [], []
    try:
        cache = json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        cache = {}
    today = date.today()
    for company, slugs in cfg["sources"]["watchlist"]["companies"].items():
        found, hit = None, cache.get(company)
        if hit and hit.get("ats"):
            try:
                res = ATS[hit["ats"]](session, hit["slug"])
            except Exception:
                res = None
            if res is not None:
                found = (hit["ats"], hit["slug"], res)
        elif hit and (today - date.fromisoformat(hit["checked"])).days < REPROBE_DAYS:
            missing.append(company)
            continue
        for slug in ([] if found else slugs):
            for name, fn in ATS.items():
                try:
                    res = fn(session, slug)
                except Exception:
                    res = None
                if res is not None:
                    found = (name, slug, res)
                    break
                time.sleep(0.2)
            if found:
                break
        if not found:
            cache[company] = {"ats": None, "checked": today.isoformat()}
            missing.append(company)
            continue
        ats, slug, rows = found
        cache[company] = {"ats": ats, "slug": slug, "checked": today.isoformat()}
        de = [r for r in rows if _german(r["location"])]
        resolved.append(f"{company} ({ats}:{slug}, {len(de)} DE)")
        for r in de:
            jobs.append(Job(source="watchlist", source_id=f"{ats}:{r['id']}", title=r["title"], company=company,
                            location=r["location"], url=r["url"], posted=r["posted"],
                            description=clean_text(r["description"])))
    os.makedirs("data", exist_ok=True)
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), indent=1, sort_keys=True)
    print(f"  watchlist: {len(jobs)} raw from {len(resolved)} companies")
    print("    resolved: " + ("; ".join(resolved) or "none"))
    print("    not on a public ATS feed: " + (", ".join(missing) or "none"))
    return jobs
