"""Razorpay payments for DreamJob Pro.

Flow (Razorpay Standard Checkout):
  1. Browser asks POST /api/pay/order. The server creates a Razorpay order; the amount always comes
     from server settings, never from the browser.
  2. Browser opens Razorpay Checkout with that order id. The customer pays on Razorpay's own page.
  3. Browser sends the three values Checkout returns to POST /api/pay/verify. The server checks the
     HMAC signature with the key secret, then asks Razorpay's API that the payment is real, belongs
     to this order and has the right amount, and captures it if needed.
  4. The server answers with a signed Pro pass (no database needed). The browser keeps it and sends it
     in the X-DreamJob-Pass header. Lost it, or on another device? POST /api/pay/restore with the
     payment id and the email used at checkout issues it again.
  5. Webhooks (POST /api/pay/webhook) are verified with the webhook secret. Refunds revoke the pass.

Secrets (key secret, webhook secret, pass secret) are read from environment variables only and are
never sent to the browser or written to logs.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time

import httpx

from .config import settings

log = logging.getLogger("dreamjob.payments")
API = "https://api.razorpay.com/v1"
PRODUCT = "dreamjob_pro"
STATUS_TTL = 6 * 3600  # re-check a pass's payment with Razorpay at most every 6 hours


class PaymentError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def enabled() -> bool:
    return bool(settings.razorpay_key_id and settings.razorpay_key_secret)


def public_config() -> dict:
    return {"enabled": enabled(), "key_id": settings.razorpay_key_id if enabled() else "",
            "amount": settings.pro_price_inr * 100, "currency": "INR", "price": settings.pro_price_inr,
            "days": settings.pro_days, "pro_tops": sorted(settings.pro_tops), "name": "DreamJob Pro"}


# ---------------------------------------------------------------------- signatures
def _hmac_hex(key: str, message: bytes) -> str:
    return hmac.new(key.encode(), message, hashlib.sha256).hexdigest()


def valid_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """Razorpay: HMAC-SHA256(order_id + '|' + payment_id, key_secret) == razorpay_signature."""
    if not (order_id and payment_id and signature and settings.razorpay_key_secret):
        return False
    expected = _hmac_hex(settings.razorpay_key_secret, f"{order_id}|{payment_id}".encode())
    return hmac.compare_digest(expected, signature)


def valid_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """Razorpay: HMAC-SHA256(raw request body, webhook_secret) == X-Razorpay-Signature."""
    if not (settings.razorpay_webhook_secret and signature):
        return False
    return hmac.compare_digest(_hmac_hex(settings.razorpay_webhook_secret, raw_body), signature)


# ---------------------------------------------------------------------- Pro pass (signed token)
def _pass_key() -> bytes:
    if settings.pass_secret:
        return settings.pass_secret.encode()
    # derived, so a separate secret is optional; rotating the key secret invalidates passes (restore re-issues)
    return hmac.new(settings.razorpay_key_secret.encode(), b"dreamjob-pass-v1", hashlib.sha256).digest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_pass(payment_id: str, paid_at: float) -> dict:
    exp = int(paid_at + settings.pro_days * 86400)
    body = _b64(json.dumps({"v": 1, "pid": payment_id, "exp": exp}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_pass_key(), body.encode(), hashlib.sha256).digest())
    return {"token": f"{body}.{sig}", "expires_at": exp, "payment_id": payment_id}


def read_pass(token: str | None) -> dict | None:
    """The pass's data if the signature is valid and it has not expired, else None."""
    if not token or "." not in token or len(token) > 400 or not enabled():
        return None
    body, sig = token.split(".", 1)
    good = _b64(hmac.new(_pass_key(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(good, sig):
        return None
    try:
        data = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("exp", 0) < time.time():
        return None
    return data


# payment id -> (checked_at, still_valid). Per worker; refunds seen by webhook or API revoke the pass.
_status: dict[str, tuple[float, bool]] = {}


async def check_pass(token: str | None) -> dict | None:
    data = read_pass(token)
    if not data:
        return None
    pid = data["pid"]
    checked = _status.get(pid)
    if checked is None or time.time() - checked[0] > STATUS_TTL:
        try:
            pay = await _api("GET", f"/payments/{pid}")
            ok = pay.get("status") == "captured" and not pay.get("amount_refunded")
            _status[pid] = (time.time(), ok)
        except PaymentError:
            # Razorpay unreachable: keep the last answer, or trust the signed pass. Paid users are not locked out.
            _status[pid] = (time.time() - STATUS_TTL + 600, checked[1] if checked else True)
        if len(_status) > 50000:
            _status.clear()
    return data if _status[pid][1] else None


# ---------------------------------------------------------------------- Razorpay API
async def _api(method: str, path: str, payload: dict | None = None) -> dict:
    try:
        async with httpx.AsyncClient(base_url=API, timeout=httpx.Timeout(15.0, connect=8.0),
                                     auth=(settings.razorpay_key_id, settings.razorpay_key_secret)) as c:
            r = await c.request(method, path, json=payload)
    except httpx.HTTPError as e:
        log.warning("razorpay %s %s failed: %r", method, path.split("/")[1], e)
        raise PaymentError("Payments are not reachable right now. You have not been charged twice. Try again in a minute.", 503)
    if r.status_code == 401:
        log.error("razorpay rejected the API keys (check RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET)")
        raise PaymentError("Payments are not set up correctly on this server. Nothing was charged.", 503)
    if r.status_code == 404:
        raise PaymentError("That payment was not found. Check the payment ID in your Razorpay receipt email.", 404)
    if r.status_code >= 400:
        try:
            desc = r.json().get("error", {}).get("description", "")
        except ValueError:
            desc = ""
        log.warning("razorpay %s %s -> %s %s", method, path.split("/")[1], r.status_code, desc[:120])
        raise PaymentError(desc or "Razorpay could not process the request. Try again.", 502 if r.status_code >= 500 else 400)
    return r.json()


async def create_order() -> dict:
    if not enabled():
        raise PaymentError("Payments are turned off on this server.", 404)
    amount = settings.pro_price_inr * 100  # paise
    order = await _api("POST", "/orders", {
        "amount": amount, "currency": "INR", "receipt": "dj_" + secrets.token_hex(8),
        "notes": {"product": PRODUCT, "days": str(settings.pro_days)},
    })
    return {"order_id": order["id"], "amount": order["amount"], "currency": order["currency"],
            "key_id": settings.razorpay_key_id}


async def _confirm(pay: dict, order_id: str | None) -> dict:
    """Checks a payment belongs to a DreamJob Pro order with the right amount, capturing it if needed."""
    oid = pay.get("order_id")
    if not oid or (order_id and oid != order_id):
        raise PaymentError("This payment does not belong to a DreamJob order.", 400)
    order = await _api("GET", f"/orders/{oid}")
    if (order.get("notes") or {}).get("product") != PRODUCT:
        raise PaymentError("This payment is not for DreamJob Pro.", 400)
    if pay.get("currency") != "INR" or int(pay.get("amount", 0)) != int(order.get("amount", -1)):
        raise PaymentError("The paid amount does not match the order. Contact support with your payment ID.", 400)
    if pay.get("amount_refunded") or pay.get("status") == "refunded":
        raise PaymentError("This payment was refunded, so the pass is no longer active.", 402)
    if pay.get("status") == "authorized":  # account set to manual capture: capture it now
        pay = await _api("POST", f"/payments/{pay['id']}/capture", {"amount": pay["amount"], "currency": pay["currency"]})
    if pay.get("status") != "captured":
        raise PaymentError("The payment has not completed. If money left your account, it is refunded automatically by your bank.", 402)
    _status[pay["id"]] = (time.time(), True)
    return pay


async def verify(order_id: str, payment_id: str, signature: str) -> dict:
    if not enabled():
        raise PaymentError("Payments are turned off on this server.", 404)
    if not valid_payment_signature(order_id, payment_id, signature):
        log.warning("payment signature mismatch for %s", payment_id[:24])
        raise PaymentError("The payment could not be verified. If you were charged, use “Restore purchase” with your payment ID.", 400)
    pay = await _confirm(await _api("GET", f"/payments/{payment_id}"), order_id)
    log.info("pro pass issued for payment %s", payment_id)
    return issue_pass(payment_id, float(pay.get("created_at") or time.time()))


async def restore(payment_id: str, email: str) -> dict:
    if not enabled():
        raise PaymentError("Payments are turned off on this server.", 404)
    pay = await _api("GET", f"/payments/{payment_id}")
    if (pay.get("email") or "").strip().lower() != email.strip().lower():
        raise PaymentError("The email does not match this payment. Use the email you entered at checkout.", 403)
    pay = await _confirm(pay, None)
    p = issue_pass(payment_id, float(pay.get("created_at") or 0))
    if p["expires_at"] < time.time():
        raise PaymentError("This pass has expired. Buy a new one to keep using Pro.", 402)
    return p


_seen_events: dict[str, float] = {}


def handle_webhook(raw_body: bytes, signature: str, event_id: str = "") -> bool:
    """Returns False when the signature is wrong. Duplicate deliveries are ignored."""
    if not valid_webhook_signature(raw_body, signature):
        return False
    if event_id and event_id in _seen_events:
        return True
    if event_id:
        _seen_events[event_id] = time.time()
        if len(_seen_events) > 10000:
            for k in sorted(_seen_events, key=_seen_events.get)[:5000]:
                _seen_events.pop(k, None)
    try:
        event = json.loads(raw_body)
    except json.JSONDecodeError:
        return True
    name = event.get("event", "")
    payload = event.get("payload") or {}
    pay = (payload.get("payment") or {}).get("entity") or {}
    refund = (payload.get("refund") or {}).get("entity") or {}
    pid = pay.get("id") or refund.get("payment_id")
    if name.startswith("refund.") and pid:
        _status[pid] = (time.time(), False)
    elif name == "payment.captured" and pid:
        _status[pid] = (time.time(), True)
    log.info("razorpay webhook %s %s", name, pid or "")
    return True
