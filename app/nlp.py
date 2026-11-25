"""Lightweight, dependency-free text analysis: skills, titles, seniority, experience, keywords.

Everything here is pure Python and runs in a few milliseconds per document, so the app
needs no paid AI API and no heavy ML model.
"""
from __future__ import annotations

import html
import math
import re
from collections import Counter
from datetime import datetime, timezone

from .skills import SKILLS_RAW, SOFT_SKILLS, TITLE_FAMILIES

# --------------------------------------------------------------------------- tokenising
# Keeps tech tokens such as "c++", "c#", "node.js", ".net" intact; splits on - and /.
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#]*(?:\.[A-Za-z0-9+#]+)*|\.[A-Za-z][A-Za-z0-9]*")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

STOPWORDS = set("""
a about above after again against all am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have
having he her here hers herself him himself his how i if in into is it its itself just me more most
my myself no nor not now of off on once only or other our ours ourselves out over own same she should
so some such than that the their theirs them themselves then there these they this those through to
too under until up very was we were what when where which while who whom why will with would you your
yours yourself yourselves also etc per via within across including include includes well new using
use used work working works job role team teams company us looking join you'll we're you're it's
able ability strong experience experienced years year skills skill knowledge must required requirements
preferred plus responsibilities responsible opportunity candidate candidates position apply etc
help make ensure based across will may like get one two three time day days week weeks month
""".split())


_LINE_WS_RE = re.compile(r"[ \t\r\f\v ]+")


def strip_html(text: str, keep_lines: bool = False) -> str:
    """HTML to plain text. With keep_lines, paragraphs and bullet points survive (for display)."""
    if not text:
        return ""
    if keep_lines:
        text = re.sub(r"(?i)<\s*li[^>]*>", "\n• ", text)
    text = re.sub(r"(?i)<\s*(br|/p|/li|/h\d|/div|/ul|/ol|/tr|/section)\s*/?>", "\n", text)
    text = re.sub(r"(?i)<\s*(p|h\d|ul|ol|div|section)(\s[^>]*)?>", "\n", text) if keep_lines else text
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    if not keep_lines:
        return _WS_RE.sub(" ", text).strip()
    out: list[str] = []
    for line in text.split("\n"):
        line = _LINE_WS_RE.sub(" ", line).strip()
        if line in ("•", "• "):
            continue
        if line or (out and out[-1]):
            out.append(line)
    # consecutive bullet points stay together; other blocks keep one blank line between them
    out = [l for i, l in enumerate(out)
           if l or not (0 < i < len(out) - 1 and out[i - 1].startswith("•") and out[i + 1].startswith("•"))]
    return "\n".join(out).strip()


def tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text or "")


# --------------------------------------------------------------------------- skills
def _norm_phrase(s: str) -> tuple[str, ...]:
    return tuple(t.lower() for t in tokens(s))


def _build_skill_lookup():
    lookup: dict[tuple[str, ...], list[tuple[str, str | None]]] = {}
    max_len = 1
    for line in SKILLS_RAW.strip().splitlines():
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if not parts:
            continue
        canonical = parts[0].lstrip("=")
        for alias in parts:
            case_sensitive = alias.startswith("=")
            alias = alias.lstrip("=")
            key = _norm_phrase(alias)
            if not key:
                continue
            exact = " ".join(tokens(alias)) if case_sensitive else None
            # if the canonical itself is ambiguous (e.g. "Go") only the =alias form is case-free
            lookup.setdefault(key, []).append((canonical, exact))
            max_len = max(max_len, len(key))
    return lookup, max_len


SKILL_LOOKUP, _MAX_NGRAM = _build_skill_lookup()
# Short words that are only skills when written exactly (case-sensitive).
_CASE_ONLY = {("go",), ("r",), ("swift",), ("rust",), ("ruby",), ("excel",), ("julia",),
              ("unity",), ("sketch",), ("bootstrap",), ("node",), ("german",),
              ("french",), ("spanish",)}
ALL_SKILLS = sorted({c for v in SKILL_LOOKUP.values() for c, _ in v})
SKILL_SET = set(ALL_SKILLS)


