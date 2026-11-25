"""Job source connectors. Each returns a list of normalised job dicts.

Key-free sources (always on)
  * Company career boards: ~150 employers via the official public APIs of Greenhouse, Lever,
    Ashby and SmartRecruiters. These give the date the employer first published the job.
  * Remotive, Remote OK, We Work Remotely, Jobicy, Working Nomads, Arbeitnow.

Optional sources (free keys, see .env.example)
  * JSearch (RapidAPI): Google for Jobs results, which include LinkedIn, Indeed, Glassdoor, Naukri
    and company sites. Free plan is about 200 requests a month, so results are cached for hours.
  * Adzuna: on-site jobs in 19 countries including India, US and UK.
  * Jooble: large aggregator with India coverage.

Himalayas was removed on purpose: its dates are re-import dates that can lag the employer's real
publish date by weeks, which broke the 24/48/72-hour filters.
"""
from __future__ import annotations

import asyncio
import html as htmlmod
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from .companies import BOARDS
from .config import settings
from .nlp import strip_html, title_family

log = logging.getLogger("dreamjob.sources")

# window -> (JSearch date_posted, max days old)
DESC_LIMIT = 8000  # characters of description kept per job
WINDOW_DAYS = {"24h": 1, "48h": 2, "72h": 3, "1w": 7, "1m": 31}
JSEARCH_DATE = {"24h": "today", "48h": "3days", "72h": "3days", "1w": "week", "1m": "month"}


def _ts(value) -> float | None:
    """Parse ISO strings, RFC 822 strings or epoch numbers to a UTC epoch float."""
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            v = float(value)
            return v / 1000 if v > 1e12 else v
        s = str(value).strip()
        if s[:3].isalpha() and "," in s[:5]:  # RFC 822: "Mon, 16 Nov 2026 18:32:34 +0000"
            return parsedate_to_datetime(s).timestamp()
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError, IndexError):
        return None


def _salary(lo, hi, cur="") -> str:
    def f(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        if v <= 0:
            return None
        return f"{v/1000:.0f}k" if v >= 1000 else f"{v:.0f}"
    a, b = f(lo), f(hi)
    cur = (cur or "").replace("None", "")
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}.get(cur.upper(), cur + " " if cur else "$")
    if a and b and a != b:
        return f"{sym}{a} – {sym}{b}"
    if a or b:
        return f"{sym}{a or b}"
    return ""


def _job(**kw) -> dict:
    desc = strip_html(kw.pop("description", "") or "", keep_lines=True)
    kw["text"] = desc[:DESC_LIMIT]
    kw["tags"] = [str(t) for t in (kw.get("tags") or []) if t][:20]
    kw["title"] = strip_html(kw.get("title") or "")[:160]
    kw["company"] = strip_html(kw.get("company") or "")[:120]
    loc = strip_html(kw.get("location") or "")
    kw["remote"] = bool(kw.get("remote")) or "remote" in loc.lower()
    kw["location"] = (loc or ("Remote" if kw["remote"] else ""))[:120]
    for k in ("salary", "job_type", "logo"):
        kw.setdefault(k, "")
    jt = str(kw["job_type"] or "")
    kw["job_type"] = {"fulltime": "Full-time", "full time": "Full-time", "full-time": "Full-time", "parttime": "Part-time",
                      "part time": "Part-time", "intern": "Internship", "temporary": "Temporary"}.get(jt.lower().replace("_", " "), jt)
    return kw


async def _get_json(client: httpx.AsyncClient, url: str, timeout: float | None = None, **params):
    kw = {"timeout": httpx.Timeout(timeout, connect=15.0)} if timeout else {}
    r = await client.get(url, params=params or None, **kw)
    r.raise_for_status()
    return r.json()


def _recent(ts: float | None, days: int = 31) -> bool:
    return bool(ts) and ts >= datetime.now(timezone.utc).timestamp() - days * 86400


