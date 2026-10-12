"""Job Radar: collect -> gate -> enrich -> dedupe -> score -> write.
Run locally:  python run.py          (sources without credentials are skipped)
Offline test: python run.py --fixtures tests/fixtures"""
import argparse
import json
import os
import sys
from datetime import date, timedelta

import requests
import yaml

from radar import output, site
from radar.models import Job
from radar.score import dedupe, domain_gate, score, title_gate
from radar.sources import adzuna, arbeitnow, bundesagentur, email_alerts, jooble, watchlist

SOURCES = {"bundesagentur": bundesagentur, "arbeitnow": arbeitnow, "adzuna": adzuna,
           "jooble": jooble, "email_alerts": email_alerts, "watchlist": watchlist}


def load_fixtures(folder):
    jobs = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".json"):
            jobs += [Job(**j) for j in json.load(open(os.path.join(folder, name), encoding="utf-8"))]
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--out", default=".")
    ap.add_argument("--fixtures", help="folder of normalized job JSON for offline testing")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    session = requests.Session()

    print("Collecting...")
    if args.fixtures:
        raw = load_fixtures(args.fixtures)
    else:
        raw = []
        for name, mod in SOURCES.items():
            if not cfg["sources"].get(name, {}).get("enabled"):
                continue
            try:
                raw += mod.collect(session, cfg)
            except Exception as e:   # one broken source must not kill the run
                print(f"  ! {name} failed: {e}", file=sys.stderr)

    cutoff = (date.today() - timedelta(days=cfg["lookback_days"])).isoformat()
    jobs = [j for j in raw if title_gate(j, cfg) and (not j.posted or j.posted >= cutoff)]
    print(f"Title gate: {len(raw)} -> {len(jobs)}")

    if not args.fixtures:
        for j in jobs:
            if j.source == "bundesagentur" and not j.description:
                try:
                    bundesagentur.enrich(session, j)
                except Exception as e:
                    print(f"  ! enrich {j.source_id}: {e}", file=sys.stderr)

    jobs = [j for j in jobs if domain_gate(j, cfg)]
    jobs = dedupe(jobs)
    jobs = sorted((score(j, cfg) for j in jobs), key=lambda j: -j.score)
    print(f"Domain gate + dedupe: {len(jobs)} jobs")

    by_source = {}
    for j in jobs:
        for src in j.sources:
            by_source[src] = by_source.get(src, 0) + 1
    output.write_jobs(jobs, os.path.join(args.out, "data", "jobs.csv"))
    rows = output.update_tracker(jobs, os.path.join(args.out, "data", "tracker.csv"))
    output.write_shortlist(jobs, rows, os.path.join(args.out, "SHORTLIST.md"),
                           cfg["shortlist_size"], {"raw": len(raw), "kept": len(jobs), "by_source": by_source})
    site.write_site(jobs, rows, os.path.join(args.out, "docs"), {"raw": len(raw)})
    print("Wrote data/jobs.csv, data/tracker.csv, SHORTLIST.md, docs/index.html")


if __name__ == "__main__":
    main()
