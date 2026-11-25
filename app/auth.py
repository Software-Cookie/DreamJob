"""Sign-in without a database: one-time email links and Google OAuth, both ending in a signed session cookie.

Email:  POST /api/auth/email/start sends a link (valid 15 minutes) -> GET /auth/email/verify shows a confirm button
        (so mail scanners that pre-open links can't use it up) -> POST /auth/email/verify sets the session.
Google: GET /auth/google/start (authorization code flow with PKCE and a state value bound to a cookie)
        -> GET /auth/google/callback exchanges the code with Google and sets the session.

Every token is HMAC-SHA256 signed with AUTH_SECRET (or a random secret created once in data/auth_secret).
No passwords are stored anywhere.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import smtplib
import ssl
import time
from collections import defaultdict, deque
from email.message import EmailMessage
from html import escape
from urllib.parse import urlencode

import httpx
from fastapi import Request

from .config import settings

log = logging.getLogger("dreamjob.auth")

SESSION_COOKIE = "dj_session"
OAUTH_COOKIE = "dj_oauth"
SESSION_DAYS = 30
LINK_MINUTES = 15
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$")
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------- configuration
def email_enabled() -> bool:
    return bool(settings.smtp_host and (settings.smtp_from or settings.smtp_user))


def google_enabled() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def enabled() -> bool:
    return email_enabled() or google_enabled()


def public_config() -> dict:
    return {"email": email_enabled(), "google": google_enabled(), "required": bool(settings.auth_required and enabled())}


def base_url(request: Request) -> str:
    """The site's public address, used in emailed links and the Google redirect. It comes from SITE_URL, never from the
    request's Host header (which a visitor controls), except on localhost for development."""
    if settings.site_url:
        return settings.site_url
    host = request.url.hostname or ""
    if host in ("localhost", "127.0.0.1"):
        return f"{request.url.scheme}://{request.url.netloc}"
    raise AuthError("Sign-in is not configured: set SITE_URL to this site's public address.", 503)


def secure_cookies(request: Request) -> bool:
    return (settings.site_url or str(request.url)).startswith("https://")


# ---------------------------------------------------------------------- signed tokens
_secret_cache: bytes | None = None


def _secret() -> bytes:
    """AUTH_SECRET, or a random secret stored once in the data folder and shared by all worker processes."""
    global _secret_cache
    if settings.auth_secret:
        return settings.auth_secret.encode()
    if _secret_cache:
        return _secret_cache
    path = settings.data_dir / "auth_secret"
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(secrets.token_hex(32).encode())
    except FileExistsError:
        pass
    for _ in range(20):  # another worker may be writing it at this moment
        value = path.read_bytes().strip()
        if value:
            _secret_cache = value
            return value
        time.sleep(0.05)
    raise RuntimeError("could not read data/auth_secret")


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _key(purpose: str) -> bytes:
    return hmac.new(_secret(), b"dreamjob-" + purpose.encode(), hashlib.sha256).digest()


def sign(purpose: str, data: dict) -> str:
    body = _b64(json.dumps(data, separators=(",", ":")).encode())
    return body + "." + _b64(hmac.new(_key(purpose), body.encode(), hashlib.sha256).digest())


