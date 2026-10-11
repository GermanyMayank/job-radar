import html
import re
import time
from dataclasses import dataclass, field

import requests

UA = "Mozilla/5.0 (job-radar personal job search; low volume)"


@dataclass
class Job:
    source: str
    source_id: str
    title: str
    company: str = ""
    location: str = ""
    url: str = ""              # page to read the posting
    apply_url: str = ""        # external apply link if the source gives one
    posted: str = ""           # ISO date YYYY-MM-DD, may be empty
    description: str = ""
    sources: list = field(default_factory=list)
    score: int = 0
    bucket: str = ""
    reasons: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    key: str = ""

    def __post_init__(self):
        self.title = clean_text(self.title)
        self.company = clean_text(self.company)
        self.description = clean_text(self.description)
        if not self.sources:
            self.sources = [self.source]


def clean_text(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>|</p>|</li>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\u00a0]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def get_json(session, url, params=None, headers=None, retries=3, quiet=False):
    """GET with polite retry on 429/5xx. Returns parsed JSON or None."""
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    for attempt in range(retries):
        try:
            r = session.get(url, params=params, headers=h, timeout=30)
        except requests.RequestException as e:
            if not quiet:
                print(f"  ! {url}: {e}")
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                return None
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(3 * (attempt + 1))
            continue
        if not quiet:
            print(f"  ! {url} -> HTTP {r.status_code}")
        return None
    return None
