"""Parser for LinkedIn job alert emails (used by email_alerts.py).
No LinkedIn scraping: we only read the alerts LinkedIn emails to Mayank.
Alerts carry title / company / location only; read the full JD on the posting."""
import re

from radar.models import Job, clean_text

SENDER = "jobalerts-noreply@linkedin.com"
JOB_LINK = re.compile(r"https?://(?:[a-z]+\.)?linkedin\.com/(?:comm/)?jobs/view/(\d+)[^\s\"'<>]*", re.I)
# Badge / status lines LinkedIn puts around each job; never a title, company or location.
SKIP_LINES = re.compile(r"(^view job|^apply|easy apply|actively (hiring|recruiting)|early applicant|"
                        r"promoted|\balumni?\b|\bconnections?\b|\bapplicants?\b|^new$|see all jobs|"
                        r"^\d+ (school|company)|^\W*$)", re.I)


def parse_alert(text, html_, posted=""):
    """Return Jobs from one alert email. Plain-text alerts list each job as
    title / company / location lines followed by a 'View job: <link>' line."""
    jobs, seen = [], set()
    body = text or clean_text(html_)
    lines = [l.strip() for l in body.splitlines()]
    for i, line in enumerate(lines):
        m = JOB_LINK.search(line)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        prev = []
        j = i - 1
        while j >= 0 and len(prev) < 3:
            cand = lines[j]
            if cand and not SKIP_LINES.search(cand) and not JOB_LINK.search(cand) and not cand.startswith("-----"):
                prev.insert(0, cand)
            elif JOB_LINK.search(cand) or cand.startswith("-----"):
                break
            j -= 1
        title, company, location = (prev + ["", "", ""])[:3]
        jobs.append(Job(source="linkedin", source_id=m.group(1), title=title, company=company,
                        location=location, url=f"https://www.linkedin.com/jobs/view/{m.group(1)}/",
                        posted=posted))
    return jobs
