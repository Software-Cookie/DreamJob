"""DreamJob API + static frontend."""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

from . import nlp
from .config import settings
from .index import index
from .companies import BOARDS
from .matcher import Profile, ResumeError, build_profile, rank, read_resume
from .sources import enabled_sources

# Some OSes (notably Windows) map .js to text/plain; browsers then refuse to run it.
for _ext, _type in {".js": "application/javascript", ".css": "text/css", ".svg": "image/svg+xml"}.items():
    mimetypes.add_type(_type, _ext)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("dreamjob")
STATIC = Path(__file__).resolve().parent.parent / "static"

HOURS = {"24h": 24, "48h": 48, "72h": 72, "1w": 168, "1m": 720}
TOPS = {3, 10, 20, 30}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await index.start()
    task = asyncio.create_task(index.run_forever())
    yield
    task.cancel()
    await index.stop()


app = FastAPI(title="DreamJob", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
app.add_middleware(GZipMiddleware, minimum_size=800)
if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------- rate limiting
_hits: dict[str, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    # Take the address appended by our own proxy (counted from the right); the left-most
    # entries are client-supplied and could be spoofed to dodge the rate limit.
    fwd = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if fwd:
        return fwd[-min(settings.trusted_proxy_hops, len(fwd))]
    return request.client.host if request.client else "?"


def _check_rate(request: Request):
    now = time.monotonic()
    q = _hits[_client_ip(request)]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= settings.rate_limit_per_minute:
        raise HTTPException(429, "Too many searches in a minute. Wait a moment and try again.")
    q.append(now)
    if len(_hits) > 20000:
        _hits.clear()


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.url.path.startswith("/static/"):
        resp.headers.setdefault("Cache-Control", "public, max-age=3600")
    return resp


# ---------------------------------------------------------------------- models
class ProfileIn(BaseModel):
    titles: list[str] = Field(default_factory=list, max_length=6)
    skills: list[str] = Field(default_factory=list, max_length=80)
    years: float = Field(0, ge=0, le=50)
    level: str | None = None
    terms: dict[str, int] = Field(default_factory=dict)
    location: str = Field("", max_length=80)

    @field_validator("titles")
    @classmethod
    def _titles(cls, v):
        return [" ".join(t.lower() for t in nlp.tokens(x))[:80] for x in v if x and x.strip()][:6]

    @field_validator("skills")
    @classmethod
    def _skills(cls, v):
        return [s.strip()[:60] for s in v if s and s.strip()]

    @field_validator("terms")
    @classmethod
    def _terms(cls, v):
        return {k[:40]: max(1, min(int(c), 50)) for k, c in list(v.items())[:80]}

    def to_profile(self) -> Profile:
        level = self.level if self.level in nlp.LEVELS else nlp.level_from_years(self.years)
        fam = nlp.title_family(self.titles[0]) if self.titles else None
        return Profile(titles=self.titles, skills=self.skills, years=self.years, level=level,
                       terms=self.terms, family=fam, location=self.location)


class MatchIn(BaseModel):
    profile: ProfileIn
    window: Literal["24h", "48h", "72h", "1w", "1m"] = "1w"
    top: int = 10
    location: str = Field("", max_length=80)
    remote_only: bool = False


# ---------------------------------------------------------------------- core
async def _match(profile: Profile, window: str, top: int, location: str, remote_only: bool) -> dict:
    if top not in TOPS:
        raise HTTPException(422, "top must be 3, 10, 20 or 30")
    t0 = time.perf_counter()
    if not index.jobs and index.refreshing:
        # first boot with no snapshot: wait briefly for the initial crawl
        for _ in range(40):
            if index.jobs:
                break
            await asyncio.sleep(0.5)
    live = (await index.live(profile.queries, window, location, settings.live_search_timeout)
            if profile.queries else [])
    pool = index.jobs + live  # index first: on duplicates, the employer's own posting wins
    results, considered, by_source = await run_in_threadpool(
        rank, profile, pool, index.idf, index.default_idf,
        hours=HOURS[window], top=top, location=location, remote_only=remote_only)
    return {"profile": profile.public(), "results": results, "considered": considered,
            "by_source": by_source, "window": window, "top": top, "location": location,
            "remote_only": remote_only, "took_ms": round((time.perf_counter() - t0) * 1000),
            "index": {"jobs": len(index.jobs), "last_refresh": index.last_refresh}}


@app.post("/api/analyze")
async def analyze(request: Request,
                  file: UploadFile | None = File(None),
                  text: str = Form(""),
                  window: Literal["24h", "48h", "72h", "1w", "1m"] = Form("1w"),
                  top: int = Form(10),
                  location: str = Form("", max_length=80),
                  remote_only: bool = Form(False)):
    """Upload a résumé (PDF/DOCX/TXT) or paste text; returns the parsed profile and ranked jobs."""
    _check_rate(request)
    if file is not None and file.filename:
        data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if len(data) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"The file is larger than {settings.max_upload_mb} MB. Upload a smaller file.")
        try:
            resume_text = await run_in_threadpool(read_resume, file.filename, data)
        except ResumeError as e:
            raise HTTPException(422, str(e))
    elif len(text.strip()) >= 80:
        resume_text = text[:60000]
    else:
        raise HTTPException(422, "Add your résumé: upload a file or paste at least a few lines of text.")
    profile = await run_in_threadpool(build_profile, resume_text)
    return await _match(profile, window, top, location, remote_only)


@app.post("/api/match")
async def match(body: MatchIn, request: Request):
    """Re-rank with an edited profile (no re-upload needed)."""
    _check_rate(request)
    return await _match(body.profile.to_profile(), body.window, body.top, body.location, body.remote_only)


@app.get("/api/stats")
async def stats():
    return {**index.stats(), "enabled": enabled_sources(), "companies": len(BOARDS)}


@app.get("/api/health")
async def health():
    return {"status": "ok", "jobs": len(index.jobs)}


@app.get("/api/skills")
async def skills():
    return {"skills": nlp.ALL_SKILLS}


@app.exception_handler(HTTPException)
async def http_error(_req: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
async def home():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(STATIC / "favicon.svg", media_type="image/svg+xml")
