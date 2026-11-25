"""In-memory job index with background refresh, disk snapshot and a coalescing live-search cache."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import time
from dataclasses import asdict, dataclass, field

import httpx

from . import nlp
from .config import settings
from . import sources
from .sources import FEEDS, live_searches

log = logging.getLogger("dreamjob.index")
MAX_AGE_DAYS = 31
SOURCE_DEADLINE = 600  # seconds; hard cap for one source per refresh (first company-site crawl is the slowest)
SNAPSHOT = settings.data_dir / "jobs_snapshot.json"
SNAPSHOT_VERSION = 3  # 3: full descriptions and experience ranges


@dataclass(slots=True)
class Job:
    id: str
    source: str
    url: str
    title: str
    company: str
    location: str
    remote: bool
    posted_at: float
    salary: str
    job_type: str
    logo: str
    tags: list
    snippet: str
    skills: dict            # canonical skill -> occurrences
    family: str | None
    level: str | None
    req_years: int | None
    title_core: list
    terms: dict             # term -> count (top terms, used for tf-idf)
    vec: dict = field(default_factory=dict)  # tf-idf vector, rebuilt from terms
    title_norm: str = ""    # " senior backend engineer " - precomputed for fast phrase checks
    key: str = ""           # dedupe key
    description: str = ""   # full plain-text description, paragraphs kept
    req_years_max: int | None = None

    def __post_init__(self):
        if not self.title_norm:
            self.title_norm = " " + " ".join(t.lower() for t in nlp.tokens(self.title)) + " "
        if not self.key:
            self.key = re.sub(r"[^a-z0-9]", "", (self.title + "|" + self.company).lower())

    def public(self) -> dict:
        return {k: getattr(self, k) for k in (
            "id", "source", "url", "title", "company", "location", "remote", "posted_at",
            "salary", "job_type", "logo", "snippet", "description", "req_years", "req_years_max", "level")}

    def haystack(self) -> str:
        """Lower-case title, tags and description; searched for skills that are not in the skill list."""
        return f"{self.title}\n{' '.join(self.tags)}\n{self.description}".lower()


def featurize(d: dict) -> Job | None:
    if not d.get("title") or not d.get("url") or not d.get("posted_at"):
        return None  # a job without a trustworthy posting date can't be placed in a time window
    d["posted_at"] = min(float(d["posted_at"]), time.time())  # guard against clock skew at the source
    title, text, tags = d["title"], d.get("text", ""), d.get("tags", [])
    req_lo, req_hi = nlp.required_years(text)
    skills = nlp.extract_skills(f"{title}\n{' , '.join(tags)}\n{text}")
    # skills in the title count extra: they are the core of the role
    for s in nlp.extract_skills(title):
        skills[s] += 2
    return Job(
        id=d["id"], source=d["source"], url=d["url"], title=title, company=d.get("company", ""),
        location=d.get("location", ""), remote=bool(d.get("remote")), posted_at=float(d["posted_at"]),
        salary=d.get("salary", ""), job_type=d.get("job_type", ""), logo=d.get("logo", ""),
        tags=tags[:8], snippet=_snippet(text), skills=dict(skills.most_common(40)),
        family=nlp.title_family(title), level=job_level(title, text, req_lo),
        req_years=req_lo, req_years_max=req_hi, title_core=sorted(nlp.title_core(title)),
        terms=nlp.term_counts(f"{title} {title} {' '.join(tags)} {text}"), description=text,
    )


def job_level(title: str, text: str, req_years: int | None) -> str | None:
    """Seniority from the title; if the title says nothing and no years are stated, from the description's wording."""
    return nlp.level_from_title(title) or (None if req_years else nlp.level_from_text(text))


def _crawler_lock():
    """An exclusive lock on data/crawler.lock, released by the OS when the process exits. None if taken."""
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        f = open(settings.data_dir / "crawler.lock", "a+")
    except OSError:
        return None
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f
    except OSError:
        f.close()
        return None


def _snippet(text: str, n: int = 260) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def dedupe_key(j: Job) -> str:
    return j.key


