"""Rule-based filtering, dedupe and scoring against Mayank's master CV.
Score out of 100: domain 35, role 25, seniority 15, skills 15, freshness 10, minus penalties."""
import re
from datetime import date
from difflib import SequenceMatcher

LEGAL = re.compile(r"\b(gmbh|ag|se|kg|co|mbh|ug|haftungsbeschränkt|ltd|inc|group|holding|deutschland|germany)\b|[&.,()+]", re.I)
GENDER = re.compile(r"\((?:[mwfdix]\s*/\s*){1,3}[mwfdix]\)|\(all genders?\)|\(gn\)|\*innen|\(in\)|/in\b", re.I)

GERMAN_C1 = re.compile(
    r"(deutsch\w*[^.\n]{0,60}\b(c1|c2|verhandlungssicher|fließend|fliessend|muttersprach)"
    r"|\b(c1|c2|verhandlungssicher\w*|fließend\w*|fliessend\w*|sehr gut\w*|exzellent\w*)\b[^.\n]{0,40}deutsch"
    r"|fluent\s+(in\s+)?german|german[^.\n]{0,30}\b(fluent|native|c1|c2|business)\b|native\s+german)", re.I)
YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d+\s*)?(?:jahre?n?|years?)\b[^.\n]{0,40}"
                   r"(berufserfahrung|erfahrung|experience)|"
                   r"(berufserfahrung|erfahrung|experience)[^.\n]{0,25}?(\d{1,2})\s*\+?\s*(?:jahre?n?|years?)", re.I)
DE_WORDS = re.compile(r"\b(und|die|der|wir|sie|mit|für|ihre|bei|eine)\b", re.I)
EN_WORDS = re.compile(r"\b(and|the|we|you|with|for|your|our|will|are)\b", re.I)


def norm_company(c):
    return re.sub(r"\s+", " ", LEGAL.sub(" ", (c or "").lower())).strip()


def norm_title(t):
    t = GENDER.sub(" ", (t or "").lower())
    return " ".join(re.sub(r"[^a-z0-9äöüß ]+", " ", t).split())


def has_word(text, terms):
    """Whole-word match (so 'hse' does not hit 'Wechsel', 'sap' not 'sapient')."""
    low = (text or "").lower()
    return [t for t in terms if re.search(r"(?<![a-zäöüß])" + re.escape(t) + r"(?![a-zäöüß])", low)]


def has_any(text, terms):
    low = (text or "").lower()
    return [t for t in terms if t in low]


def email_sources(cfg):
    return set(cfg["sources"].get("email_alerts", {}).get("senders", {}))


def title_gate(job, cfg):
    t = job.title.lower()
    if not t or has_any(t, cfg["exclude_title_terms"]):
        return False
    return bool(has_any(t, cfg["role_terms_title"])) or job.source == "linkedin"


def domain_gate(job, cfg):
    blob = f" {job.title} {job.company} {job.description} ".lower()
    if job.source in email_sources(cfg) and not job.description:
        return True    # alerts come from solar searches Mayank set up; score reflects the thin data
    if job.source == "watchlist":
        return True    # employer is a solar/renewables company by definition
    return bool(has_any(blob, cfg["domain_terms"]))


def dedupe(jobs):
    """Same posting on several boards -> one record (keeps longest description, merges sources)."""
    by_company = {}
    for j in jobs:
        comp = norm_company(j.company)
        for known in by_company:       # same firm written longer/shorter on another board
            if comp and known and (comp.startswith(known + " ") or known.startswith(comp + " ")):
                comp = known
                break
        j.key = f"{comp}|{norm_title(j.title)}"
        bucket = by_company.setdefault(comp, [])
        for other in bucket:
            if SequenceMatcher(None, norm_title(j.title), norm_title(other.title)).ratio() >= 0.88:
                keep, drop = (j, other) if len(j.description) > len(other.description) else (other, j)
                keep.sources = sorted(set(keep.sources) | set(drop.sources))
                keep.apply_url = keep.apply_url or drop.apply_url
                keep.posted = max(keep.posted, drop.posted)
                if keep is j:
                    j.key = other.key
                    bucket[bucket.index(other)] = j
                break
        else:
            bucket.append(j)
    return [j for b in by_company.values() for j in b]


def score(job, cfg, today=None):
    today = today or date.today()
    title, desc = job.title.lower(), job.description.lower()
    pts, why, flags = 0, [], []

    # Domain fit (35)
    d_title = has_any(f" {title} ", cfg["domain_terms"])
    d_desc = set(has_any(f" {desc} {job.company.lower()} ", cfg["domain_terms"]))
    d = (25 if d_title else 0) + min(10, 2 * len(d_desc))
    pts += min(35, d)
    if d_title:
        why.append("solar/PV in title")
    elif d_desc:
        why.append("solar/PV in JD")

    # Role fit (25)
    if has_any(title, cfg["role_terms_title"]):
        pts += 25
        why.append("PM/coordination role")
    elif has_any(desc, cfg["role_terms_title"]):
        pts += 10

    # Seniority (15)
    yrs = [int(m.group(1) or m.group(4)) for m in YEARS.finditer(desc)]
    yrs = [y for y in yrs if 1 <= y <= 15]
    if has_any(f"{title} {desc[:600]}", cfg["junior_terms"]):
        pts += 15
        why.append("junior/entry level")
    elif yrs and max(yrs) >= 5:
        pts += 3
        flags.append(f"asks {max(yrs)}+ yrs")
    elif yrs and max(yrs) >= 3:
        pts += 9
        why.append(f"{max(yrs)} yrs asked (Mayank ~3+)")
    else:
        pts += 10

    # CV skills overlap (15)
    skills = has_word(desc, cfg["cv_skills"])
    pts += min(15, 3 * len(skills))
    if skills:
        why.append("skills: " + ", ".join(skills[:5]))

    # Freshness (10)
    try:
        age = (today - date.fromisoformat(job.posted)).days
        pts += 10 if age <= 3 else 7 if age <= 7 else 4 if age <= 14 else 0
    except ValueError:
        pts += 4

    # Penalties
    if GERMAN_C1.search(desc):
        pts -= 25
        flags.append("fluent/C1 German asked")
    elif desc and len(DE_WORDS.findall(desc)) > 2 * max(1, len(EN_WORDS.findall(desc))):
        pts -= 5
        flags.append("German-language posting")
    if has_any(title, cfg["penalty_title_terms"]["sales"]):
        pts -= 30
        flags.append("sales role")
    if has_any(title, cfg["penalty_title_terms"]["trade"]):
        pts -= 25
        flags.append("trade/installer role")
    if not desc:
        flags.append("no JD text (read on site)")

    job.score = max(0, min(100, pts))
    job.bucket = "Strong" if job.score >= 65 else "Review" if job.score >= 45 else "Low"
    job.reasons, job.flags = why, flags
    return job
