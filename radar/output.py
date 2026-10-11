"""Writes three files:
  data/jobs.csv     every job that passed the gates in today's run, ranked
  data/tracker.csv  persistent list across runs; edit the status/notes columns by hand
  SHORTLIST.md      top jobs not yet decided, readable on GitHub/phone"""
import csv
import os
from datetime import date

STATUSES = "new | apply | applied | interview | offer | rejected | skip | expired"
JOB_COLS = ["score", "bucket", "title", "company", "location", "posted", "sources",
            "reasons", "flags", "url", "apply_url", "key"]
TRACK_COLS = ["key", "status", "notes", "score", "bucket", "title", "company", "location",
              "posted", "first_seen", "last_seen", "sources", "url", "apply_url"]


def _row(j):
    return {"score": j.score, "bucket": j.bucket, "title": j.title, "company": j.company,
            "location": j.location, "posted": j.posted, "sources": "+".join(j.sources),
            "reasons": "; ".join(j.reasons), "flags": "; ".join(j.flags), "url": j.url,
            "apply_url": j.apply_url, "key": j.key}


def write_jobs(jobs, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=JOB_COLS)
        w.writeheader()
        for j in jobs:
            w.writerow(_row(j))


def update_tracker(jobs, path, today=None, expire_after_days=30):
    today = (today or date.today()).isoformat()
    rows = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            rows = {r["key"]: r for r in csv.DictReader(f)}
    for j in jobs:
        r = rows.get(j.key)
        if r is None:
            r = {"key": j.key, "status": "new", "notes": "", "first_seen": today}
            rows[j.key] = r
        r.update({"score": j.score, "bucket": j.bucket, "title": j.title, "company": j.company,
                  "location": j.location, "posted": j.posted, "last_seen": today,
                  "sources": "+".join(j.sources), "url": j.url,
                  "apply_url": j.apply_url or r.get("apply_url", "")})
    for r in rows.values():   # stale undecided jobs drop off the shortlist
        if r["status"] == "new" and r.get("last_seen") and \
                (date.fromisoformat(today) - date.fromisoformat(r["last_seen"])).days > expire_after_days:
            r["status"] = "expired"
    ordered = sorted(rows.values(), key=lambda r: (-int(r.get("score") or 0), r["key"]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRACK_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(ordered)
    return rows


def write_shortlist(jobs, tracker_rows, path, size, run_stats):
    open_status = {"new", "apply"}
    pick = [j for j in jobs if tracker_rows.get(j.key, {}).get("status", "new") in open_status][:size]
    new_today = {k for k, r in tracker_rows.items() if r.get("first_seen") == date.today().isoformat()}
    esc = lambda s: (s or "").replace("|", "/")
    lines = [f"# Job Radar shortlist ({date.today().isoformat()})", "",
             f"Collected {run_stats['raw']} postings, {run_stats['kept']} passed filters, "
             f"{len(new_today)} new today. Status values for data/tracker.csv: `{STATUSES}`.", "",
             "| # | Score | Role | Company | Location | Posted | Why | Watch out | Links |",
             "|---|---|---|---|---|---|---|---|---|"]
    for i, j in enumerate(pick, 1):
        links = f"[posting]({j.url})" + (f" / [apply]({j.apply_url})" if j.apply_url else "")
        star = " 🆕" if j.key in new_today else ""
        lines.append(f"| {i} | **{j.score}** {j.bucket} | {esc(j.title)}{star} | {esc(j.company)} | "
                     f"{esc(j.location)} | {j.posted} | {esc('; '.join(j.reasons))} | "
                     f"{esc('; '.join(j.flags))} | {links} |")
    if not pick:
        lines.append("| | | No open matches today | | | | | | |")
    lines += ["", "Next step: paste the top picks into the Claude project for a "
              "requirement-to-evidence check and tailored CV + cover letter."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
