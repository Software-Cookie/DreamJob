"""Scores jobs against a résumé profile and explains each score."""
from __future__ import annotations

import io
import re
import time
from dataclasses import dataclass

from . import nlp
from .index import Job

LEVEL_RANK = {l: i for i, l in enumerate(nlp.LEVELS)}
WORLDWIDE = ("worldwide", "anywhere", "global", "remote")
OPEN_TO_ALL = ("worldwide", "anywhere", "global", "world")
_INDIA = ["india", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai", "chennai", "gurgaon", "gurugram",
          "noida", "delhi", "kolkata", "ahmedabad", "kochi", "jaipur", "coimbatore", "chandigarh", "indore", "thiruvananthapuram"]
LOCATION_ALIASES = {
    "india": _INDIA, "in": _INDIA,
    "usa": ["united states", "usa", "u.s.", ", us", "us-", "america"], "us": ["united states", "usa", "u.s.", ", us", "us-"],
    "united states": ["united states", "usa", "u.s.", ", us"], "america": ["united states", "usa", "americas"],
    "uk": ["united kingdom", "uk", "london", "england", "scotland", "manchester"], "united kingdom": ["united kingdom", "uk", "london", "england"],
    "europe": ["europe", "emea", "eu", "germany", "france", "netherlands", "spain", "ireland", "poland", "portugal", "berlin", "london", "amsterdam"],
    "bangalore": ["bangalore", "bengaluru"], "bengaluru": ["bangalore", "bengaluru"],
    "gurgaon": ["gurgaon", "gurugram"], "gurugram": ["gurgaon", "gurugram"], "delhi": ["delhi", "noida", "gurgaon", "gurugram", "ncr"],
}


def _location_matcher(location: str):
    """Returns a predicate for the location filter, or None when no location is set."""
    terms = [t.strip().lower() for t in re.split(r"[,/;]| or ", location or "") if t.strip()]
    if not terms:
        return None
    wants_remote = any(t in ("remote", "anywhere", "worldwide") for t in terms)
    needles = sorted({n for t in terms if t not in ("remote", "anywhere", "worldwide") for n in LOCATION_ALIASES.get(t, [t])})

    def ok(job) -> bool:
        jl = job.location.lower()
        if wants_remote and job.remote:
            return True
        if needles and any(n in jl for n in needles):
            return True
        # remote jobs open to everyone also fit any location; "Remote - US" does not
        return bool(needles) and job.remote and (jl.strip() in ("", "remote") or any(w in jl for w in OPEN_TO_ALL))
    return ok


def feed_name(source: str) -> str:
    return "Company career sites" if source.endswith(" careers") else source


@dataclass
class Profile:
    titles: list[str]
    skills: list[str]
    years: float
    level: str
    terms: dict
    family: str | None = None
    location: str = ""

    @property
    def queries(self) -> list[str]:
        return self.search_queries(1)

    def search_queries(self, n: int) -> list[str]:
        """Up to n live searches: the main job titles, then the strongest hard skills phrased as a role."""
        out = list(dict.fromkeys(self.titles[:2]))
        noun = self.titles[0].split()[-1] if self.titles else "developer"
        for s in (s for s in self.skills if not nlp.is_soft(s)):
            if len(out) >= n:
                break
            q = f"{s} {noun}"
            if q.lower() not in (x.lower() for x in out):
                out.append(q)
        return out[:n]

    def public(self) -> dict:
        return {"titles": self.titles, "skills": self.skills, "years": self.years,
                "level": self.level, "family": self.family, "terms": self.terms, "location": self.location}


# ---------------------------------------------------------------------- résumé → profile
class ResumeError(ValueError):
    pass