# =========================================================================== job boards
async def remotive(client, search: str | None = None) -> list[dict]:
    params = {"search": search, "limit": 100} if search else {}
    data = await _get_json(client, "https://remotive.com/api/remote-jobs", **params)
    return [_job(
        id=f"remotive:{j.get('id')}", source="Remotive", url=j.get("url", ""),
        title=j.get("title"), company=j.get("company_name"),
        location=j.get("candidate_required_location") or "Remote", remote=True,
        posted_at=_ts(j.get("publication_date")), salary=j.get("salary") or "",
        tags=j.get("tags") or [], description=j.get("description"),
        job_type=(j.get("job_type") or "").replace("_", " "), logo=j.get("company_logo") or "",
    ) for j in data.get("jobs", [])]


async def remoteok(client) -> list[dict]:
    data = await _get_json(client, "https://remoteok.com/api", timeout=75)  # slow API (~30-60 s)
    return [_job(
        id=f"remoteok:{j.get('id')}", source="Remote OK", url=j.get("url") or j.get("apply_url", ""),
        title=j.get("position"), company=j.get("company"), location=j.get("location") or "Remote",
        remote=True, posted_at=_ts(j.get("epoch") or j.get("date")),
        salary=_salary(j.get("salary_min"), j.get("salary_max"), "USD"),
        tags=j.get("tags") or [], description=j.get("description"), logo=j.get("company_logo") or "",
    ) for j in data if isinstance(j, dict) and "position" in j]  # first element is a legal notice


async def weworkremotely(client) -> list[dict]:
    r = await client.get("https://weworkremotely.com/remote-jobs.rss")
    r.raise_for_status()
    out = []
    for it in ET.fromstring(r.content).findall("./channel/item"):
        raw_title = it.findtext("title") or ""
        company, _, title = raw_title.partition(": ")
        out.append(_job(
            id=f"wwr:{it.findtext('guid')}", source="We Work Remotely", url=it.findtext("link") or "",
            title=title or raw_title, company=company if title else "",
            location=it.findtext("region") or "Remote", remote=True,
            posted_at=_ts(it.findtext("pubDate")), tags=[it.findtext("category") or ""],
            description=it.findtext("description"), job_type=it.findtext("type") or "",
        ))
    return out


async def workingnomads(client) -> list[dict]:
    data = await _get_json(client, "https://www.workingnomads.com/api/exposed_jobs/", timeout=60)
    return [_job(
        id=f"wn:{j.get('url')}", source="Working Nomads", url=j.get("url", ""), title=j.get("title"),
        company=j.get("company_name"), location=j.get("location") or "Remote", remote=True,
        posted_at=_ts(j.get("pub_date")), tags=(j.get("tags") or "").split(",") + [j.get("category_name") or ""],
        description=j.get("description"),
    ) for j in data]


async def arbeitnow(client, pages: int = 8) -> list[dict]:
    async def page(n):
        try:
            return (await _get_json(client, "https://www.arbeitnow.com/api/job-board-api", page=n)).get("data", [])
        except Exception as e:
            log.warning("arbeitnow page %s failed: %s", n, e)
            return []
    rows = [j for chunk in await asyncio.gather(*(page(n) for n in range(1, pages + 1))) for j in chunk]
    return [_job(
        id=f"arbeitnow:{j.get('slug')}", source="Arbeitnow", url=j.get("url", ""),
        title=j.get("title"), company=j.get("company_name"), location=j.get("location"),
        remote=bool(j.get("remote")), posted_at=_ts(j.get("created_at")),
        tags=(j.get("tags") or []), description=j.get("description"),
        job_type=", ".join(j.get("job_types") or [])[:60],
    ) for j in rows]


async def jobicy(client, count: int = 100) -> list[dict]:
    data = await _get_json(client, "https://jobicy.com/api/v2/remote-jobs", count=count)
    return [_job(
        id=f"jobicy:{j.get('id')}", source="Jobicy", url=j.get("url", ""),
        title=j.get("jobTitle"), company=j.get("companyName"), location=j.get("jobGeo") or "Remote",
        remote=True, posted_at=_ts(j.get("pubDate")),
        salary=_salary(j.get("annualSalaryMin") or j.get("salaryMin"), j.get("annualSalaryMax") or j.get("salaryMax"),
                       j.get("salaryCurrency") or "USD"),
        tags=(j.get("jobIndustry") or []) + ([j.get("jobLevel")] if j.get("jobLevel") not in (None, "Any") else []),
        description=j.get("jobDescription") or j.get("jobExcerpt"),
        job_type=", ".join(j.get("jobType") or []), logo=j.get("companyLogo") or "",
    ) for j in data.get("jobs", [])]


