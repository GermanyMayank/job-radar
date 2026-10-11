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


# ---- added with multi-board email alerts, Jooble and watchlist ----
import json as _json
import yaml as _yaml
from radar.sources.email_alerts import parse_generic
from radar.sources import watchlist as _wl
from radar.models import Job as _Job
from radar.score import dedupe as _dedupe

_CFG = _yaml.safe_load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml"), encoding="utf-8"))

def test_generic_email_html():
    html = ('<a href="https://www.stepstone.de/job/1">Projektkoordinator Photovoltaik (m/w/d)</a>'
            '<a href="https://www.stepstone.de/job/2">Junior Projektmanager Solar</a>'
            '<a href="https://www.stepstone.de/all">Alle Jobs ansehen</a>'
            '<a href="https://www.stepstone.de/unsub">Abmelden</a>'
            '<a href="https://www.stepstone.de/job/3">Lagerist (m/w/d)</a>')
    jobs = parse_generic("stepstone", "", html, _CFG["role_terms_title"])
    assert [j.title for j in jobs] == ["Projektkoordinator Photovoltaik (m/w/d)", "Junior Projektmanager Solar"]
    assert jobs[0].url.endswith("/job/1") and jobs[0].source == "stepstone"

def test_generic_email_plaintext():
    text = "Neue Jobs für Sie\n\nProjektleiter PV-Anlagen (m/w/d)\nSolar GmbH\nMünchen\nhttps://de.indeed.com/viewjob?jk=abc\n"
    jobs = parse_generic("indeed", text, "", _CFG["role_terms_title"])
    assert len(jobs) == 1 and jobs[0].company == "Solar GmbH" and jobs[0].location == "München"

class _Resp:
    def __init__(self, status, content=b"", js=None):
        self.status_code, self.content, self._js = status, content, js
    def json(self):
        return self._js

class _Sess:
    def __init__(self, routes): self.routes = routes
    def get(self, url, **kw):
        for k, v in self.routes.items():
            if k in url: return v
        return _Resp(404)

def test_watchlist_personio_and_greenhouse():
    xml = (b'<workzag-jobs><position><id>7</id><name>Projektkoordinator PV</name><office>Berlin</office>'
           b'<createdAt>2026-10-01T00:00:00</createdAt><jobDescriptions><jobDescription><name>A</name>'
           b'<value>&lt;p&gt;MS Project&lt;/p&gt;</value></jobDescription></jobDescriptions></position>'
           b'<position><id>8</id><name>Project Manager</name><office>Madrid, Spain</office></position></workzag-jobs>')
    gh = {"jobs": [{"id": 1, "title": "Project Engineer Solar", "location": {"name": "Hamburg"},
                    "absolute_url": "https://x/1", "updated_at": "2026-10-02T00:00:00Z", "content": "PVsyst"}]}
    s = _Sess({"acme.jobs.personio.de": _Resp(200, xml), "boards-api.greenhouse.io/v1/boards/beta": _Resp(200, js=gh)})
    cfg = {"sources": {"watchlist": {"companies": {"Acme": ["acme"], "Beta": ["beta"], "Gone": ["gone"]}}}}
    cwd = os.getcwd(); tmp = tempfile.mkdtemp(); os.chdir(tmp)
    try:
        jobs = _wl.collect(s, cfg)
    finally:
        os.chdir(cwd)
    titles = sorted(j.title for j in jobs)
    assert titles == ["Project Engineer Solar", "Projektkoordinator PV"]   # Madrid job dropped
    assert any("MS Project" in j.description for j in jobs)

def test_dedupe_company_name_variants():
    a = _Job(source="bundesagentur", source_id="1", title="Projektmanager (m/w/d) Erneuerbare Energien", company="Schmieder GmbH Unternehmensberatung")
    b = _Job(source="adzuna", source_id="2", title="Projektmanager (m/w/d) Erneuerbare Energien", company="Schmieder GmbH")
    out = _dedupe([a, b])
    assert len(out) == 1 and set(out[0].sources) == {"adzuna", "bundesagentur"}

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and name not in ("test_linkedin_parser", "test_status_survives_rerun", "test_dedupe_and_sales_penalty"):
            fn(); print("PASS", name)