def read_resume(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    try:
        if name.endswith(".pdf") or data[:4] == b"%PDF":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise ResumeError("This PDF is password-protected. Remove the password and upload it again.")
            text = "\n".join((p.extract_text() or "") for p in reader.pages[:12])
        elif name.endswith(".docx"):
            from docx import Document
            doc = Document(io.BytesIO(data))
            parts = [p.text for p in doc.paragraphs]
            for table in doc.tables:
                for row in table.rows:
                    parts.append(" | ".join(c.text for c in row.cells))
            text = "\n".join(parts)
        elif name.endswith((".txt", ".md", ".rtf")) or not name:
            text = data.decode("utf-8", errors="ignore")
        else:
            raise ResumeError("Upload a PDF, DOCX or TXT file.")
    except ResumeError:
        raise
    except Exception:
        raise ResumeError("This file could not be read. Try saving it again as PDF or DOCX, or paste the text.")
    text = text.replace("\x00", " ").strip()
    if len(text) < 80:
        raise ResumeError("No readable text was found. If the PDF is a scanned image, upload a DOCX or paste the text instead.")
    return text[:60000]


def build_profile(text: str) -> Profile:
    skills = nlp.extract_skills(text)
    titles = nlp.infer_titles(text)
    years = nlp.years_of_experience(text)
    head = "\n".join(text.splitlines()[:8])
    level = None
    if titles:
        for line in head.splitlines():
            if any(t in line.lower() for t in titles):
                level = nlp.level_from_title(line)
                break
    level = level or nlp.level_from_years(years)
    family = nlp.title_family(titles[0]) if titles else None
    ordered = [s for s, _ in sorted(skills.items(), key=lambda kv: (-kv[1], kv[0]))]
    return Profile(titles=titles, skills=ordered, years=years, level=level,
                   terms=nlp.term_counts(text, 60), family=family, location=nlp.detect_location(text))


# ---------------------------------------------------------------------- scoring
def _skill_weight(s: str) -> float:
    return 0.35 if nlp.is_soft(s) else 1.0


def split_skills(skills: list[str]) -> tuple[set, dict]:
    """Known skills (canonical names) and custom ones (anything else the user typed: lower -> as typed)."""
    known, custom = set(), {}
    for s in skills:
        s = (s or "").strip()
        if not s:
            continue
        c = s if s in nlp.SKILL_SET else nlp.canonical_skill(s)
        if c:
            known.add(c)
        elif len(s) >= 2:
            custom.setdefault(s.lower(), s)
    return known, custom


def _custom_matcher(custom: dict):
    """One regex that finds any custom skill as a whole word in a job's text."""
    if not custom:
        return None
    alts = sorted((re.escape(c) for c in custom), key=len, reverse=True)
    return re.compile(r"(?<![a-z0-9+#])(" + "|".join(alts) + r")(?![a-z0-9+#])")


def _title_score(p: Profile, job: Job, pcores: list[frozenset], jtitle_norm: str) -> float:
    jcore = set(job.title_core)
    best = 0.0
    for rank, (t, pc) in enumerate(zip(p.titles[:3], pcores)):
        decay = 1.0 if rank == 0 else 0.85
        if " " + t + " " in jtitle_norm:
            best = max(best, 1.0 * decay)
        elif pc:
            overlap = len(pc & jcore) / len(pc)
            best = max(best, overlap * 0.85 * decay)
    if p.family and job.family == p.family:
        best = max(best, 0.5)
    return best


def _experience_score(p: Profile, job: Job) -> float:
    pr = LEVEL_RANK.get(p.level, 2)
    if job.level == "intern" and pr >= 2:
        return 0.15
    if job.req_years:
        gap = job.req_years - p.years
        if gap <= 0:
            if job.req_years_max and p.years > job.req_years_max + 4:
                return 0.7  # far more experience than the range asks for
            return 1.0 if gap > -8 else 0.7
        return 0.75 if gap <= 1 else max(0.05, 1 - gap * 0.22)
    if job.level:
        diff = LEVEL_RANK[job.level] - pr
        if diff <= 0:
            return 1.0 if diff >= -1 else 0.55
        return 0.65 if diff == 1 else 0.25
    return 0.62  # nothing stated: neither a reason to rank up nor to hide


def experience_ok(p: Profile, job: Job) -> bool:
    """The experience gate: False when a job needs clearly more experience than the user has, or is clearly
    too junior for them. Jobs that state nothing always pass (and simply rank lower than clear fits)."""
    yrs = p.years or 0
    ur = LEVEL_RANK.get(p.level, 2)
    lo, hi = job.req_years, job.req_years_max
    if lo is not None:
        if lo > yrs + max(1.5, yrs * 0.35):  # e.g. asks 5+ with 3 years, or 2+ for a fresher
            return False
        if hi is not None and yrs > hi + 5:   # e.g. "1-3 years" for someone with 10
            return False
        if not job.level:
            return True
    if job.level:
        jr = LEVEL_RANK[job.level]
        if job.level == "intern" and ur >= 2:
            return False
        if jr - ur >= 2:                      # entry-level user, senior/lead role
            return False
        if ur - jr >= 2 and lo is None:       # senior user, entry-level role
            return False
    return True


def _years(y: float) -> str:
    return f"{y:g} year{'' if y == 1 else 's'}"


def experience_fit(p: Profile, job: Job) -> dict:
    """Plain-language verdict on experience: good, close, short, over or unknown."""
    yrs = p.years or 0
    have = f"you have about {_years(yrs)}" if yrs else "your résumé shows no dated work experience"
    lo, hi = job.req_years, job.req_years_max
    if lo:
        need = f"{lo}–{hi} years" if hi else f"{lo}+ years"
        if yrs >= lo and (hi is None or yrs <= hi + 2):
            fit = "good"
        elif yrs >= lo:
            fit = "over"
        elif lo - yrs <= 1:
            fit = "close"
        else:
            fit = "short"
        return {"fit": fit, "required": need, "text": f"Asks for {need} of experience; {have}."}
    if job.level:
        diff = LEVEL_RANK[job.level] - LEVEL_RANK.get(p.level, 2)
        role = "An internship" if job.level == "intern" else f"A {job.level}-level role"
        fit = "good" if diff in (0, -1) else "over" if diff < -1 else "close" if diff == 1 else "short"
        return {"fit": fit, "required": job.level, "text": f"{role}; your experience fits {p.level}-level roles."}
    return {"fit": "unknown", "required": "", "text": f"No experience requirement stated; {have}."}


def score_job(p: Profile, pskills: set, custom_re, pvec: dict, pcores, job: Job) -> tuple[float, dict]:
    jskills = job.skills
    custom_hits = set(custom_re.findall(job.haystack())) if custom_re else set()
    if custom_hits:
        jskills = {**jskills, **{c: 1 for c in custom_hits if c not in jskills}}
    matched = [s for s in jskills if s in pskills or s in custom_hits]
    total_w = sum(_skill_weight(s) for s in jskills)
    got_w = sum(_skill_weight(s) for s in matched)
    if total_w:
        skill = 0.55 * (got_w / total_w) + 0.45 * min(got_w / 4.0, 1.0)
    else:
        skill = 0.2
    title = _title_score(p, job, pcores, job.title_norm) if p.titles else None
    text = min(sum(w * job.vec.get(t, 0.0) for t, w in pvec.items()) / 0.30, 1.0)
    exp = _experience_score(p, job)

    if title is None:  # no title found in résumé: lean on skills and text instead
        raw = 0.50 * skill + 0.28 * text + 0.22 * exp
    else:
        raw = 0.36 * skill + 0.30 * title + 0.14 * text + 0.20 * exp
        if title < 0.3 and len(matched) <= 1:
            raw *= 0.55  # different kind of role with almost no shared skills
    hard_total = sum(1 for s in jskills if not nlp.is_soft(s))
    hard_hits = sum(1 for s in matched if not nlp.is_soft(s))
    if hard_total >= 4 and hard_hits == 0:
        raw *= 0.6  # the job is specific about its skills and you have none of them
    # gentle curve so a genuinely strong fit reads in the 80s–90s
    score = round(min(99, 100 * (raw ** 0.8)))
    return score, {"skill": skill, "skill_cover": (got_w / total_w) if total_w else None, "title": title,
                   "text": text, "exp": exp, "matched": matched, "jskills": jskills,
                   "hard_total": hard_total, "hard_hits": hard_hits}


def explain(p: Profile, job: Job, parts: dict, custom: dict) -> dict:
    jskills = parts["jskills"]
    matched = sorted(parts["matched"], key=lambda s: (-jskills.get(s, 0), s.lower()))
    have = set(parts["matched"])
    hard_missing = [s for s, _ in sorted(job.skills.items(), key=lambda kv: -kv[1])
                    if s not in have and not nlp.is_soft(s)][:8]
    reasons = []
    if parts["title"] is not None and parts["title"] >= 0.85:
        reasons.append(f"The job title fits your {p.titles[0]} background")
    elif parts["title"] is not None and parts["title"] >= 0.5:
        reasons.append("Same kind of role as your experience")
    n_job = len([s for s in jskills if not nlp.is_soft(s)])
    n_hit = len([s for s in matched if not nlp.is_soft(s)])
    if n_job:
        reasons.append(f"You have {n_hit} of the {n_job} skills it mentions")
    exp = experience_fit(p, job)
    pct = lambda v: None if v is None else round(100 * v)
    return {"matched_skills": [custom.get(s, s) for s in matched][:40], "missing_skills": hard_missing,
            "reasons": reasons, "experience": exp,
            "breakdown": {"skills": pct(parts["skill_cover"]), "title": pct(parts["title"]), "experience": pct(parts["exp"])}}


def rank(p: Profile, jobs: list[Job], idf: dict, default_idf: float, *, hours: int, top: int,
         location: str = "", remote_only: bool = False, exp_match: bool = True,
         stats: dict | None = None) -> tuple[list[dict], int, dict]:
    """Top matches. exp_match hides jobs whose experience clearly doesn't fit (count in stats['hidden_experience'])."""
    now = time.time()
    cutoff = now - hours * 3600
    hidden_exp = 0
    loc_ok = _location_matcher(location)
    pskills, custom = split_skills(p.skills)
    custom_re = _custom_matcher(custom)
    pvec = nlp.tfidf(p.terms, idf, default_idf)
    pcores = [nlp.title_core(t) for t in p.titles[:3]]

    seen, scored, considered, by_source = set(), [], 0, {}
    for job in jobs:
        if job.posted_at < cutoff or (remote_only and not job.remote):
            continue
        if loc_ok and not loc_ok(job):
            continue
        k = job.key
        if k in seen:
            continue
        seen.add(k)
        considered += 1
        f = feed_name(job.source)
        by_source[f] = by_source.get(f, 0) + 1
        # cheap pre-screen: no shared skill and a different kind of role -> cannot rank well
        if job.family != p.family and pskills.isdisjoint(job.skills) \
                and not (custom_re and custom_re.search(job.haystack())):
            continue
        if exp_match and not experience_ok(p, job):
            hidden_exp += 1
            continue
        s, parts = score_job(p, pskills, custom_re, pvec, pcores, job)
        if parts["hard_total"] >= 4 and parts["hard_hits"] == 0 and (parts["title"] or 0) < 0.85:
            continue  # not a real match: specific skills, none of them yours, and a different title
        # among similar scores, newer postings come first (up to 5 points over a month)
        order = s - min(5.0, (now - job.posted_at) / 86400 / 6)
        scored.append((order, job.posted_at, job, parts, s))

    if stats is not None:
        stats["hidden_experience"] = hidden_exp
    scored.sort(key=lambda x: (-x[0], -x[1]))
    results, per_company = [], {}
    for _, _, job, parts, s in scored:
        c = job.company.lower()
        if per_company.get(c, 0) >= 3:  # keep the list varied
            continue
        per_company[c] = per_company.get(c, 0) + 1
        results.append({**job.public(), "score": s, **explain(p, job, parts, custom)})
        if len(results) >= top:
            break
    return results, considered, dict(sorted(by_source.items(), key=lambda kv: -kv[1]))
