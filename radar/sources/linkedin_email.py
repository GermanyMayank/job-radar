"""LinkedIn job alert emails, read over IMAP (read-only) from the inbox that receives them.
No LinkedIn scraping: we only parse emails LinkedIn sends to the user.
Needs IMAP_USER and IMAP_PASSWORD (a Gmail app password), optional IMAP_HOST.
Alert emails carry title/company/location only; the full JD is read on the
company site or pasted into Claude for shortlisted jobs."""
import email
import imaplib
import os
import re
from datetime import date, timedelta
from email.utils import parsedate_to_datetime

from radar.models import Job, clean_text

SENDER = "jobalerts-noreply@linkedin.com"
JOB_LINK = re.compile(r"https?://(?:[a-z]+\.)?linkedin\.com/(?:comm/)?jobs/view/(\d+)[^\s\"'<>]*", re.I)
SKIP_LINES = re.compile(r"^(view job|apply|easy apply|actively recruiting|promoted|\d+ (school|company) alum|"
                        r"be an early applicant|new|see all jobs|\W*)$", re.I)


def _parts(msg):
    text, html_ = "", ""
    for part in msg.walk():
        ctype = part.get_content_type()
        if part.get_content_maintype() == "multipart":
            continue
        try:
            payload = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        except Exception:
            continue
        if ctype == "text/plain":
            text += payload
        elif ctype == "text/html":
            html_ += payload
    return text, html_


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
            if cand and not SKIP_LINES.match(cand) and not JOB_LINK.search(cand) and not cand.startswith("-----"):
                prev.insert(0, cand)
            elif JOB_LINK.search(cand) or cand.startswith("-----"):
                break
            j -= 1
        title, company, location = (prev + ["", "", ""])[:3]
        jobs.append(Job(source="linkedin", source_id=m.group(1), title=title, company=company,
                        location=location, url=f"https://www.linkedin.com/jobs/view/{m.group(1)}/",
                        posted=posted))
    return jobs


def collect(session, cfg):
    user, pw = os.getenv("IMAP_USER"), os.getenv("IMAP_PASSWORD")
    if not (user and pw):
        print("  linkedin_email: skipped (no IMAP_USER / IMAP_PASSWORD)")
        return []
    sc = cfg["sources"]["linkedin_email"]
    since = (date.today() - timedelta(days=sc.get("days_back", 3))).strftime("%d-%b-%Y")
    jobs = []
    imap = imaplib.IMAP4_SSL(os.getenv("IMAP_HOST", "imap.gmail.com"))
    try:
        imap.login(user, pw)
        imap.select(sc.get("mailbox", "INBOX"), readonly=True)   # never marks or changes mail
        _, ids = imap.search(None, f'(FROM "{SENDER}" SINCE {since})')
        for mid in ids[0].split():
            _, data = imap.fetch(mid, "(BODY.PEEK[])")
            msg = email.message_from_bytes(data[0][1])
            try:
                posted = parsedate_to_datetime(msg["Date"]).date().isoformat()
            except Exception:
                posted = ""
            jobs.extend(parse_alert(*_parts(msg), posted=posted))
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    print(f"  linkedin_email: {len(jobs)} raw")
    return jobs
