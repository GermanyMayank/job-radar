"""Offline tests: python -m pytest tests  (or python tests/test_radar.py)"""
import csv, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from radar.sources.linkedin_email import parse_alert

ALERT = """Your job alert for project coordinator solar
New jobs match your preferences.

Junior Project Coordinator PV
Helio Parks GmbH
Berlin, Germany
View job: https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=abc

---------------------------------------------------------
Projektkoordinator Photovoltaik (m/w/d)
SonnenBau GmbH
Nuremberg, Bavaria, Germany
Actively recruiting
View job: https://www.linkedin.com/comm/jobs/view/4087654321/?trk=x

---------------------------------------------------------
See all jobs: https://www.linkedin.com/comm/jobs/search
"""

def test_linkedin_parser():
    jobs = parse_alert(ALERT, "")
    assert [j.source_id for j in jobs] == ["4012345678", "4087654321"]
    assert jobs[0].title == "Junior Project Coordinator PV" and jobs[0].company == "Helio Parks GmbH"
    assert jobs[1].location.startswith("Nuremberg") and jobs[1].company == "SonnenBau GmbH"

def test_status_survives_rerun():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = tempfile.mkdtemp()
    run = lambda: subprocess.run([sys.executable, "run.py", "--fixtures", "tests/fixtures", "--out", out],
                                 cwd=root, check=True, capture_output=True)
    run()
    path = os.path.join(out, "data", "tracker.csv")
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    rows[0]["status"], rows[0]["notes"] = "applied", "sent 11 Oct"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    run()
    again = {r["key"]: r for r in csv.DictReader(open(path, encoding="utf-8"))}
    assert again[rows[0]["key"]]["status"] == "applied"
    assert again[rows[0]["key"]]["notes"] == "sent 11 Oct"
    shortlist = open(os.path.join(out, "SHORTLIST.md"), encoding="utf-8").read()
    assert rows[0]["title"] not in shortlist     # decided jobs leave the shortlist

def test_dedupe_and_sales_penalty():
    out = tempfile.mkdtemp()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    subprocess.run([sys.executable, "run.py", "--fixtures", "tests/fixtures", "--out", out], cwd=root, check=True, capture_output=True)
    rows = list(csv.DictReader(open(os.path.join(out, "data", "jobs.csv"), encoding="utf-8")))
    sonnen = [r for r in rows if r["company"].startswith("SonnenBau")]
    assert len(sonnen) == 1 and "adzuna" in sonnen[0]["sources"] and "bundesagentur" in sonnen[0]["sources"]
    sales = [r for r in rows if "Vertrieb" in r["title"]][0]
    assert sales["bucket"] == "Low"

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)