def extract_skills(text: str) -> Counter:
    """Return Counter(canonical_skill -> occurrences) using greedy longest n-gram match."""
    toks = tokens(text)
    low = [t.lower() for t in toks]
    found: Counter = Counter()
    i, n = 0, len(toks)
    while i < n:
        matched = 0
        for L in range(min(_MAX_NGRAM, n - i), 0, -1):
            key = tuple(low[i:i + L])
            cands = SKILL_LOOKUP.get(key)
            if not cands:
                continue
            original = " ".join(toks[i:i + L])
            for canonical, exact in cands:
                if exact is not None:
                    if original == exact:
                        found[canonical] += 1
                        matched = L
                        break
                elif key not in _CASE_ONLY:
                    found[canonical] += 1
                    matched = L
                    break
            if matched:
                break
        i += matched or 1
    return found


# --------------------------------------------------------------------------- titles
_TITLE_SYNONYMS = {
    "developer": "engineer", "dev": "engineer", "programmer": "engineer", "swe": "engineer",
    "sde": "engineer", "frontend": "front", "backend": "back", "fullstack": "full",
    "sr": "senior", "jr": "junior", "mgr": "manager", "ml": "machine", "ai": "machine",
}
_LEVEL_WORDS = {"senior", "junior", "lead", "staff", "principal", "head", "chief", "intern",
                "associate", "entry", "level", "i", "ii", "iii", "iv", "mid", "remote", "sr", "jr",
                "trainee", "graduate", "fresher", "contract", "part", "full", "time", "freelance"}

_TITLE_INDEX: list[tuple[tuple[str, ...], str, str]] = []
for fam, titles in TITLE_FAMILIES.items():
    for t in titles:
        _TITLE_INDEX.append((_norm_phrase(t), t, fam))
_TITLE_INDEX.sort(key=lambda x: -len(x[0]))

# Family keyword fallbacks used when no exact title phrase is present in a job title.
_FAMILY_HINTS = [
    ("data", {"data", "analytics", "analyst", "scientist", "machine", "ml", "ai", "bi", "statistician"}),
    ("devops", {"devops", "sre", "reliability", "infrastructure", "cloud", "platform", "sysadmin"}),
    ("security", {"security", "cybersecurity", "soc", "penetration"}),
    ("qa", {"qa", "tester", "sdet", "quality", "testing"}),
    ("design", {"designer", "design", "ux", "ui", "artist", "illustrator"}),
    ("product", {"product"}),
    ("software", {"engineer", "developer", "programmer", "software", "frontend", "backend",
                  "fullstack", "android", "ios", "web", "architect"}),
    ("marketing", {"marketing", "seo", "growth", "brand", "social"}),
    ("content", {"writer", "copywriter", "editor", "content", "journalist"}),
    ("sales", {"sales", "account", "business", "partnerships", "bdr", "sdr"}),
    ("support", {"support", "success", "customer", "service"}),
    ("finance", {"finance", "financial", "accountant", "accounting", "tax", "audit", "payroll"}),
    ("hr", {"recruiter", "talent", "hr", "people", "recruiting"}),
    ("project", {"project", "program", "scrum", "delivery"}),
    ("admin", {"assistant", "administrative", "receptionist", "office"}),
    ("healthcare", {"nurse", "medical", "clinical", "health", "physician", "pharmacist"}),
    ("education", {"teacher", "tutor", "instructor", "education", "trainer"}),
    ("legal", {"legal", "lawyer", "attorney", "paralegal", "counsel"}),
]


def title_core(title: str) -> frozenset[str]:
    out = set()
    for t in tokens(title.lower()):
        t = _TITLE_SYNONYMS.get(t, t)
        if t in _LEVEL_WORDS or t in STOPWORDS or len(t) < 2:
            continue
        out.add(t)
    return frozenset(out)


def title_family(title: str) -> str | None:
    low = tuple(t.lower() for t in tokens(title))
    s = " " + " ".join(low) + " "
    for key, _t, fam in _TITLE_INDEX:
        if " " + " ".join(key) + " " in s:
            return fam
    toks = set(low)
    for fam, hints in _FAMILY_HINTS:
        if toks & hints:
            return fam
    return None