class JobIndex:
    def __init__(self):
        self.by_source: dict[str, list[Job]] = {}
        self.jobs: list[Job] = []
        self.idf: dict[str, float] = {}
        self.default_idf = 5.0
        self.status: dict[str, dict] = {}
        self.last_refresh: float = 0
        self.refreshing = False
        self._running: set[str] = set()
        self._done_at: dict[str, float] = {}
        self._live: dict[str, tuple[float, list[Job]]] = {}
        self._inflight: dict[str, asyncio.Task] = {}
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        self._lockfile = None   # open file holding the crawler lock (this process crawls)
        self._snap_mtime = 0.0  # snapshot version this process has loaded

    async def _follow_snapshot(self):
        """Non-crawling workers: load the crawler's snapshot whenever it is newer."""
        try:
            mtime = SNAPSHOT.stat().st_mtime
        except OSError:
            return
        if mtime > self._snap_mtime:
            self._snap_mtime = mtime
            await asyncio.to_thread(self._load_snapshot)
        self.refreshing = not self.jobs

    # ------------------------------------------------------------------ lifecycle
    async def start(self):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=15.0), follow_redirects=True,
            headers={"User-Agent": settings.user_agent, "Accept": "application/json"},
            limits=httpx.Limits(max_connections=40, max_keepalive_connections=20),
        )
        try:
            self._snap_mtime = SNAPSHOT.stat().st_mtime
        except OSError:
            pass
        await asyncio.to_thread(self._load_snapshot)

    async def stop(self):
        if self._client:
            await self._client.aclose()

    async def run_forever(self):
        """Background scheduler: each source refreshes on its own interval; slow ones never block others.

        With several worker processes, only one of them (the holder of data/crawler.lock) talks to the
        job sources. The others reload its snapshot when it changes, so each employer API is called once."""
        while True:
            if self._lockfile is None:
                self._lockfile = await asyncio.to_thread(_crawler_lock)
                if self._lockfile is not None:
                    log.info("this worker (pid %s) refreshes the job sources", os.getpid())
            if self._lockfile is None:
                await self._follow_snapshot()
                await asyncio.sleep(30)
                continue
            now = time.time()
            for name, (_fn, minutes) in FEEDS.items():
                due = self._done_at.get(name, 0) + minutes * 60
                if name not in self._running and (now >= due or name not in self.by_source):
                    self._running.add(name)
                    asyncio.create_task(self._refresh_source(name))
            self.refreshing = bool(self._running)
            await asyncio.sleep(20)

    async def refresh(self):
        """Refresh every source now and wait for all of them (used by scripts and tests)."""
        self.refreshing = True
        try:
            await asyncio.gather(*(self._refresh_source(n) for n in FEEDS))
        finally:
            self.refreshing = False

    async def _refresh_source(self, name: str):
        t0 = time.time()
        try:
            raw = await asyncio.wait_for(self._fetch(name), timeout=SOURCE_DEADLINE)
            old = {j.id: j for j in self.by_source.get(name, [])}

            def build():
                out = []
                for d in raw:
                    if d.get("_reuse"):  # unchanged job we already analysed: keep it
                        if d["id"] in old:
                            out.append(old[d["id"]])
                    elif (j := featurize(d)) is not None:
                        out.append(j)
                return out
            jobs = await asyncio.to_thread(build)
            async with self._lock:
                self.by_source[name] = jobs
                self.status[name] = {"ok": True, "count": len(jobs), "checked_at": time.time()}
                await asyncio.to_thread(self._rebuild)
                self.last_refresh = time.time()
                await asyncio.to_thread(self._save_snapshot)
            log.info("source %s: %d jobs in %.1fs (index %d)", name, len(jobs), time.time() - t0, len(self.jobs))
        except Exception as e:  # keep the previous jobs from this source
            log.warning("source %s failed: %r", name, e)
            self.status[name] = {**self.status.get(name, {}), "ok": False,
                                 "error": (str(e) or type(e).__name__)[:200], "checked_at": time.time()}
        finally:
            self._done_at[name] = time.time()
            self._running.discard(name)

    async def _fetch(self, name: str):
        """Fetch one feed, retrying once on a transient network error."""
        fn = FEEDS[name][0]
        try:
            return await fn(self._client)
        except (httpx.TransportError, httpx.HTTPStatusError) as e:
            log.info("retrying %s after %r", name, e)
            await asyncio.sleep(3)
            return await fn(self._client)

    def _rebuild(self):
        cutoff = time.time() - MAX_AGE_DAYS * 86400
        seen, jobs = set(), []
        # FEEDS order = priority: a job found on the employer's own site wins over a board's copy
        for name in FEEDS:
            for j in self.by_source.get(name, []):
                k = dedupe_key(j)
                if j.posted_at >= cutoff and k not in seen:
                    seen.add(k)
                    jobs.append(j)
        jobs.sort(key=lambda j: -j.posted_at)
        df: dict[str, int] = {}
        for j in jobs:
            for t in j.terms:
                df[t] = df.get(t, 0) + 1
        n = max(len(jobs), 1)
        idf = {t: math.log((n + 1) / (c + 0.5)) + 1 for t, c in df.items()}
        self.default_idf = math.log((n + 1) / 0.5) + 1
        for j in jobs:
            j.vec = nlp.tfidf(j.terms, idf, self.default_idf)
        self.idf, self.jobs = idf, jobs
        sources.KNOWN_JOB_IDS = {j.id for j in jobs}

    # ------------------------------------------------------------------ live search
    async def live(self, queries: list[str], window: str, location: str, timeout: float,
                   years: float | None = None, viewer: dict | None = None) -> list[Job]:
        """Run per-role searches; identical concurrent searches share one upstream call."""
        now = time.time()
        out: list[Job] = []
        waits = []
        for q in queries:
            for key, (fn, ttl) in live_searches(q, window, location, years, viewer).items():
                cached = self._live.get(key)
                if cached and cached[0] > now:
                    out.extend(cached[1])
                    continue
                task = self._inflight.get(key)
                if task is None:
                    task = asyncio.create_task(self._run_live(key, fn, ttl))
                    self._inflight[key] = task
                waits.append(task)
        if waits:
            done, _ = await asyncio.wait(waits, timeout=timeout)
            for t in done:
                if not t.cancelled() and t.exception() is None:
                    out.extend(t.result())
        return out

    async def _run_live(self, key, fn, ttl_minutes: int) -> list[Job]:
        try:
            raw = await fn(self._client)
            jobs = await asyncio.to_thread(lambda: [j for j in map(featurize, raw) if j])
            for j in jobs:
                j.vec = nlp.tfidf(j.terms, self.idf, self.default_idf)
            self._live[key] = (time.time() + ttl_minutes * 60, jobs)
            if len(self._live) > 800:  # simple bound on memory
                for k in sorted(self._live, key=lambda k: self._live[k][0])[:200]:
                    self._live.pop(k, None)
            return jobs
        except Exception as e:
            log.warning("live search %s failed: %r", key, e)
            self._live[key] = (time.time() + 120, [])  # brief negative cache
            return []
        finally:
            self._inflight.pop(key, None)

    # ------------------------------------------------------------------ snapshot
    def _save_snapshot(self):
        try:
            settings.data_dir.mkdir(parents=True, exist_ok=True)
            payload = {"version": SNAPSHOT_VERSION, "saved_at": self.last_refresh, "status": self.status,
                       "done_at": self._done_at,
                       "by_source": {s: [{k: v for k, v in asdict(j).items() if k != "vec"} for j in lst]
                                     for s, lst in self.by_source.items()}}
            tmp = SNAPSHOT.with_suffix(f".{os.getpid()}.tmp")  # per process: no clash between workers
            tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            tmp.replace(SNAPSHOT)
        except OSError as e:
            log.warning("could not save snapshot: %s", e)

    def _load_snapshot(self):
        try:
            payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
            if payload.get("version") != SNAPSHOT_VERSION:
                log.info("ignoring snapshot from an older version")
                return
            self.by_source = {s: [Job(**d) for d in lst] for s, lst in payload["by_source"].items() if s in FEEDS}
            for lst in self.by_source.values():  # re-derive experience fields so rule updates apply without a recrawl
                for j in lst:
                    j.req_years, j.req_years_max = nlp.required_years(j.description)
                    j.level = job_level(j.title, j.description, j.req_years)
            self.status = {k: v for k, v in payload.get("status", {}).items() if k in FEEDS}
            self._done_at = {k: v for k, v in payload.get("done_at", {}).items() if k in FEEDS}
            self._rebuild()
            self.last_refresh = payload.get("saved_at", 0)
            log.info("loaded snapshot with %d jobs", len(self.jobs))
        except FileNotFoundError:
            pass
        except Exception as e:
            log.warning("ignoring unreadable snapshot: %s", e)

    def stats(self) -> dict:
        now = time.time()
        windows = {w: sum(1 for j in self.jobs if j.posted_at >= now - h * 3600)
                   for w, h in (("24h", 24), ("48h", 48), ("72h", 72), ("1w", 168), ("1m", 720))}
        return {"jobs": len(self.jobs), "by_window": windows, "last_refresh": self.last_refresh,
                "refreshing": self.refreshing, "sources": self.status}


index = JobIndex()