def unsign(purpose: str, token: str | None) -> dict | None:
    """The token's data if its signature is right for this purpose and it has not expired."""
    if not token or len(token) > 4096 or token.count(".") != 1:
        return None
    body, sig = token.split(".")
    good = _b64(hmac.new(_key(purpose), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(good, sig):
        return None
    try:
        data = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("exp", 0) < time.time():
        return None
    return data


def safe_next(path: str | None) -> str:
    """Only same-site paths: blocks open redirects such as //evil.com or https://evil.com."""
    if not path or not path.startswith("/") or path.startswith("//") or "\\" in path or len(path) > 300:
        return "/"
    return path


def with_flag(path: str, flag: str) -> str:
    return path + ("&" if "?" in path else "?") + flag


# ---------------------------------------------------------------------- sessions
def session_token(user: dict) -> str:
    now = int(time.time())
    return sign("session", {"email": user["email"], "name": user.get("name", "")[:80],
                            "picture": user.get("picture", "")[:400], "provider": user["provider"],
                            "iat": now, "exp": now + SESSION_DAYS * 86400})


def current_user(request: Request) -> dict | None:
    data = unsign("session", request.cookies.get(SESSION_COOKIE))
    if not data or not data.get("email"):
        return None
    return {k: data.get(k, "") for k in ("email", "name", "picture", "provider")}


def set_session(response, request: Request, user: dict):
    response.set_cookie(SESSION_COOKIE, session_token(user), max_age=SESSION_DAYS * 86400, httponly=True,
                        secure=secure_cookies(request), samesite="lax", path="/")


def clear_session(response, request: Request):
    response.delete_cookie(SESSION_COOKIE, path="/", secure=secure_cookies(request), httponly=True, samesite="lax")


# ---------------------------------------------------------------------- email links
_sent: dict[str, deque] = defaultdict(deque)   # email -> send times (per worker)
_used: dict[str, float] = {}                    # link nonce -> expiry (per worker)


def normalise_email(email: str) -> str:
    email = (email or "").strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise AuthError("Enter a valid email address.", 422)
    return email


def link_token(email: str, next_path: str) -> str:
    return sign("email-link", {"email": email, "next": safe_next(next_path), "n": secrets.token_urlsafe(12),
                               "exp": int(time.time()) + LINK_MINUTES * 60})


def check_send_quota(email: str):
    now = time.monotonic()
    q = _sent[email]
    while q and now - q[0] > 600:
        q.popleft()
    if len(q) >= 3:
        raise AuthError("We've already sent several links to this address. Check your inbox and spam folder, or try again in 10 minutes.", 429)
    q.append(now)
    if len(_sent) > 20000:
        _sent.clear()


def consume_link(token: str) -> dict:
    data = unsign("email-link", token)
    if not data:
        raise AuthError("This sign-in link has expired or is not valid. Request a new one.", 400)
    now = time.time()
    for n in [n for n, exp in _used.items() if exp < now]:
        _used.pop(n, None)
    if data["n"] in _used:
        raise AuthError("This sign-in link has already been used. Request a new one.", 400)
    _used[data["n"]] = data["exp"]
    return data


def send_mail(to: str, subject: str, text: str, html: str):
    """Sends one email over SMTP (STARTTLS on 587, TLS on 465). Runs in a worker thread."""
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    ctx = ssl.create_default_context()
    if settings.smtp_port == 465 and settings.smtp_tls != "none":
        server = smtplib.SMTP_SSL(settings.smtp_host, 465, timeout=20, context=ctx)
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
        if settings.smtp_tls != "none":
            server.starttls(context=ctx)
    try:
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def link_email(link: str) -> tuple[str, str, str]:
    name = settings.business_name or "DreamJob"
    subject = f"Your {name} sign-in link"
    text = (f"Sign in to {name} by opening this link:\n\n{link}\n\n"
            f"The link works once and expires in {LINK_MINUTES} minutes. If you didn't ask for it, ignore this email.")
    html = f"""<!doctype html><html><body style="margin:0;background:#F8FAFC;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#0B1220">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" style="max-width:480px;background:#fff;border:1px solid #E5E7EB;border-radius:14px">
<tr><td style="padding:32px">
<p style="margin:0 0 20px;font-size:18px;font-weight:700">{escape(name)}</p>
<p style="margin:0 0 8px;font-size:20px;font-weight:700">Sign in to your account</p>
<p style="margin:0 0 24px;font-size:15px;line-height:1.6;color:#374151">Click the button below to sign in. The link works once and expires in {LINK_MINUTES} minutes.</p>
<p style="margin:0 0 24px"><a href="{escape(link)}" style="display:inline-block;background:#0B1220;color:#fff;text-decoration:none;font-weight:600;padding:12px 22px;border-radius:10px">Sign in to {escape(name)}</a></p>
<p style="margin:0;font-size:13px;line-height:1.6;color:#6B7280">If you didn't request this, you can safely ignore this email. Nobody can sign in without access to your inbox.</p>
</td></tr></table></td></tr></table></body></html>"""
    return subject, text, html


# ---------------------------------------------------------------------- Google OAuth
def google_start(request: Request, next_path: str) -> tuple[str, str]:
    """Returns (Google URL to redirect to, signed cookie holding state and the PKCE verifier)."""
    if not google_enabled():
        raise AuthError("Google sign-in is not set up on this site.", 404)
    verifier = secrets.token_urlsafe(48)
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    state = secrets.token_urlsafe(24)
    url = GOOGLE_AUTH + "?" + urlencode({
        "client_id": settings.google_client_id, "redirect_uri": base_url(request) + "/auth/google/callback",
        "response_type": "code", "scope": "openid email profile", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256", "prompt": "select_account",
    })
    cookie = sign("oauth", {"state": state, "v": verifier, "next": safe_next(next_path), "exp": int(time.time()) + 600})
    return url, cookie


async def google_finish(request: Request, code: str, state: str) -> tuple[dict, str]:
    """Checks the state, exchanges the code with Google and returns (user, next path)."""
    saved = unsign("oauth", request.cookies.get(OAUTH_COOKIE))
    if not saved or not state or not hmac.compare_digest(saved["state"], state):
        raise AuthError("google_state", 400)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=8.0)) as c:
            r = await c.post(GOOGLE_TOKEN, data={
                "code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
                "redirect_uri": base_url(request) + "/auth/google/callback", "grant_type": "authorization_code",
                "code_verifier": saved["v"],
            })
    except httpx.HTTPError as e:
        log.warning("google token exchange failed: %r", e)
        raise AuthError("google_failed", 502)
    if r.status_code != 200:
        log.warning("google token exchange answered %s", r.status_code)
        raise AuthError("google_failed", 502)
    # The ID token came straight from Google's token endpoint over TLS, so its claims are trusted (Google's
    # OpenID Connect guide); audience, issuer, expiry and email verification are still checked.
    try:
        claims = json.loads(_unb64(r.json()["id_token"].split(".")[1]))
    except (KeyError, IndexError, ValueError, json.JSONDecodeError):
        raise AuthError("google_failed", 502)
    if (claims.get("aud") != settings.google_client_id
            or claims.get("iss") not in ("https://accounts.google.com", "accounts.google.com")
            or claims.get("exp", 0) < time.time() or not claims.get("email") or not claims.get("email_verified")):
        raise AuthError("google_unverified", 400)
    user = {"email": claims["email"].lower(), "name": claims.get("name", ""), "picture": claims.get("picture", ""),
            "provider": "google"}
    return user, saved["next"]


CONFIRM_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in – {name}</title><link rel="icon" href="/static/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/static/styles.css?v=9"></head>
<body><main class="auth-page"><div class="card auth-card">
<a class="brand" href="/"><img src="/static/logo.svg" width="28" height="28" alt=""><span>DreamJob</span></a>
<h1>Confirm sign-in</h1><p class="muted">Continue as <b>{email}</b>.</p>
<form method="post" action="/auth/email/verify"><input type="hidden" name="token" value="{token}">
<button class="btn btn-primary btn-block" type="submit">Continue to {name}</button></form>
<p class="muted small">Didn't request this? Close this page. Nothing happens unless you continue.</p>
</div></main></body></html>"""