def infer_titles(text: str) -> list[str]:
    """Find likely job titles in a résumé; titles near the top weigh more."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    scores: Counter = Counter()
    for idx, line in enumerate(lines[:200]):
        low = " " + " ".join(t.lower() for t in tokens(line)) + " "
        weight = 3.0 if idx < 6 else (1.5 if idx < 25 else 1.0)
        for key, title, _fam in _TITLE_INDEX:
            if " " + " ".join(key) + " " in low:
                scores[title] += weight * (1 + 0.15 * len(key))
                low = low.replace(" " + " ".join(key) + " ", " ")  # longest phrase wins
    return [t for t, _ in scores.most_common(4)]


# --------------------------------------------------------------------------- seniority / years
LEVELS = ["intern", "entry", "mid", "senior", "lead", "executive"]


def level_from_title(title: str) -> str | None:
    t = " " + " ".join(tokens(title.lower())) + " "
    if re.search(r" (intern|internship|trainee|apprentice|working student|werkstudent|praktikum) ", t):
        return "intern"
    if re.search(r" (chief|vp|vice president|director|head of|cto|cfo|ceo|coo) ", t):
        return "executive"
    if re.search(r" (lead|principal|staff|architect|manager) ", t):
        return "lead"
    if re.search(r" (senior|sr|iii|iv|v) ", t):
        return "senior"
    if re.search(r" (junior|jr|entry|graduate|grad|associate|assoc|fresher|i|level 1|l1) ", t):
        return "entry"  # "Software Engineer I" is the first rung
    if re.search(r" (ii|mid|intermediate|level 2|l2) ", t):
        return "mid"
    return None


# Seniority stated in a job description, used only when the title and required years say nothing.
_LEVEL_TEXT = [
    ("intern", re.compile(r"(?i)\b(internship program(me)?|working student|werkstudent\w*|pflichtpraktikum)\b")),
    ("entry", re.compile(r"(?i)\b(entry[- ]level|new[- ]grad(uate)?s?|recent (college |university )?graduates?|graduate (program(me)?|scheme)|"
                         r"no (prior |previous )?(work )?experience (is )?(required|needed)|freshers?( are)? welcome|"
                         r"berufseinsteiger\w*|erste (berufs)?erfahrung\w*|junior[- ]level|early[- ]career)\b")),
    ("senior", re.compile(r"(?i)\b(senior[- ]level|seasoned|extensive (professional |industry |hands-on )?experience|"
                          r"langjährige\w* (berufs)?erfahrung|significant experience leading)\b")),
    ("mid", re.compile(r"(?i)\b(mehrjährige\w* (berufs)?erfahrung|mid[- ]level|several years of (professional )?experience)\b")),
]


def level_from_text(text: str) -> str | None:
    for level, rx in _LEVEL_TEXT:
        if rx.search(text or ""):
            return level
    return None


def level_from_years(years: float) -> str:
    if years < 1:
        return "entry"
    if years < 3:
        return "entry" if years < 2 else "mid"
    if years < 6:
        return "mid"
    if years < 10:
        return "senior"
    return "lead"


_YEARS_STATED = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)(?:\s+of)?(?:\s+\w+){0,4}?\s+(?:experience|exp)\b", re.I)
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DATE = r"(?:(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*|(\d{1,2})[/\-.])?((?:19|20)\d{2})"
_RANGE_RE = re.compile(_DATE + r"\s*(?:-|–|—|to|until|till)\s*(?:" + _DATE + r"|(present|current|now|today|date|ongoing))", re.I)
_EDU_RE = re.compile(r"(?i)universit|college|school|b\.?tech|b\.?e\b|bachelor|master|m\.?tech|mba|degree|gpa|cgpa|diploma|ssc|hsc|class x|education|b\.?sc|m\.?sc|ph\.?d")


def years_of_experience(text: str) -> float:
    stated = [float(m.group(1)) for m in _YEARS_STATED.finditer(text) if 0 < float(m.group(1)) <= 45]
    now = datetime.now(timezone.utc)
    intervals = []
    for line in text.splitlines():
        if _EDU_RE.search(line):
            continue
        for m in _RANGE_RE.finditer(line):
            mon1 = _MONTHS.get((m.group(1) or "")[:3].lower()) or (int(m.group(2)) if m.group(2) and 0 < int(m.group(2)) <= 12 else 1)
            y1 = int(m.group(3))
            if m.group(7):
                y2, mon2 = now.year, now.month
            else:
                y2 = int(m.group(6))
                mon2 = _MONTHS.get((m.group(4) or "")[:3].lower()) or (int(m.group(5)) if m.group(5) and 0 < int(m.group(5)) <= 12 else 12)
            a, b = y1 * 12 + mon1, y2 * 12 + mon2
            if 1975 * 12 < a <= b <= now.year * 12 + now.month + 1:
                intervals.append((a, b + 1))  # end month is inclusive
    months = 0
    if intervals:
        intervals.sort()
        cs, ce = intervals[0]
        for s, e in intervals[1:]:
            if s <= ce:
                ce = max(ce, e)
            else:
                months += ce - cs
                cs, ce = s, e
        months += ce - cs
    from_ranges = round(months / 12, 1)
    if stated:
        # résumé summaries ("5+ years of experience") are usually the most reliable signal
        return max(min(max(stated), 45), from_ranges if from_ranges <= max(stated) + 3 else 0)
    return min(from_ranges, 45)


# English, German ("3 Jahre Berufserfahrung") and French ("3 ans d'expérience")
_REQ_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:(?:-|–|—|to|bis|à)\s*(\d{1,2})\s*\+?\s*)?(?:years?|yrs?|jahren?|ans)\b", re.I)
_EXP_WORDS = ("experience", "erfahrung", "expérience", "experiencia")


def required_years(text: str) -> tuple[int | None, int | None]:
    """Years of experience a job asks for, as (minimum, maximum). '3-5 years' -> (3, 5); '4+ years' -> (4, None)."""
    for m in _REQ_YEARS.finditer(text or ""):
        tail = text[m.end():m.end() + 60].lower()
        head = text[max(0, m.start() - 40):m.start()].lower()
        if any(w in tail for w in _EXP_WORDS) or "exp" in tail[:6] or any(w in head for w in _EXP_WORDS):
            lo = int(m.group(1))
            hi = int(m.group(2)) if m.group(2) else None
            if 0 < lo <= 20 and (hi is None or lo < hi <= 30):
                return lo, hi
    return None, None


def canonical_skill(name: str) -> str | None:
    """'reactjs' -> 'React' when the name is a known skill or alias, else None."""
    cands = SKILL_LOOKUP.get(_norm_phrase(name))
    if not cands:
        return None
    for canonical, exact in cands:
        if exact is None or " ".join(tokens(name)) == exact:
            return canonical
    return cands[0][0]


# --------------------------------------------------------------------------- contact details (autofill)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<![\w])(\+?\d[\d\s().-]{8,16}\d)(?![\w])")
_URL_RE = re.compile(r"(?i)\b((?:https?://)?(?:www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s,;|()<>]*)?)")
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*){1,3}$")


def extract_contact(text: str) -> dict:
    """Name, email, phone and profile links from a résumé. Used to pre-fill application forms."""
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    head = "\n".join(lines[:25])
    out = {"first_name": "", "last_name": "", "email": "", "phone": "", "linkedin": "", "github": "", "website": ""}
    for line in lines[:6]:
        cand = re.sub(r"\s+", " ", line.split("|")[0]).strip()
        low = cand.lower()
        if (_NAME_RE.match(cand) and not _EMAIL_RE.search(cand) and not title_family(cand)
                and not any(w in low for w in ("resume", "curriculum", "vitae", "profile", "summary"))):
            parts = cand.title() if cand.isupper() else cand
            first, *rest = parts.split(" ")
            out["first_name"], out["last_name"] = first, " ".join(rest)
            break
    if m := _EMAIL_RE.search(head) or _EMAIL_RE.search(text or ""):
        out["email"] = m.group(0)
    for m in _PHONE_RE.finditer(head):
        digits = re.sub(r"\D", "", m.group(1))
        if 10 <= len(digits) <= 13 and not re.fullmatch(r"(19|20)\d{2}\D*(19|20)\d{2}", m.group(1).strip()):
            out["phone"] = re.sub(r"\s+", " ", m.group(1)).strip()
            break
    for m in _URL_RE.finditer(text or ""):
        u = m.group(1).rstrip(".")
        low = u.lower()
        if "@" in u or low.endswith((".pdf", ".docx")):
            continue
        full = u if low.startswith("http") else "https://" + u
        if "linkedin.com/" in low and not out["linkedin"]:
            out["linkedin"] = full
        elif "github.com/" in low and not out["github"]:
            out["github"] = full
        elif not out["website"] and not any(d in low for d in ("linkedin.", "github.", "gmail.", "yahoo.", "outlook.", "hotmail.")) \
                and ("/" in low.split("//")[-1] or low.count(".") >= 1) and len(u) > 6 and not re.match(r"^\d", u):
            if re.search(r"(?i)portfolio|\.dev\b|\.io\b|\.me\b|vercel\.app|netlify\.app|github\.io|behance|dribbble", low):
                out["website"] = full
    return out


def _clean_seg(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" ,|–—-:•·\t")


def extract_history(text: str) -> tuple[list[dict], list[dict]]:
    """Work experience and education entries (title, company, dates). Heuristic: the user reviews them."""
    lines = [l.strip() for l in (text or "").splitlines()]
    jobs, schools = [], []
    now = datetime.now(timezone.utc)
    for idx, line in enumerate(lines):
        m = _RANGE_RE.search(line)
        if not m:
            continue
        mon1 = _MONTHS.get((m.group(1) or "")[:3].lower()) or (int(m.group(2)) if m.group(2) and 0 < int(m.group(2)) <= 12 else None)
        start = {"month": mon1, "year": int(m.group(3))}
        if m.group(7):
            end, current = {"month": now.month, "year": now.year}, True
        else:
            mon2 = _MONTHS.get((m.group(4) or "")[:3].lower()) or (int(m.group(5)) if m.group(5) and 0 < int(m.group(5)) <= 12 else None)
            end, current = {"month": mon2, "year": int(m.group(6))}, False
        rest = _clean_seg(line[:m.start()] + " " + line[m.end():])
        context = [rest] if len(rest) > 2 else []
        if idx > 0 and lines[idx - 1] and not _RANGE_RE.search(lines[idx - 1]):
            context.append(_clean_seg(lines[idx - 1]))
        blob = " | ".join(c for c in context if c)
        if _EDU_RE.search(blob):
            segs = [_clean_seg(s) for s in re.split(r"\s*(?:\||,| - | – | — )\s*", blob) if _clean_seg(s)]
            school = next((s for s in segs if re.search(r"(?i)universit|college|school|institute|iit|nit|academy", s)), segs[0] if segs else "")
            degree = next((s for s in segs if s != school and _EDU_RE.search(s)), "")
            schools.append({"school": school[:120], "degree": degree[:120], "start": start, "end": end})
            continue
        segs = [_clean_seg(s) for s in re.split(r"\s*(?:\||,| at | @ | - | – | — )\s*", blob) if _clean_seg(s)]
        title = next((s for s in segs if title_family(s)), "")
        company = next((s for s in segs if s != title and not _PLACE_RE.fullmatch(s) and len(s) < 80), "")
        location = next((s for s in segs if _PLACE_RE.search(s) and s not in (title, company)), "")
        if title or company:
            jobs.append({"title": title[:120], "company": company[:120], "location": location[:80],
                         "start": start, "end": end, "current": current})
    return jobs[:10], schools[:6]


# --------------------------------------------------------------------------- keyword vectors
def term_counts(text: str, limit: int = 80) -> dict[str, int]:
    c = Counter(t for t in (w.lower() for w in tokens(text))
                if len(t) > 2 and t not in STOPWORDS and not t.isdigit())
    return dict(c.most_common(limit))


def tfidf(counts: dict[str, int], idf: dict[str, float], default_idf: float) -> dict[str, float]:
    vec = {t: (1 + math.log(c)) * idf.get(t, default_idf) for t, c in counts.items()}
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {t: v / norm for t, v in vec.items()}


def is_soft(skill: str) -> bool:
    return skill in SOFT_SKILLS


_PLACES = ["Bengaluru", "Bangalore", "Hyderabad", "Pune", "Mumbai", "Chennai", "Gurgaon", "Gurugram", "Noida",
           "New Delhi", "Delhi", "Kolkata", "Ahmedabad", "Kochi", "Jaipur", "Coimbatore", "Chandigarh", "Indore",
           "Visakhapatnam", "Vijayawada", "Thiruvananthapuram", "Mysore", "Nagpur", "Bhubaneswar", "Lucknow",
           "London", "Berlin", "Amsterdam", "Dublin", "Paris", "Toronto", "Vancouver", "Singapore", "Dubai", "Sydney",
           "New York", "San Francisco", "Seattle", "Austin", "Boston", "Chicago",
           "India", "United States", "USA", "United Kingdom", "Germany", "Canada", "Australia", "Netherlands", "UAE"]
_PLACE_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in _PLACES) + r")\b", re.I)


def detect_location(text: str) -> str:
    """City or country from the résumé header (first lines), used to pre-fill outside searches."""
    head = "\n".join(text.splitlines()[:15])
    m = _PLACE_RE.search(head)
    if not m:
        return ""
    found = next(p for p in _PLACES if p.lower() == m.group(1).lower())
    return {"Bangalore": "Bengaluru", "Gurgaon": "Gurugram", "USA": "United States"}.get(found, found)
