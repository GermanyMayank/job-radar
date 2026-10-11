"""Job alert emails from several boards, read over IMAP (read-only) from Mayank's Gmail.
No board is scraped: we only parse alerts the boards send him.
LinkedIn has a dedicated parser; every other board uses a generic one that finds
job-title lines and links. Board-specific tuning happens once real alerts arrive.
Needs IMAP_USER and IMAP_PASSWORD (Gmail app password), optional IMAP_HOST."""
import email
import imaplib
import os
import re
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from radar.models import Job, clean_text
from radar.sources.linkedin_email import parse_alert as parse_linkedin

URL = re.compile(r"https?://[^\s\"'<>)\]]+")
NOISE = re.compile(r"(unsubscribe|abmelden|abbestellen|datenschutz|privacy|impressum|einstellungen|settings|"
                   r"alle (jobs|stellen)|see all|view all|mehr jobs|app|help|hilfe|kontakt|feedback|"
                   r"^\W*$|^jetzt bewerben$|^apply( now)?$|^details$|^ansehen$|^view job$)", re.I)


class _Anchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items, self._href, self._text = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._text = dict(attrs).get("href"), []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.items.append((self._href, " ".join(" ".join(self._text).split())))
            self._href = None


def _parts(msg):
    text, html_ = "", ""
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        try:
            payload = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        except Exception:
            continue
        if part.get_content_type() == "text/plain":
            text += payload
        elif part.get_content_type() == "text/html":
            html_ += payload
    return text, html_


def parse_generic(board, text, html_, role_terms, posted=""):
    """Any job-alert email: anchors (HTML) or 'title line + link' (plain text).
    Keeps only lines that look like job titles (contain a role term)."""
    jobs, seen = [], set()

    def add(title, url, company="", location=""):
        title = " ".join((title or "").split())
        if not title or not url or NOISE.search(title) or len(title) > 160:
            return
        if not any(t in title.lower() for t in role_terms):
            return
        key = title.lower()
        if key in seen:
            return
        seen.add(key)
        jobs.append(Job(source=board, source_id=url[-120:], title=title, company=company,
                        location=location, url=url, posted=posted))

    if html_:
        p = _Anchors()
        try:
            p.feed(html_)
        except Exception:
            pass
        for href, txt in p.items:
            add(txt, href)
    if not jobs and text:
        lines = [l.strip() for l in text.splitlines()]
        for i, line in enumerate(lines):
            if any(t in line.lower() for t in role_terms) and not URL.search(line):
                nxt = [l for l in lines[i + 1:i + 6] if l]
                link = next((URL.search(l).group(0) for l in nxt if URL.search(l)), "")
                info = [l for l in nxt if not URL.search(l)][:2]
                add(line, link, *(info + ["", ""])[:2])
    return jobs


def collect(session, cfg):
    user = (os.getenv("IMAP_USER") or "").strip()
    pw = "".join((os.getenv("IMAP_PASSWORD") or "").split())
    if not (user and pw):
        print("  email_alerts: skipped (no IMAP_USER / IMAP_PASSWORD)")
        return []
    sc = cfg["sources"]["email_alerts"]
    since = (date.today() - timedelta(days=sc.get("days_back", 3))).strftime("%d-%b-%Y")
    imap = imaplib.IMAP4_SSL(os.getenv("IMAP_HOST", "imap.gmail.com"))
    out = []
    try:
        try:
            imap.login(user, pw)
        except imaplib.IMAP4.error as e:
            print(f"  email_alerts: login rejected ({e}). Needs full Gmail address + 16-char app password.")
            return []
        imap.select(sc.get("mailbox", "INBOX"), readonly=True)   # never marks or changes mail
        for board, sender in sc["senders"].items():
            _, ids = imap.search(None, f'(FROM "{sender}" SINCE {since})')
            n_mail, before = len(ids[0].split()), len(out)
            for mid in ids[0].split():
                _, data = imap.fetch(mid, "(BODY.PEEK[])")
                msg = email.message_from_bytes(data[0][1])
                try:
                    posted = parsedate_to_datetime(msg["Date"]).date().isoformat()
                except Exception:
                    posted = ""
                text, html_ = _parts(msg)
                if board == "linkedin":
                    out += parse_linkedin(text, html_, posted=posted)
                else:
                    out += parse_generic(board, text, html_, cfg["role_terms_title"], posted=posted)
            if n_mail:
                print(f"  email_alerts/{board}: {n_mail} mails -> {len(out) - before} jobs")
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    print(f"  email_alerts: {len(out)} raw")
    return out