# =========================================================================== company career boards
_GH_TEXT: dict[str, str] = {}  # job id -> description HTML, fetched once (descriptions rarely change)
KNOWN_JOB_IDS: set[str] = set()  # ids already in the index; their descriptions are not downloaded again


async def greenhouse(client, slug: str, name: str, sem: asyncio.Semaphore) -> list[dict]:
    data = await _get_json(client, f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    recent = [j for j in data.get("jobs", []) if _recent(_ts(j.get("first_published") or j.get("updated_at")))]

    async def text(j):  # list endpoint has no description; fetch new ones once and cache them
        jid = str(j.get("id"))
        if jid not in _GH_TEXT:
            try:
                async with sem:
                    d = await _get_json(client, f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{jid}")
                _GH_TEXT[jid] = htmlmod.unescape(d.get("content") or "")[:DESC_LIMIT * 2]
            except Exception:
                return ""
        return _GH_TEXT[jid]

    known = [j for j in recent if f"gh:{slug}:{j.get('id')}" in KNOWN_JOB_IDS]
    recent = [j for j in recent if f"gh:{slug}:{j.get('id')}" not in KNOWN_JOB_IDS]
    texts = await asyncio.gather(*(text(j) for j in recent[: settings.board_detail_limit]))
    texts += [""] * (len(recent) - len(texts))
    reuse = [{"id": f"gh:{slug}:{j.get('id')}", "_reuse": True} for j in known]
    return reuse + [_job(
        id=f"gh:{slug}:{j.get('id')}", source=f"{j.get('company_name') or name} careers", url=j.get("absolute_url", ""),
        title=j.get("title"), company=j.get("company_name") or name, location=(j.get("location") or {}).get("name", ""),
        posted_at=_ts(j.get("first_published") or j.get("updated_at")), description=t,
        tags=[d.get("name", "") for d in (j.get("departments") or [])],
    ) for j, t in zip(recent, texts)]


async def lever(client, slug: str, name: str, _sem=None) -> list[dict]:
    data = await _get_json(client, f"https://api.lever.co/v0/postings/{slug}", mode="json", limit=300)
    out = []
    for j in data if isinstance(data, list) else []:
        posted = _ts(j.get("createdAt"))
        if not _recent(posted):
            continue
        cat = j.get("categories") or {}
        lists = "".join(f"<h3>{l.get('text','')}</h3><ul>{l.get('content','')}</ul>" for l in (j.get("lists") or []))
        out.append(_job(
            id=f"lever:{slug}:{j.get('id')}", source=f"{name} careers", url=j.get("hostedUrl", ""),
            title=j.get("text"), company=name, location=cat.get("location") or ", ".join(cat.get("allLocations") or []),
            remote=(j.get("workplaceType") == "remote"), posted_at=posted,
            description=f"{j.get('description') or j.get('descriptionPlain','')}{lists}<p>{j.get('additional') or j.get('additionalPlain','')}</p>",
            tags=[cat.get("team", ""), cat.get("department", "")], job_type=cat.get("commitment") or "",
        ))
    return out


async def ashby(client, slug: str, name: str, _sem=None) -> list[dict]:
    data = await _get_json(client, f"https://api.ashbyhq.com/posting-api/job-board/{slug}", timeout=60)
    out = []
    for j in data.get("jobs", []):
        posted = _ts(j.get("publishedAt"))
        if not _recent(posted) or j.get("isListed") is False:
            continue
        locs = [j.get("location") or ""] + [s.get("location", "") for s in (j.get("secondaryLocations") or [])]
        out.append(_job(
            id=f"ashby:{slug}:{j.get('id')}", source=f"{name} careers", url=j.get("jobUrl") or j.get("applyUrl", ""),
            title=j.get("title"), company=name, location=", ".join(l for l in locs if l)[:120],
            remote=bool(j.get("isRemote")) or j.get("workplaceType") == "Remote", posted_at=posted,
            description=j.get("descriptionHtml") or j.get("descriptionPlain") or "",
            tags=[j.get("department", ""), j.get("team", "")], job_type=j.get("employmentType") or "",
        ))
    return out


async def _sr_description(client, company_id: str, pid: str, sem: asyncio.Semaphore) -> str:
    key = f"sr:{company_id}:{pid}"
    if key not in _GH_TEXT:
        try:
            async with sem:
                d = await _get_json(client, f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings/{pid}")
        except Exception:
            return ""
        secs = (d.get("jobAd") or {}).get("sections") or {}
        parts = []
        for k in ("jobDescription", "qualifications", "additionalInformation", "companyDescription"):
            sec = secs.get(k) or {}
            if sec.get("text"):
                parts.append(f"<h3>{sec.get('title') or ''}</h3>{sec['text']}")
        _GH_TEXT[key] = "".join(parts)[:DESC_LIMIT * 2]
    return _GH_TEXT[key]


async def smartrecruiters(client, company_id: str, name: str, sem=None) -> list[dict]:
    async def fetch(country=None):
        params = {"limit": 100}
        if country:
            params["country"] = country
        return (await _get_json(client, f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings", **params)).get("content", [])
    batches = await asyncio.gather(fetch(), *(fetch(c) for c in settings.board_countries), return_exceptions=True)
    seen, out = set(), []
    for batch in batches:
        if isinstance(batch, Exception):
            continue
        for j in batch:
            posted = _ts(j.get("releasedDate"))
            if j.get("id") in seen or not _recent(posted):
                continue
            seen.add(j.get("id"))
            if f"sr:{company_id}:{j.get('id')}" in KNOWN_JOB_IDS:
                out.append({"id": f"sr:{company_id}:{j.get('id')}", "_reuse": True})
                continue
            loc = j.get("location") or {}
            parts = [j.get("name", ""), (j.get("function") or {}).get("label", ""), (j.get("industry") or {}).get("label", ""),
                     (j.get("experienceLevel") or {}).get("label", ""), (j.get("department") or {}).get("label", "")]
            out.append(_job(
                id=f"sr:{company_id}:{j.get('id')}", source=f"{name} careers",
                url=f"https://jobs.smartrecruiters.com/{company_id}/{j.get('id')}",
                title=j.get("name"), company=(j.get("company") or {}).get("name") or name,
                location=loc.get("fullLocation") or ", ".join(x for x in (loc.get("city"), loc.get("country", "").upper()) if x),
                remote=bool(loc.get("remote")), posted_at=posted, description=" . ".join(p for p in parts if p),
                job_type=(j.get("typeOfEmployment") or {}).get("label", ""), _pid=j.get("id"),
            ))
    # descriptions are a second request per job: fetch them for new jobs only, up to the limit
    new = [d for d in out if not d.get("_reuse")][: settings.board_detail_limit]
    if sem is not None and new:
        texts = await asyncio.gather(*(_sr_description(client, company_id, d["_pid"], sem) for d in new))
        for d, t in zip(new, texts):
            if t:
                d["text"] = strip_html(t, keep_lines=True)[:DESC_LIMIT]
    for d in out:
        d.pop("_pid", None)
    return out


# =========================================================================== Hacker News "Who is hiring?"
_HN_LOC = re.compile(r"(?i)\b(remote|onsite|on-site|hybrid|in[- ]office)\b")
_HN_PAY = re.compile(r"[$€£₹]\s?\d|\d+\s?k\b|\blpa\b|salary|equity", re.I)


def _hn_job(c: dict) -> dict | None:
    raw = c.get("comment_text") or ""
    text = strip_html(raw, keep_lines=True)
    first = text.split("\n", 1)[0]
    segs = [x.strip() for x in re.split(r"\s+\|\s+|\s*\|\s*", first) if x.strip()]
    if len(segs) < 3 or len(first) > 400:
        return None  # not in the "Company | Role | Location" format the thread asks for
    company = re.sub(r"\s*\(.*?\)\s*", " ", segs[0]).strip()[:80]
    title = next((x for x in segs[1:] if title_family(x) and not _HN_LOC.fullmatch(x)), "")
    if not company or not title:
        return None
    location = ", ".join(x for x in segs[1:] if x != title and (_HN_LOC.search(x) or len(x.split()) <= 4 and x[:1].isupper()
                                                                and not _HN_PAY.search(x) and not title_family(x)))[:120]
    salary = next((x for x in segs[1:] if _HN_PAY.search(x) and x != title), "")[:60]
    return _job(
        id=f"hn:{c.get('objectID')}", source="Hacker News", url=f"https://news.ycombinator.com/item?id={c.get('objectID')}",
        title=title[:160], company=company, location=location or "See description",
        remote=bool(re.search(r"(?i)\bremote\b", first)), posted_at=_ts(c.get("created_at_i")),
        salary=salary, description=raw, tags=["Hacker News"],
    )


async def hn_hiring(client) -> list[dict]:
    """Top-level posts from the last two monthly 'Ask HN: Who is hiring?' threads (public Algolia API)."""
    hits = (await _get_json(client, "https://hn.algolia.com/api/v1/search_by_date",
                            tags="story,author_whoishiring", hitsPerPage=10)).get("hits", [])
    threads = [h["objectID"] for h in hits if "who is hiring" in (h.get("title") or "").lower()][:2]
    out = []
    for sid in threads:
        page, pages = 0, 1
        while page < min(pages, 4):
            d = await _get_json(client, "https://hn.algolia.com/api/v1/search_by_date",
                                tags=f"comment,story_{sid}", hitsPerPage=1000, page=page)
            pages = d.get("nbPages", 1)
            for c in d.get("hits", []):
                if str(c.get("parent_id")) == str(sid) and (j := _hn_job(c)):
                    out.append(j)
            page += 1
    return out


_ATS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "smartrecruiters": smartrecruiters}
_ID_PREFIX = {"greenhouse": "gh", "lever": "lever", "ashby": "ashby", "smartrecruiters": "sr"}


async def company_boards(client) -> list[dict]:
    """All configured company boards, a few at a time. One failing board never fails the rest,
    and a board that fails keeps the jobs it had, so a short outage doesn't empty it for an hour."""
    sem = asyncio.Semaphore(6)        # concurrent boards
    detail_sem = asyncio.Semaphore(6)  # concurrent description requests

    async def one(kind, slug, name):
        async with sem:
            for attempt in (1, 2):
                try:
                    return await _ATS[kind](client, slug, name, detail_sem)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt == 1:
                        await asyncio.sleep(10)  # rate limited: back off once, politely
                        continue
                    err = e
                except Exception as e:
                    err = e
                break
            log.info("board %s/%s failed: %r", kind, slug, err)
            prefix = f"{_ID_PREFIX[kind]}:{slug}:"
            return [{"id": i, "_reuse": True} for i in KNOWN_JOB_IDS if i.startswith(prefix)]
    results = await asyncio.gather(*(one(*b) for b in BOARDS))
    return [j for lst in results for j in lst]


# =========================================================================== optional keyed sources
def jsearch_experience(years: float | None) -> str:
    """JSearch's own experience filter, so the portals return roles at the right level."""
    if years is None:
        return ""
    if years < 1:
        return "no_experience,under_3_years_experience"
    return "under_3_years_experience" if years < 3 else "more_than_3_years_experience"


async def jsearch(client, q: str, window: str, location: str, years: float | None = None) -> list[dict]:
    """Google for Jobs via JSearch: LinkedIn, Naukri, foundit (Monster), Indeed, Glassdoor, company sites..."""
    if not settings.jsearch_key:
        return []
    where = location or settings.default_country_name
    params = {"query": f"{q} jobs in {where}" if where else f"{q} jobs", "page": 1, "num_pages": settings.jsearch_pages,
              "date_posted": JSEARCH_DATE.get(window, "month"), "country": settings.default_country}
    if jsearch_experience(years):
        params["job_requirements"] = jsearch_experience(years)
    r = await client.get("https://jsearch.p.rapidapi.com/search", params=params, headers={"X-RapidAPI-Key": settings.jsearch_key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"})
    r.raise_for_status()
    out = []
    for j in r.json().get("data", []) or []:
        loc = j.get("job_location") or ", ".join(x for x in (j.get("job_city"), j.get("job_state"), j.get("job_country")) if x)
        out.append(_job(
            id=f"jsearch:{j.get('job_id')}", source=j.get("job_publisher") or "Google Jobs",
            url=j.get("job_apply_link") or j.get("job_google_link") or "", title=j.get("job_title"),
            company=j.get("employer_name"), location=loc, remote=bool(j.get("job_is_remote")),
            posted_at=_ts(j.get("job_posted_at_timestamp") or j.get("job_posted_at_datetime_utc")),
            salary=_salary(j.get("job_min_salary"), j.get("job_max_salary"), j.get("job_salary_currency") or ""),
            description=j.get("job_description"), job_type=j.get("job_employment_type") or "",
            logo=j.get("employer_logo") or "",
        ))
    return out


async def adzuna(client, q: str, window: str, location: str) -> list[dict]:
    if not (settings.adzuna_app_id and settings.adzuna_app_key):
        return []
    params = dict(app_id=settings.adzuna_app_id, app_key=settings.adzuna_app_key, what=q,
                  results_per_page=50, max_days_old=WINDOW_DAYS.get(window, 31), sort_by="date")
    if location and location.lower() not in ("remote", "anywhere", "worldwide"):
        params["where"] = location
    data = await _get_json(client, f"https://api.adzuna.com/v1/api/jobs/{settings.adzuna_country}/search/1", **params)
    cur = {"in": "INR", "gb": "GBP", "de": "EUR", "fr": "EUR", "nl": "EUR"}.get(settings.adzuna_country, "USD")
    return [_job(
        id=f"adzuna:{j.get('id')}", source="Adzuna", url=j.get("redirect_url", ""),
        title=j.get("title"), company=(j.get("company") or {}).get("display_name"),
        location=(j.get("location") or {}).get("display_name"),
        remote="remote" in f"{j.get('title','')} {j.get('description','')}".lower(),
        posted_at=_ts(j.get("created")), salary=_salary(j.get("salary_min"), j.get("salary_max"), cur),
        tags=[(j.get("category") or {}).get("label", "")], description=j.get("description"),
        job_type=(j.get("contract_time") or "").replace("_", " "),
    ) for j in data.get("results", [])]


async def jooble(client, q: str, window: str, location: str) -> list[dict]:
    if not settings.jooble_key:
        return []
    since = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - WINDOW_DAYS.get(window, 31) * 86400, timezone.utc)
    r = await client.post(f"https://{settings.jooble_host}/api/{settings.jooble_key}", json={
        "keywords": q, "location": location or settings.default_country_name or "",
        "page": "1", "ResultOnPage": "50", "datecreatedfrom": since.strftime("%Y-%m-%d"),
    })
    r.raise_for_status()
    return [_job(
        id=f"jooble:{j.get('id')}", source=f"{j.get('source') or 'Jooble'}".strip(), url=j.get("link", ""),
        title=j.get("title"), company=j.get("company"), location=j.get("location"),
        posted_at=_ts(j.get("updated")), salary=j.get("salary") or "", description=j.get("snippet"),
        job_type=j.get("type") or "",
    ) for j in (r.json().get("jobs") or [])]


# =========================================================================== registry
# name -> (fetch function, refresh interval in minutes)
FEEDS = {
    "Company career sites": (company_boards, settings.board_refresh_minutes),
    "Remotive": (lambda c: remotive(c), settings.refresh_minutes),
    "Remote OK": (lambda c: remoteok(c), settings.refresh_minutes),
    "We Work Remotely": (lambda c: weworkremotely(c), settings.refresh_minutes),
    "Jobicy": (lambda c: jobicy(c), settings.refresh_minutes),
    "Working Nomads": (lambda c: workingnomads(c), settings.refresh_minutes),
    "Arbeitnow": (lambda c: arbeitnow(c, pages=settings.arbeitnow_pages), settings.refresh_minutes),
    "Hacker News": (hn_hiring, 120),
}


async def careerjet(client, q: str, window: str, location: str, viewer: dict | None = None) -> list[dict]:
    """Careerjet Job Search API v4: aggregates Indian and global job sites. Free publisher key."""
    if not settings.careerjet_key:
        return []
    viewer = viewer or {}
    params = {"keywords": q, "locale_code": settings.careerjet_locale, "sort": "date", "page_size": 100,
              "fragment_size": 600, "user_ip": viewer.get("ip") or "127.0.0.1",
              "user_agent": viewer.get("ua") or "Mozilla/5.0"}
    if location and location.lower() not in ("remote", "anywhere", "worldwide"):
        params["location"] = location
    r = await client.get("https://search.api.careerjet.net/v4/query", params=params, auth=(settings.careerjet_key, ""),
                         headers={"Referer": (settings.site_url or "https://dreamjob.app") + "/"})
    r.raise_for_status()
    data = r.json()
    cutoff = datetime.now(timezone.utc).timestamp() - WINDOW_DAYS.get(window, 31) * 86400
    out = []
    for j in data.get("jobs", []) if data.get("type") == "JOBS" else []:
        posted = _ts(re.sub(r",(?=\S)", ", ", j.get("date") or ""))  # "Wed,15 Nov 2025 ..." -> "Wed, 15 Nov 2025 ..."
        if not posted or posted < cutoff:
            continue
        out.append(_job(
            id=f"careerjet:{j.get('url')}", source="Careerjet", url=j.get("url", ""), title=j.get("title"),
            company=j.get("company"), location=j.get("locations") or "", posted_at=posted,
            salary=j.get("salary") or "", description=j.get("description"),
        ))
    return out


def live_searches(query: str, window: str, location: str, years: float | None = None, viewer: dict | None = None) -> dict:
    """Searches run at request time for the user's role. Keys are cache keys."""
    q, loc = query.strip().lower(), (location or "").strip().lower()
    searches = {f"remotive|{q}": (lambda c: remotive(c, search=query), settings.live_cache_minutes)}
    if settings.jsearch_key:  # small free quota: cache longer, per window and experience band
        band = jsearch_experience(years)
        searches[f"jsearch|{q}|{window}|{loc}|{band}"] = (lambda c: jsearch(c, query, window, location, years),
                                                          settings.jsearch_cache_minutes)
    if settings.careerjet_key:
        searches[f"careerjet|{q}|{window}|{loc}"] = (lambda c: careerjet(c, query, window, location, viewer),
                                                     settings.live_cache_minutes)
    if settings.adzuna_app_id and settings.adzuna_app_key:
        searches[f"adzuna|{q}|{window}|{loc}"] = (lambda c: adzuna(c, query, window, location), settings.live_cache_minutes)
    if settings.jooble_key:
        searches[f"jooble|{q}|{window}|{loc}"] = (lambda c: jooble(c, query, window, location), settings.live_cache_minutes)
    return searches


def enabled_sources() -> list[str]:
    names = list(FEEDS)
    if settings.jsearch_key:
        names.append("LinkedIn, Indeed & more (JSearch)")
    if settings.adzuna_app_id and settings.adzuna_app_key:
        names.append("Adzuna")
    if settings.jooble_key:
        names.append("Jooble")
    if settings.careerjet_key:
        names.append("Careerjet")
    return names


def live_portals() -> list[str]:
    """Names shown while a search runs."""
    names = []
    if settings.jsearch_key:
        names += ["LinkedIn", "Naukri", "Indeed", "foundit (Monster)", "Glassdoor"]
    if settings.careerjet_key:
        names.append("Careerjet")
    if settings.jooble_key:
        names.append("Jooble")
    if settings.adzuna_app_id and settings.adzuna_app_key:
        names.append("Adzuna")
    return names
