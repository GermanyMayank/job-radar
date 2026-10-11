"""Writes three files:
  data/jobs.csv     every job that passed the gates in today's run, ranked
  data/tracker.csv  persistent list across runs; edit the status/notes columns by hand
  SHORTLIST.md      top jobs not yet decided, readable on GitHub/phone"""
import csv
import os
from datetime import date

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


SOURCE_NAMES = {"bundesagentur": "Bundesagentur", "adzuna": "Adzuna", "jooble": "Jooble",
                "arbeitnow": "Arbeitnow", "watchlist": "Company sites", "linkedin": "LinkedIn"}


def _table(jobs, new_keys, start=1):
    esc = lambda s: (s or "").replace("|", "/").strip()
    rows = ["| # | Score | Role | Company | Location | Posted | Why it fits | Watch out | Link |",
            "|--:|--:|---|---|---|---|---|---|---|"]
    for i, j in enumerate(jobs, start):
        link = f"[open]({j.url})" + (f" · [apply]({j.apply_url})" if j.apply_url else "")
        new = " 🆕" if j.key in new_keys else ""
        rows.append(f"| {i} | **{j.score}** | {esc(j.title)}{new} | {esc(j.company) or '(not given)'} | "
                    f"{esc(j.location)} | {j.posted or '?'} | {esc(', '.join(j.reasons))} | "
                    f"{esc(', '.join(j.flags))} | {link} |")
    return rows


def write_shortlist(jobs, tracker_rows, path, size, run_stats):
    today = date.today().isoformat()
    open_jobs = [j for j in jobs if tracker_rows.get(j.key, {}).get("status", "new") in ("new", "apply")][:size]
    new_keys = {k for k, r in tracker_rows.items() if r.get("first_seen") == today}
    strong = [j for j in open_jobs if j.bucket == "Strong"]
    review = [j for j in open_jobs if j.bucket != "Strong"]
    counts = run_stats.get("by_source", {})
    status = {}
    for r in tracker_rows.values():
        status[r.get("status", "new")] = status.get(r.get("status", "new"), 0) + 1

    lines = [f"# ☀️ Job Radar · {today}", "",
             f"**{len(strong)} strong matches** and {len(review)} to review, out of {run_stats['kept']} relevant "
             f"jobs ({len([j for j in open_jobs if j.key in new_keys])} new today, 🆕). "
             f"Scanned {run_stats['raw']:,} postings.", ""]
    if counts:
        lines.append("Relevant jobs by source: " + " · ".join(
            f"{SOURCE_NAMES.get(k, k.title())} {v}" for k, v in sorted(counts.items(), key=lambda x: -x[1])) + "")
        lines.append("")
    tracked = " · ".join(f"{k} {v}" for k, v in sorted(status.items()) if k not in ("new",))
    if tracked:
        lines += [f"Tracker: {tracked}", ""]

    lines += ["## Strong matches", ""]
    lines += _table(strong, new_keys) if strong else ["_None today._"]
    lines += ["", "## Worth a look", ""]
    lines += _table(review, new_keys, start=len(strong) + 1) if review else ["_None today._"]
    lines += ["", "---", "",
              "**How to use:** open a job, and if it's interesting paste it into the Claude project for a fit "
              "check and a tailored CV + cover letter. Then set its `status` in "
              "[`data/tracker.csv`](data/tracker.csv) (`apply`, `applied`, `interview`, `offer`, `rejected`, "
              "`skip`). Decided jobs leave this list.", "",
              "Scores are a sorting aid, not a verdict. See the README for how they're calculated."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
