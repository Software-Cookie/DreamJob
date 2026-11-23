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
        if self.titles:
            return self.titles[:1]
        hard = [s for s in self.skills if not nlp.is_soft(s)]
        return hard[:2]

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
    ordered = [s for s, _ in sorted(skills.items(), key=lambda kv: (-kv[1], kv[0]))][:60]
    return Profile(titles=titles, skills=ordered, years=years, level=level,
                   terms=nlp.term_counts(text, 60), family=family, location=nlp.detect_location(text))


# ---------------------------------------------------------------------- scoring
def _skill_weight(s: str) -> float:
    return 0.35 if nlp.is_soft(s) else 1.0


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
            return 1.0 if gap > -8 else 0.7
        return 0.75 if gap <= 1 else max(0.05, 1 - gap * 0.22)
    if job.level:
        diff = LEVEL_RANK[job.level] - pr
        if diff <= 0:
            return 1.0 if diff >= -1 else 0.6
        return 0.7 if diff == 1 else 0.3
    return 0.75


def score_job(p: Profile, pskills: set, pvec: dict, pcores, job: Job) -> tuple[float, dict]:
    jskills = job.skills
    matched = [s for s in jskills if s in pskills]
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
        raw = 0.55 * skill + 0.30 * text + 0.15 * exp
    else:
        raw = 0.38 * skill + 0.32 * title + 0.17 * text + 0.13 * exp
        if title < 0.3 and len(matched) <= 1:
            raw *= 0.55  # different kind of role with almost no shared skills
    # gentle curve so a genuinely strong fit reads in the 80s–90s
    score = round(min(99, 100 * (raw ** 0.8)))
    return score, {"skill": skill, "title": title, "text": text, "exp": exp, "matched": matched}


def explain(p: Profile, job: Job, parts: dict) -> dict:
    matched = sorted(parts["matched"], key=lambda s: (-job.skills.get(s, 0), s))
    hard_missing = [s for s, _ in sorted(job.skills.items(), key=lambda kv: -kv[1])
                    if s not in set(p.skills) and not nlp.is_soft(s)][:5]
    reasons = []
    if parts["title"] is not None and parts["title"] >= 0.85:
        reasons.append(f"The job title fits your {p.titles[0]} background")
    elif parts["title"] is not None and parts["title"] >= 0.5:
        reasons.append("Same kind of role as your experience")
    n_job = len([s for s in job.skills if not nlp.is_soft(s)])
    n_hit = len([s for s in matched if not nlp.is_soft(s)])
    if n_job:
        reasons.append(f"You have {n_hit} of the {n_job} skills it mentions")
    if job.req_years:
        reasons.append(f"Asks for {job.req_years}+ years; you have about {p.years:g}")
    elif job.level and job.level != "mid":
        reasons.append(f"{job.level.capitalize()}-level role")
    return {"matched_skills": matched[:10], "missing_skills": hard_missing, "reasons": reasons}


def rank(p: Profile, jobs: list[Job], idf: dict, default_idf: float, *, hours: int, top: int,
         location: str = "", remote_only: bool = False) -> tuple[list[dict], int, dict]:
    cutoff = time.time() - hours * 3600
    loc_ok = _location_matcher(location)
    pskills = set(p.skills)
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
        if job.family != p.family and pskills.isdisjoint(job.skills):
            continue
        s, parts = score_job(p, pskills, pvec, pcores, job)
        scored.append((s, job.posted_at, job, parts))

    scored.sort(key=lambda x: (-x[0], -x[1]))
    results, per_company = [], {}
    for s, _, job, parts in scored:
        c = job.company.lower()
        if per_company.get(c, 0) >= 3:  # keep the list varied
            continue
        per_company[c] = per_company.get(c, 0) + 1
        results.append({**job.public(), "score": s, **explain(p, job, parts)})
        if len(results) >= top:
            break
    return results, considered, dict(sorted(by_source.items(), key=lambda kv: -kv[1]))
