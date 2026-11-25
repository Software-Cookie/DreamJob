"""DreamJob API + static frontend."""
from __future__ import annotations

import asyncio
import html
import io
import logging
import mimetypes
import time
import zipfile
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

from . import __version__, auth, nlp, payments
from .companies import BOARDS
from .config import settings
from .index import index
from .matcher import Profile, ResumeError, build_profile, rank, read_resume
from .sources import enabled_sources, live_portals

# Some OSes (notably Windows) map .js to text/plain; browsers then refuse to run it.
for _ext, _type in {".js": "application/javascript", ".css": "text/css", ".svg": "image/svg+xml"}.items():
    mimetypes.add_type(_type, _ext)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("dreamjob")
ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
EXTENSION = ROOT / "extension"

HOURS = {"24h": 24, "48h": 48, "72h": 72, "1w": 168, "1m": 720}
TOPS = {3, 10, 20, 30}
MAX_SKILLS = 300

# Razorpay Checkout runs in an iframe from *.razorpay.com; everything else is served by DreamJob itself.
CSP = ("default-src 'self'; script-src 'self' https://checkout.razorpay.com https://*.razorpay.com; "
       "frame-src https://api.razorpay.com https://*.razorpay.com; connect-src 'self' https://*.razorpay.com; "
       "img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; object-src 'none'; "
       "base-uri 'self'; form-action 'self' https://api.razorpay.com; frame-ancestors 'none'")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await index.start()
    task = asyncio.create_task(index.run_forever())
    if payments.enabled():
        log.info("payments on (Razorpay %s mode), Pro: INR %s for %s days",
                 "live" if settings.razorpay_key_id.startswith("rzp_live") else "test",
                 settings.pro_price_inr, settings.pro_days)
    yield
    task.cancel()
    await index.stop()


app = FastAPI(title="DreamJob", version=__version__, lifespan=lifespan,
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
app.add_middleware(GZipMiddleware, minimum_size=800)
if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type", "X-DreamJob-Pass"])


# ---------------------------------------------------------------------- rate limiting
_hits: dict[str, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    # Take the address appended by our own proxy (counted from the right); the left-most
    # entries are client-supplied and could be spoofed to dodge the rate limit.
    fwd = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if fwd:
        return fwd[-min(settings.trusted_proxy_hops, len(fwd))]
    return request.client.host if request.client else "?"


def _check_rate(request: Request, bucket: str = "search", limit: int | None = None):
    now = time.monotonic()
    q = _hits[f"{bucket}|{_client_ip(request)}"]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= (limit or settings.rate_limit_per_minute):
        raise HTTPException(429, "Too many requests in a minute. Wait a moment and try again.")
    q.append(now)
    if len(_hits) > 20000:
        _hits.clear()


def _viewer(request: Request) -> dict:
    """The visitor's IP and browser, which some partner APIs (Careerjet) require with each search."""
    return {"ip": _client_ip(request), "ua": request.headers.get("user-agent", "")[:300]}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    h = resp.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(self \"https://api.razorpay.com\")")
    h.setdefault("Strict-Transport-Security", "max-age=31536000")
    if h.get("content-type", "").startswith("text/html"):
        h.setdefault("Content-Security-Policy", CSP)
    if request.url.path.startswith("/static/"):
        h.setdefault("Cache-Control", "public, max-age=3600")
    elif request.url.path.startswith(("/api/", "/auth/")):
        h.setdefault("Cache-Control", "no-store")
    return resp


# ---------------------------------------------------------------------- models
class ProfileIn(BaseModel):
    titles: list[str] = Field(default_factory=list, max_length=6)
    skills: list[str] = Field(default_factory=list, max_length=MAX_SKILLS)
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
        out, seen = [], set()
        for s in v:
            s = " ".join((s or "").split())[:60]
            if s and s.lower() not in seen:
                seen.add(s.lower())
                out.append(s)
        return out

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
    exp_match: bool = True


class VerifyIn(BaseModel):
    razorpay_order_id: str = Field(..., min_length=6, max_length=64, pattern=r"^order_[A-Za-z0-9]+$")
    razorpay_payment_id: str = Field(..., min_length=6, max_length=64, pattern=r"^pay_[A-Za-z0-9]+$")
    razorpay_signature: str = Field(..., min_length=10, max_length=256, pattern=r"^[a-f0-9]+$")


class RestoreIn(BaseModel):
    payment_id: str = Field(..., min_length=6, max_length=64, pattern=r"^pay_[A-Za-z0-9]+$")
    email: str = Field(..., min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------- core
def _require_login(request: Request):
    if settings.auth_required and auth.enabled() and not auth.current_user(request):
        raise HTTPException(401, "Sign in to see your matches.")


async def _require_pro(top: int, request: Request):
    if not payments.enabled() or top not in settings.pro_tops:
        return
    if not await payments.check_pass(request.headers.get("x-dreamjob-pass")):
        tops = " and ".join(f"Top {t}" for t in sorted(settings.pro_tops))
        raise HTTPException(402, f"{tops} are part of DreamJob Pro.")


async def _read_upload(file: UploadFile | None, text: str) -> str:
    if file is not None and file.filename:
        data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if len(data) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"The file is larger than {settings.max_upload_mb} MB. Upload a smaller file.")
        try:
            return await run_in_threadpool(read_resume, file.filename, data)
        except ResumeError as e:
            raise HTTPException(422, str(e))
    if len(text.strip()) >= 80:
        return text[:60000]
    raise HTTPException(422, "Add your résumé: upload a file or paste at least a few lines of text.")


async def _match(profile: Profile, window: str, top: int, location: str, remote_only: bool, exp_match: bool = True,
                 viewer: dict | None = None) -> dict:
    if top not in TOPS:
        raise HTTPException(422, "top must be 3, 10, 20 or 30")
    t0 = time.perf_counter()
    if not index.jobs and index.refreshing:
        # first boot with no snapshot: wait briefly for the initial crawl
        for _ in range(40):
            if index.jobs:
                break
            await asyncio.sleep(0.5)
    # deep search: several searches per résumé on every connected portal; identical searches are shared and cached
    queries = profile.search_queries(settings.deep_queries)
    timeout = settings.deep_search_timeout if live_portals() else settings.live_search_timeout
    live = (await index.live(queries, window, location, timeout, years=profile.years, viewer=viewer)
            if queries else [])
    pool = index.jobs + live  # index first: on duplicates, the employer's own posting wins
    stats: dict = {}
    results, considered, by_source = await run_in_threadpool(
        lambda: rank(profile, pool, index.idf, index.default_idf, hours=HOURS[window], top=top,
                     location=location, remote_only=remote_only, exp_match=exp_match, stats=stats))
    return {"profile": profile.public(), "results": results, "considered": considered,
            "by_source": by_source, "window": window, "top": top, "location": location,
            "remote_only": remote_only, "exp_match": exp_match,
            "hidden_experience": stats.get("hidden_experience", 0), "took_ms": round((time.perf_counter() - t0) * 1000),
            "index": {"jobs": len(index.jobs), "last_refresh": index.last_refresh}}


@app.post("/api/analyze")
async def analyze(request: Request,
                  file: UploadFile | None = File(None),
                  text: str = Form(""),
                  window: Literal["24h", "48h", "72h", "1w", "1m"] = Form("1w"),
                  top: int = Form(10),
                  location: str = Form("", max_length=80),
                  remote_only: bool = Form(False),
                  exp_match: bool = Form(True)):
    """Upload a résumé (PDF/DOCX/TXT) or paste text; returns the parsed profile and ranked jobs."""
    _check_rate(request)
    _require_login(request)
    await _require_pro(top, request)
    resume_text = await _read_upload(file, text)
    profile = await run_in_threadpool(build_profile, resume_text)
    return await _match(profile, window, top, location, remote_only, exp_match, _viewer(request))


@app.post("/api/match")
async def match(body: MatchIn, request: Request):
    """Re-rank with an edited profile (no re-upload needed)."""
    _check_rate(request)
    _require_login(request)
    await _require_pro(body.top, request)
    return await _match(body.profile.to_profile(), body.window, body.top, body.location, body.remote_only, body.exp_match,
                        _viewer(request))


@app.post("/api/profile/extract")
async def profile_extract(request: Request, file: UploadFile | None = File(None), text: str = Form("")):
    """Contact details, work history, education and skills from a résumé, for the autofill extension.
    Nothing is stored: the file is read in memory and discarded."""
    _check_rate(request, "extract", 10)
    resume_text = await _read_upload(file, text)

    def work():
        p = build_profile(resume_text)
        jobs, schools = nlp.extract_history(resume_text)
        return {"contact": nlp.extract_contact(resume_text), "experience": jobs, "education": schools,
                "skills": p.skills, "titles": p.titles, "years": p.years, "location": p.location}
    return await run_in_threadpool(work)


# ---------------------------------------------------------------------- sign-in
class EmailStartIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    next: str = Field("/", max_length=300)


@app.get("/api/auth/me")
async def auth_me(request: Request):
    return {"user": auth.current_user(request), **auth.public_config()}


@app.post("/api/auth/email/start")
async def auth_email_start(body: EmailStartIn, request: Request):
    """Emails a one-time sign-in link. The answer is the same whether or not the address has signed in before."""
    _check_rate(request, "auth", 5)
    if not auth.email_enabled():
        raise HTTPException(404, "Email sign-in is not set up on this site.")
    email = auth.normalise_email(body.email)
    base = auth.base_url(request)
    auth.check_send_quota(email)
    subject, text, html_body = auth.link_email(f"{base}/auth/email/verify?token={auth.link_token(email, body.next)}")
    try:
        await run_in_threadpool(auth.send_mail, email, subject, text, html_body)
    except Exception as e:
        log.warning("sign-in email to a %s address failed: %r", email.split("@")[-1], e)
        raise HTTPException(503, "We couldn't send the email right now. Try again in a minute.")
    return {"ok": True, "message": f"Check your inbox. We sent a sign-in link that expires in {auth.LINK_MINUTES} minutes."}


@app.get("/auth/email/verify", include_in_schema=False)
async def auth_email_confirm(token: str = ""):
    """Shows a confirm button: mail scanners that open links automatically can't use the link up."""
    data = auth.unsign("email-link", token)
    if not data:
        return RedirectResponse("/?auth_error=link_expired", 303)
    page = auth.CONFIRM_PAGE.format(name=html.escape(settings.business_name), email=html.escape(data["email"]),
                                    token=html.escape(token))
    return HTMLResponse(page, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@app.post("/auth/email/verify", include_in_schema=False)
async def auth_email_verify(request: Request, token: str = Form("")):
    _check_rate(request, "auth-verify", 20)
    try:
        data = auth.consume_link(token)
    except auth.AuthError:
        return RedirectResponse("/?auth_error=link_expired", 303)
    resp = RedirectResponse(auth.with_flag(data["next"], "signed_in=1"), 303)
    auth.set_session(resp, request, {"email": data["email"], "provider": "email"})
    return resp


@app.get("/auth/google/start", include_in_schema=False)
async def auth_google_start(request: Request, next: str = "/"):
    _check_rate(request, "auth", 10)
    try:
        url, cookie = auth.google_start(request, next)
    except auth.AuthError:
        return RedirectResponse("/?auth_error=google_unavailable", 303)
    resp = RedirectResponse(url, 302)
    resp.set_cookie(auth.OAUTH_COOKIE, cookie, max_age=600, httponly=True, secure=auth.secure_cookies(request),
                    samesite="lax", path="/auth/google")
    return resp


@app.get("/auth/google/callback", include_in_schema=False)
async def auth_google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error or not code:
        resp = RedirectResponse("/?auth_error=google_cancelled", 303)
    else:
        try:
            user, nxt = await auth.google_finish(request, code, state)
        except auth.AuthError as e:
            resp = RedirectResponse(f"/?auth_error={'google_unverified' if str(e) == 'google_unverified' else 'google_failed'}", 303)
        else:
            resp = RedirectResponse(auth.with_flag(nxt, "signed_in=1"), 303)
            auth.set_session(resp, request, user)
    resp.delete_cookie(auth.OAUTH_COOKIE, path="/auth/google")
    return resp


@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    resp = JSONResponse({"ok": True})
    auth.clear_session(resp, request)
    return resp


@app.exception_handler(auth.AuthError)
async def auth_error(_req: Request, exc: auth.AuthError):
    return JSONResponse({"error": str(exc)}, status_code=exc.status)


# ---------------------------------------------------------------------- payments
@app.post("/api/pay/order")
async def pay_order(request: Request):
    _check_rate(request, "pay", 10)
    return await payments.create_order()


@app.post("/api/pay/verify")
async def pay_verify(body: VerifyIn, request: Request):
    _check_rate(request, "pay", 10)
    return await payments.verify(body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature)


@app.post("/api/pay/restore")
async def pay_restore(body: RestoreIn, request: Request):
    _check_rate(request, "restore", 5)
    return await payments.restore(body.payment_id, body.email)


@app.post("/api/pay/status")
async def pay_status(request: Request):
    data = await payments.check_pass(request.headers.get("x-dreamjob-pass"))
    return {"active": bool(data), "expires_at": data["exp"] if data else None}


@app.post("/api/pay/webhook", include_in_schema=False)
async def pay_webhook(request: Request):
    raw = await request.body()
    if len(raw) > 1_000_000:
        raise HTTPException(413, "Payload too large")
    ok = payments.handle_webhook(raw, request.headers.get("x-razorpay-signature", ""),
                                 request.headers.get("x-razorpay-event-id", ""))
    if not ok:
        raise HTTPException(400, "Invalid signature")
    return {"ok": True}


# ---------------------------------------------------------------------- info
@app.get("/api/config")
async def config():
    return {"version": __version__, "payments": payments.public_config(), "live_portals": live_portals(),
            "auth": auth.public_config(),
            "business_name": settings.business_name, "contact_email": settings.contact_email}


@app.get("/api/stats")
async def stats():
    return {**index.stats(), "enabled": enabled_sources(), "companies": len(BOARDS)}


@app.get("/api/health")
async def health():
    return {"status": "ok", "jobs": len(index.jobs), "version": __version__}


@app.get("/api/skills")
async def skills():
    return {"skills": nlp.ALL_SKILLS}


@app.exception_handler(HTTPException)
async def http_error(_req: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.exception_handler(payments.PaymentError)
async def payment_error(_req: Request, exc: payments.PaymentError):
    return JSONResponse({"error": str(exc)}, status_code=exc.status)


# ---------------------------------------------------------------------- pages
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
async def home():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


_PAGES = {"terms": "terms.html", "privacy": "privacy.html", "refunds": "refunds.html",
          "contact": "contact.html", "pricing": "pricing.html", "autofill": "autofill.html"}


def _render(name: str) -> str:
    """Fills the business details into a page template (values are HTML-escaped)."""
    tpl = (ROOT / "app" / "pages" / _PAGES[name]).read_text(encoding="utf-8")
    email = settings.contact_email
    values = {
        "BUSINESS_NAME": settings.business_name, "PRICE": str(settings.pro_price_inr), "DAYS": str(settings.pro_days),
        "PRO_TOPS": " and ".join(f"Top {t}" for t in sorted(settings.pro_tops)) or "Top 20 and Top 30",
        "ADDRESS": settings.business_address or "Address available on request by email.",
        "UPDATED": date(2026, 11, 25).strftime("%d %B %Y"), "VERSION": __version__,
    }
    out = tpl
    for k, v in values.items():
        out = out.replace("{{" + k + "}}", html.escape(v))
    link = f'<a href="mailto:{html.escape(email)}">{html.escape(email)}</a>' if email else "the contact address shown on this site once it is set"
    return out.replace("{{EMAIL_LINK}}", link)


def _page_route(name: str):
    async def page():
        return HTMLResponse(_render(name), headers={"Cache-Control": "no-cache"})
    return page


for _name in _PAGES:
    app.add_api_route(f"/{_name}", _page_route(_name), methods=["GET"], include_in_schema=False)

_zip_cache: bytes | None = None


@app.get("/download/dreamjob-autofill.zip", include_in_schema=False)
async def extension_zip():
    """The autofill browser extension, zipped from the extension/ folder."""
    global _zip_cache
    if _zip_cache is None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(EXTENSION.rglob("*")):
                if f.is_file() and not f.name.startswith(".") and f.suffix not in (".pem", ".crx", ".zip"):
                    z.write(f, Path("dreamjob-autofill") / f.relative_to(EXTENSION))
        _zip_cache = buf.getvalue()
    return Response(_zip_cache, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="dreamjob-autofill.zip"'})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(STATIC / "favicon.svg", media_type="image/svg+xml")
