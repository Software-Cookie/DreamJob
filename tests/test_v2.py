"""Tests for v2: descriptions, experience ranges, unlimited/custom skills, new sources, payments, pages, autofill."""
import asyncio
import base64
import re
import dataclasses
import hashlib
import hmac
import io
import json
import time
import zipfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, nlp, payments, sources
from app.index import featurize, index
from app.matcher import build_profile, rank

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = (ROOT / "scripts" / "sample_resume.txt").read_text(encoding="utf-8")
SECRET = "test_secret_value_123"


def _job(i, title, text, hours_ago=2, company=None, **kw):
    j = featurize({"id": f"t:{i}", "source": "Test", "url": f"https://example.com/{i}", "title": title,
                   "company": company or f"Co{i}", "location": kw.get("location", "Worldwide"), "remote": True,
                   "posted_at": time.time() - hours_ago * 3600, "text": text, "tags": []})
    j.vec = nlp.tfidf(j.terms, {}, 5.0)
    return j


@pytest.fixture
def client(monkeypatch):
    async def no_live(*_a, **_k):
        return []

    async def noop(*_a, **_k):
        return None
    monkeypatch.setattr(index, "live", no_live)
    monkeypatch.setattr(index, "run_forever", noop)
    monkeypatch.setattr(index, "_load_snapshot", lambda: None)
    index.jobs = [_job(1, "Senior Backend Engineer", "Python Django Kafka Kubernetes AWS PostgreSQL. 3-5 years of experience.")]
    main._hits.clear()
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def paid(monkeypatch):
    """Payments switched on with test keys."""
    s = dataclasses.replace(payments.settings, razorpay_key_id="rzp_test_abc", razorpay_key_secret=SECRET,
                            razorpay_webhook_secret="whsec", pass_secret="", pro_price_inr=99, pro_days=30,
                            pro_tops=frozenset({20, 30}))
    monkeypatch.setattr(payments, "settings", s)
    monkeypatch.setattr(main, "settings", s)
    payments._status.clear()
    payments._seen_events.clear()
    return s


# ---------------------------------------------------------------------- matching
def test_required_years_ranges():
    assert nlp.required_years("We need 3-5 years of experience with Python") == (3, 5)
    assert nlp.required_years("4+ years of professional experience") == (4, None)
    assert nlp.required_years("Experience: 2 to 4 years in sales") == (2, 4)
    assert nlp.required_years("Founded 10 years ago, we build tools") == (None, None)


def test_experience_verdicts():
    p = build_profile(SAMPLE)  # about 7 years
    def fit(text):
        res, _, _ = rank(p, [_job(1, "Senior Backend Engineer", "Python Kafka. " + text)], {}, 5.0, hours=24, top=3,
                         exp_match=False)
        return res[0]["experience"]
    assert fit("3-5 years of experience")["fit"] in ("good", "over")
    assert fit("12+ years of experience")["fit"] == "short"
    assert fit("5+ years of experience")["fit"] == "good"
    assert "Asks for 5+ years" in fit("5+ years of experience")["text"]


FRESHER = ("Ananya Rao\nComputer Science Graduate | Hyderabad\nB.Tech Computer Science, JNTU 2021 - 2025\n"
           "Skills: Python, Java, SQL, JavaScript, React, Git\nSoftware Intern at Acme, Jun 2024 - Aug 2024\n"
           "Looking for an entry level software engineer role.")


def test_experience_gate_matches_seniority():
    """Freshers don't get Staff/Senior roles; seniors don't get junior roles; roles that state nothing stay."""
    senior, fresher = build_profile(SAMPLE), build_profile(FRESHER)
    assert fresher.level == "entry" and senior.level in ("senior", "lead")
    jobs = [_job(1, "Staff Software Engineer", "Python, Java, SQL, Kafka, Kubernetes. 8+ years of experience."),
            _job(2, "Senior Backend Engineer", "Python, Kafka, Kubernetes, AWS, SQL"),
            _job(3, "Junior Python Developer", "Python, SQL, Git, JavaScript"),
            _job(4, "Software Engineer I", "Python, Java, React"),
            _job(5, "Software Engineer", "Python, Kafka, SQL. Entry-level role, new grads welcome."),
            _job(6, "Software Engineer", "Python, Java, Kafka, SQL, React"),
            _job(7, "Backend Engineer", "Python, Kafka, Kubernetes. Requires 3-5 years of experience.")]
    stats = {}
    titles = lambda p, **kw: {r["company"] for r in rank(p, jobs, {}, 5.0, hours=24, top=10, **kw)[0]}
    f = titles(fresher, stats=stats)
    assert "Co1" not in f and "Co2" not in f and "Co7" not in f       # too senior
    assert {"Co3", "Co4", "Co5", "Co6"} <= f                           # entry-level and unstated roles
    assert stats["hidden_experience"] == 3
    s = titles(senior)
    assert "Co3" not in s and "Co4" not in s and "Co5" not in s       # too junior
    assert {"Co1", "Co2", "Co6", "Co7"} <= s
    assert "Co1" in titles(fresher, exp_match=False)                  # the switch shows everything


def test_job_levels_from_titles_and_descriptions():
    assert nlp.level_from_title("Software Engineer II") == "mid"
    assert nlp.level_from_title("Data Analyst I") == "entry"
    assert nlp.level_from_title("Sr. Software Engineer I") == "senior"
    assert nlp.level_from_text("We welcome new grads and recent graduates") == "entry"
    assert nlp.level_from_text("Sie bringen mehrjährige Berufserfahrung mit") == "mid"
    assert nlp.level_from_text("We mentor junior engineers") is None    # 'junior' alone in a description is not a level
    assert nlp.required_years("Mindestens 3 Jahre Berufserfahrung in Python") == (3, None)
    assert nlp.required_years("3 à 5 ans d'expérience") == (3, 5)


def test_unrelated_jobs_are_not_padded_in():
    p = build_profile(SAMPLE)
    jobs = [_job(1, "Backend Engineer", "Python Kafka Kubernetes AWS"),
            _job(2, "Mobile Developer", "Swift, Kotlin, Objective-C, Xcode, Android Studio, Jetpack Compose", company="M")]
    res = rank(p, jobs, {}, 5.0, hours=24, top=10)[0]
    assert [r["company"] for r in res] == ["Co1"]


def test_newer_postings_win_ties():
    p = build_profile(SAMPLE)
    old = _job(1, "Senior Backend Engineer", "Python Kafka Kubernetes AWS", hours_ago=24 * 25, company="Old")
    new = _job(2, "Senior Backend Engineer", "Python Kafka Kubernetes AWS", hours_ago=3, company="New")
    res = rank(p, [old, new], {}, 5.0, hours=720, top=2)[0]
    assert [r["company"] for r in res] == ["New", "Old"]


def test_custom_and_unlimited_skills_are_matched(client):
    # a skill outside the built-in list ("Zephyr RTOS") must still match the job text
    index.jobs = [_job(1, "Firmware Engineer", "Embedded C on Zephyr RTOS and FreeRTOS. Bluetooth Low Energy."),
                  _job(2, "Firmware Engineer", "Embedded C on bare metal.", company="Other")]
    skills = ["Zephyr RTOS", "Embedded C"] + [f"skill number {i}" for i in range(150)]
    body = {"profile": {"titles": ["firmware engineer"], "skills": skills, "years": 4}, "top": 10}
    r = client.post("/api/match", json=body)
    assert r.status_code == 200, r.text
    res = r.json()["results"]
    assert res[0]["company"] == "Co1" and "Zephyr RTOS" in res[0]["matched_skills"]
    assert len(r.json()["profile"]["skills"]) == 152
    body["profile"]["skills"] = [f"s{i}" for i in range(301)]
    assert client.post("/api/match", json=body).status_code == 422  # sane upper bound


def test_full_description_keeps_paragraphs():
    raw = "<h3>About</h3><p>We build things.</p><ul><li>Python</li><li>SQL</li></ul><p>Apply now</p>"
    text = nlp.strip_html(raw, keep_lines=True)
    assert "• Python\n• SQL" in text and "About\n\nWe build things." in text and "\n\n\n" not in text
    d = sources._job(id="x", source="T", url="https://x", title="Dev", posted_at=time.time(), description=raw)
    j = featurize(d)
    assert "• Python" in j.public()["description"] and j.public()["snippet"]


def test_resume_contact_and_history():
    text = ("Priya Sharma\nBackend Engineer | Bengaluru, India\npriya.sharma@example.com | +91 98765 43210\n"
            "linkedin.com/in/priyasharma | github.com/priyas\n\nEXPERIENCE\nSenior Backend Engineer, Acme Corp\n"
            "Jan 2021 - Present\nBackend Engineer at Beta Labs | Mar 2018 - Dec 2020\n\nEDUCATION\n"
            "B.Tech Computer Science, IIT Madras 2014 - 2018\n")
    c = nlp.extract_contact(text)
    assert (c["first_name"], c["last_name"]) == ("Priya", "Sharma")
    assert c["email"] == "priya.sharma@example.com" and c["phone"].startswith("+91")
    assert c["linkedin"] == "https://linkedin.com/in/priyasharma" and c["github"].endswith("github.com/priyas")
    jobs, schools = nlp.extract_history(text)
    assert jobs[0]["title"] == "Senior Backend Engineer" and jobs[0]["company"] == "Acme Corp" and jobs[0]["current"]
    assert jobs[1]["company"] == "Beta Labs" and jobs[1]["start"] == {"month": 3, "year": 2018}
    assert schools and "IIT Madras" in schools[0]["school"]


def test_profile_extract_endpoint(client):
    r = client.post("/api/profile/extract", data={"text": SAMPLE})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {"contact", "experience", "education", "skills", "years"}
    assert "Python" in body["skills"]


# ---------------------------------------------------------------------- new sources
def test_hacker_news_parser():
    c = {"objectID": "42", "created_at_i": int(time.time()) - 3600, "parent_id": 1,
         "comment_text": "Acme Robotics | Senior Backend Engineer | Bengaluru or REMOTE (India) | ₹40-60 LPA<p>We use Python and Kafka."}
    j = sources._hn_job(c)
    assert j["company"] == "Acme Robotics" and j["title"] == "Senior Backend Engineer"
    assert j["remote"] and "Bengaluru" in j["location"] and "LPA" in j["salary"]
    assert j["url"] == "https://news.ycombinator.com/item?id=42"
    assert sources._hn_job({"objectID": "1", "created_at_i": 1, "comment_text": "Just a reply, not a job"}) is None


def test_smartrecruiters_fetches_descriptions(monkeypatch):
    recent = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - 3600))

    async def fake(_c, url, timeout=None, **_p):
        if url.endswith("/postings"):
            return {"content": [{"id": "p1", "name": "Data Engineer", "releasedDate": recent, "location": {"city": "Pune", "country": "in"}}]}
        return {"jobAd": {"sections": {"jobDescription": {"title": "The job", "text": "<p>Spark and Airflow</p>"}}}}
    monkeypatch.setattr(sources, "_get_json", fake)
    monkeypatch.setattr(sources, "KNOWN_JOB_IDS", set())
    sources._GH_TEXT.clear()
    out = asyncio.run(sources.smartrecruiters(None, "Acme", "Acme", asyncio.Semaphore(2)))
    assert len(out) == 1 and "Spark and Airflow" in out[0]["text"] and "_pid" not in out[0]


# ---------------------------------------------------------------------- payments
def _sig(order, pay):
    return hmac.new(SECRET.encode(), f"{order}|{pay}".encode(), hashlib.sha256).hexdigest()


def test_payment_signature_and_pass_tokens(paid):
    assert payments.valid_payment_signature("order_TestOrd00001", "pay_TestPay000001", _sig("order_TestOrd00001", "pay_TestPay000001"))
    assert not payments.valid_payment_signature("order_TestOrd00001", "pay_TestPay000002", _sig("order_TestOrd00001", "pay_TestPay000001"))
    p = payments.issue_pass("pay_TestPay000001", time.time())
    assert payments.read_pass(p["token"])["pid"] == "pay_TestPay000001"
    body, sig = p["token"].split(".")
    assert payments.read_pass(body + "x." + sig) is None          # tampered
    assert payments.read_pass(payments.issue_pass("pay_TestPay000001", time.time() - 31 * 86400)["token"]) is None  # expired


def test_config_never_leaks_secrets(client, paid):
    cfg = client.get("/api/config").json()
    text = json.dumps(cfg)
    assert cfg["payments"]["enabled"] and cfg["payments"]["key_id"] == "rzp_test_abc"
    assert SECRET not in text and "whsec" not in text


def test_pro_tops_need_a_pass(client, paid, monkeypatch):
    body = {"profile": {"titles": ["backend engineer"], "skills": ["Python"], "years": 4}, "top": 20}
    r = client.post("/api/match", json=body)
    assert r.status_code == 402 and "Pro" in r.json()["error"]
    assert client.post("/api/match", json={**body, "top": 10}).status_code == 200

    async def fake_api(method, path, payload=None):
        return {"id": "pay_TestPay000001", "status": "captured", "amount_refunded": 0}
    monkeypatch.setattr(payments, "_api", fake_api)
    token = payments.issue_pass("pay_TestPay000001", time.time())["token"]
    assert client.post("/api/match", json=body, headers={"X-DreamJob-Pass": token}).status_code == 200
    assert client.post("/api/match", json=body, headers={"X-DreamJob-Pass": "bad.token"}).status_code == 402


def test_payments_off_means_everything_free(client):
    body = {"profile": {"titles": ["backend engineer"], "skills": ["Python"], "years": 4}, "top": 30}
    assert client.post("/api/match", json=body).status_code == 200
    assert client.post("/api/pay/order").status_code == 404


def _fake_razorpay(monkeypatch, payment, order=None):
    calls = []

    async def fake_api(method, path, payload=None):
        calls.append((method, path, payload))
        if path == "/orders" and method == "POST":
            return {"id": "order_new1", "amount": payload["amount"], "currency": "INR", "notes": payload["notes"]}
        if path.startswith("/orders/"):
            return order or {"id": "order_TestOrd00001", "amount": 9900, "notes": {"product": "dreamjob_pro"}}
        if path.endswith("/capture"):
            return {**payment, "status": "captured"}
        return payment
    monkeypatch.setattr(payments, "_api", fake_api)
    return calls


def test_order_verify_and_capture(client, paid, monkeypatch):
    pay = {"id": "pay_TestPay000001", "order_id": "order_TestOrd00001", "amount": 9900, "currency": "INR", "status": "authorized",
           "created_at": int(time.time()), "email": "a@b.co"}
    calls = _fake_razorpay(monkeypatch, pay)
    o = client.post("/api/pay/order").json()
    assert o["order_id"] == "order_new1" and o["amount"] == 9900 and "key_secret" not in o
    assert calls[0][2]["amount"] == 9900  # amount comes from the server, not the browser
    good = {"razorpay_order_id": "order_TestOrd00001", "razorpay_payment_id": "pay_TestPay000001", "razorpay_signature": _sig("order_TestOrd00001", "pay_TestPay000001")}
    r = client.post("/api/pay/verify", json=good)
    assert r.status_code == 200, r.text
    assert payments.read_pass(r.json()["token"])["pid"] == "pay_TestPay000001"
    assert any(p.endswith("/capture") for _, p, _ in calls)  # authorized payments get captured
    bad = {**good, "razorpay_signature": "ab" * 32}
    assert client.post("/api/pay/verify", json=bad).status_code == 400


def test_verify_rejects_wrong_amount_or_product(client, paid, monkeypatch):
    good = {"razorpay_order_id": "order_TestOrd00001", "razorpay_payment_id": "pay_TestPay000001", "razorpay_signature": _sig("order_TestOrd00001", "pay_TestPay000001")}
    _fake_razorpay(monkeypatch, {"id": "pay_TestPay000001", "order_id": "order_TestOrd00001", "amount": 100, "currency": "INR", "status": "captured"})
    assert client.post("/api/pay/verify", json=good).status_code == 400
    _fake_razorpay(monkeypatch, {"id": "pay_TestPay000001", "order_id": "order_TestOrd00001", "amount": 9900, "currency": "INR", "status": "captured"},
                   order={"id": "order_TestOrd00001", "amount": 9900, "notes": {"product": "something_else"}})
    assert client.post("/api/pay/verify", json=good).status_code == 400
    _fake_razorpay(monkeypatch, {"id": "pay_TestPay000001", "order_id": "order_TestOrd00001", "amount": 9900, "currency": "INR", "status": "failed"})
    assert client.post("/api/pay/verify", json=good).status_code == 402


def test_restore_checks_email(client, paid, monkeypatch):
    pay = {"id": "pay_TestPay000009", "order_id": "order_TestOrd00001", "amount": 9900, "currency": "INR", "status": "captured",
           "created_at": int(time.time()) - 86400, "email": "Me@Example.com"}
    _fake_razorpay(monkeypatch, pay)
    assert client.post("/api/pay/restore", json={"payment_id": "pay_TestPay000009", "email": "other@example.com"}).status_code == 403
    r = client.post("/api/pay/restore", json={"payment_id": "pay_TestPay000009", "email": "me@example.com"})
    assert r.status_code == 200 and r.json()["expires_at"] > time.time()


def test_webhook_signature_and_refund_revokes(client, paid, monkeypatch):
    async def captured(method, path, payload=None):
        return {"id": "pay_TestPay000005", "status": "captured", "amount_refunded": 0}
    monkeypatch.setattr(payments, "_api", captured)
    token = payments.issue_pass("pay_TestPay000005", time.time())["token"]
    assert asyncio.run(payments.check_pass(token))
    event = json.dumps({"event": "refund.processed", "payload": {"refund": {"entity": {"payment_id": "pay_TestPay000005"}}}}).encode()
    sig = hmac.new(b"whsec", event, hashlib.sha256).hexdigest()
    assert client.post("/api/pay/webhook", content=event, headers={"X-Razorpay-Signature": "bad"}).status_code == 400
    assert client.post("/api/pay/webhook", content=event, headers={"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": "e1"}).status_code == 200
    assert asyncio.run(payments.check_pass(token)) is None  # refunded: pass no longer works


def test_razorpay_unreachable_is_reported_cleanly(paid, monkeypatch):
    def boom(req):
        raise httpx.ConnectError("down")
    real = httpx.AsyncClient
    monkeypatch.setattr(payments.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(boom), **{k: v for k, v in kw.items() if k != "transport"}))
    with pytest.raises(payments.PaymentError) as e:
        asyncio.run(payments.create_order())
    assert e.value.status == 503 and "not been charged" in str(e.value)


# ---------------------------------------------------------------------- pages, headers, extension
def test_policy_pages_and_security_headers(client, monkeypatch):
    s = dataclasses.replace(main.settings, business_name="Acme <Jobs>", contact_email="help@acme.test")
    monkeypatch.setattr(main, "settings", s)
    for page in ("terms", "privacy", "refunds", "contact", "pricing", "autofill"):
        r = client.get(f"/{page}")
        assert r.status_code == 200, page
        assert "{{" not in r.text, page
        assert "Acme &lt;Jobs&gt;" in r.text and "<Jobs>" not in r.text
    assert "help@acme.test" in client.get("/contact").text
    h = client.get("/").headers
    assert "checkout.razorpay.com" in h["content-security-policy"] and h["x-frame-options"] == "DENY"
    assert client.get("/api/health").headers["cache-control"] == "no-store"


def test_extension_zip_and_manifest(client):
    r = client.get("/download/dreamjob-autofill.zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "dreamjob-autofill/manifest.json" in names and "dreamjob-autofill/filler.js" in names
    m = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
    assert m["manifest_version"] == 3
    used = set(m["content_scripts"][0]["js"]) | set(m["content_scripts"][0]["css"]) | {m["background"]["service_worker"],
            m["options_page"], m["action"]["default_popup"], *m["icons"].values()}
    for f in used:
        assert (ROOT / "extension" / f).is_file(), f


# ---------------------------------------------------------------------- crawling
def test_only_one_process_holds_the_crawler_lock(tmp_path, monkeypatch):
    from app import index as index_mod
    monkeypatch.setattr(index_mod, "settings", dataclasses.replace(index_mod.settings, data_dir=tmp_path))
    first = index_mod._crawler_lock()
    assert first is not None
    assert index_mod._crawler_lock() is None  # a second worker must follow, not crawl
    first.close()
    again = index_mod._crawler_lock()
    assert again is not None
    again.close()


def test_failed_board_keeps_its_previous_jobs(monkeypatch):
    calls = []

    async def failing(client, slug, name, sem):
        calls.append(slug)
        raise httpx.HTTPStatusError("boom", request=httpx.Request("GET", "https://x"), response=httpx.Response(500))
    monkeypatch.setattr(sources, "_ATS", {**sources._ATS, "greenhouse": failing})
    monkeypatch.setattr(sources, "BOARDS", [("greenhouse", "acme", "Acme")])
    monkeypatch.setattr(sources, "KNOWN_JOB_IDS", {"gh:acme:1", "gh:acme:2", "gh:other:3"})
    out = asyncio.run(sources.company_boards(None))
    assert sorted(d["id"] for d in out) == ["gh:acme:1", "gh:acme:2"] and all(d["_reuse"] for d in out)


# ---------------------------------------------------------------------- deep search on job portals
def test_careerjet_and_jsearch_experience_filter(monkeypatch):
    from email.utils import formatdate
    fresh = formatdate(time.time() - 3600, usegmt=True).replace(", ", ",")   # Careerjet writes "Wed,15 Nov 2025 ..."
    old = formatdate(time.time() - 40 * 86400, usegmt=True)
    seen = {}

    def handler(req: httpx.Request):
        if "careerjet" in req.url.host:
            seen["cj_auth"] = req.headers.get("authorization", "")
            seen["cj_ip"] = req.url.params.get("user_ip")
            return httpx.Response(200, json={"type": "JOBS", "hits": 2, "jobs": [
                {"title": "Python Developer", "company": "Acme India", "date": fresh, "locations": "Bengaluru",
                 "url": "https://jobviewtrack.com/v2/1", "description": "Django, SQL, 3+ years of experience", "salary": ""},
                {"title": "Old Job", "company": "X", "date": old, "locations": "Pune", "url": "https://jobviewtrack.com/v2/2"}]})
        if "jsearch" in req.url.host:
            seen["js_req"] = req.url.params.get("job_requirements")
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404)

    s = dataclasses.replace(sources.settings, careerjet_key="cjkey", jsearch_key="k")
    monkeypatch.setattr(sources, "settings", s)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            cj = await sources.careerjet(c, "python developer", "1w", "Bengaluru", {"ip": "9.9.9.9", "ua": "UA"})
            await sources.jsearch(c, "python developer", "1w", "India", years=0.5)
            return cj
    cj = asyncio.run(run())
    assert [j["title"] for j in cj] == ["Python Developer"]           # the 40-day-old job is outside 1 week
    assert cj[0]["source"] == "Careerjet" and seen["cj_ip"] == "9.9.9.9" and seen["cj_auth"].startswith("Basic ")
    assert seen["js_req"] == "no_experience,under_3_years_experience"
    assert sources.jsearch_experience(5) == "more_than_3_years_experience"
    keys = {k.split("|")[0] for k in sources.live_searches("python developer", "1w", "", 5, {"ip": "1"})}
    assert {"remotive", "jsearch", "careerjet"} <= keys


def test_deep_search_queries():
    p = build_profile(SAMPLE)
    qs = p.search_queries(3)
    assert len(qs) == 3 and qs[0] == "backend engineer" and len(set(q.lower() for q in qs)) == 3
    assert p.queries == qs[:1]


def test_viewer_is_passed_to_live_search(client, monkeypatch):
    got = {}

    async def fake_live(queries, window, location, timeout, years=None, viewer=None):
        got.update(queries=queries, years=years, viewer=viewer)
        return []
    monkeypatch.setattr(index, "live", fake_live)
    r = client.post("/api/analyze", data={"text": SAMPLE, "top": "3"}, headers={"User-Agent": "TestBrowser/1"})
    assert r.status_code == 200
    assert len(got["queries"]) >= 2 and got["years"] > 5 and got["viewer"]["ua"] == "TestBrowser/1"


# ---------------------------------------------------------------------- sign-in
@pytest.fixture
def authed(client, monkeypatch, tmp_path):
    from app import auth
    s = dataclasses.replace(auth.settings, auth_secret="test-auth-secret", site_url="https://dreamjob.example",
                            smtp_host="smtp.example", smtp_user="bot@dreamjob.example", smtp_password="pw",
                            google_client_id="cid.apps.googleusercontent.com", google_client_secret="gsecret",
                            data_dir=tmp_path)
    monkeypatch.setattr(auth, "settings", s)
    monkeypatch.setattr(main, "settings", s)
    auth._sent.clear()
    auth._used.clear()
    client.base_url = httpx.URL("https://testserver")  # session cookies are Secure, as on the live HTTPS site
    sent = []
    monkeypatch.setattr(auth, "send_mail", lambda to, subject, text, html: sent.append((to, text)))
    return auth, sent


def test_email_link_sign_in_flow(client, authed):
    auth, sent = authed
    assert client.get("/api/auth/me").json() == {"user": None, "email": True, "google": True, "required": False}
    r = client.post("/api/auth/email/start", json={"email": "Priya@Example.com", "next": "/pricing"})
    assert r.status_code == 200 and sent[0][0] == "priya@example.com"
    link = re.search(r"https://dreamjob\.example/auth/email/verify\?token=(\S+)", sent[0][1])
    assert link, "the link must use SITE_URL"
    token = link.group(1)
    page = client.get("/auth/email/verify", params={"token": token})
    assert page.status_code == 200 and "priya@example.com" in page.text and auth.SESSION_COOKIE not in page.headers.get("set-cookie", "")
    r = client.post("/auth/email/verify", data={"token": token}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/pricing?signed_in=1"
    assert "HttpOnly" in r.headers["set-cookie"] and "Secure" in r.headers["set-cookie"] and "SameSite=lax" in r.headers["set-cookie"]
    me = client.get("/api/auth/me").json()["user"]
    assert me["email"] == "priya@example.com" and me["provider"] == "email"
    again = client.post("/auth/email/verify", data={"token": token}, follow_redirects=False)
    assert again.headers["location"] == "/?auth_error=link_expired"          # one use only
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/auth/me").json()["user"] is None


def test_sign_in_rejects_tampering_redirects_and_floods(client, authed):
    auth, sent = authed
    tok = auth.link_token("a@b.co", "//evil.com")
    assert auth.unsign("email-link", tok)["next"] == "/"                    # no open redirect
    body, sig = tok.split(".")
    assert auth.unsign("email-link", body + "x." + sig) is None
    assert auth.unsign("session", tok) is None                              # a link is not a session
    assert client.post("/api/auth/email/start", json={"email": "not-an-email"}).status_code == 422
    codes = [client.post("/api/auth/email/start", json={"email": "c@d.co"}).status_code for _ in range(4)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 429
    forged = auth.sign("session", {"email": "x@y.z", "provider": "email", "exp": time.time() - 1})
    client.cookies.set(auth.SESSION_COOKIE, forged)
    assert client.get("/api/auth/me").json()["user"] is None                # expired session


def test_emailed_links_never_use_the_host_header(client, authed, monkeypatch):
    auth, sent = authed
    monkeypatch.setattr(auth, "settings", dataclasses.replace(auth.settings, site_url=""))
    r = client.post("/api/auth/email/start", json={"email": "a@b.co"}, headers={"Host": "evil.com"})
    assert r.status_code == 503 and not sent


def test_google_sign_in_flow(client, authed, monkeypatch):
    auth, _ = authed
    r = client.get("/auth/google/start", params={"next": "/autofill"}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    from urllib.parse import urlparse, parse_qs
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["redirect_uri"] == ["https://dreamjob.example/auth/google/callback"] and q["code_challenge_method"] == ["S256"]
    state = q["state"][0]
    claims = {"aud": "cid.apps.googleusercontent.com", "iss": "https://accounts.google.com", "exp": time.time() + 600,
              "email": "Priya@gmail.com", "email_verified": True, "name": "Priya S", "picture": "https://lh3.googleusercontent.com/a"}
    seg = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    real = httpx.AsyncClient

    def google(req):
        assert b"code_verifier=" in req.content and b"client_secret=gsecret" in req.content
        return httpx.Response(200, json={"id_token": f"{seg({'alg': 'RS256'})}.{seg(claims)}.sig"})
    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(google), **kw))
    ok = client.get("/auth/google/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert ok.headers["location"] == "/autofill?signed_in=1"
    me = client.get("/api/auth/me").json()["user"]
    assert me == {"email": "priya@gmail.com", "name": "Priya S", "picture": "https://lh3.googleusercontent.com/a", "provider": "google"}
    client.cookies.clear()
    client.get("/auth/google/start", follow_redirects=False)                # a fresh attempt, answered with a forged state
    bad = client.get("/auth/google/callback", params={"code": "c", "state": "forged"}, follow_redirects=False)
    assert bad.headers["location"] == "/?auth_error=google_failed" and client.get("/api/auth/me").json()["user"] is None
    claims["email_verified"] = False                                        # unverified Google emails are refused
    r = client.get("/auth/google/start", follow_redirects=False)
    st = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    assert client.get("/auth/google/callback", params={"code": "c", "state": st}, follow_redirects=False).headers["location"] == "/?auth_error=google_unverified"


def test_auth_required_blocks_search_until_signed_in(client, authed, monkeypatch):
    auth, _ = authed
    s = dataclasses.replace(main.settings, auth_required=True)
    monkeypatch.setattr(main, "settings", s)
    monkeypatch.setattr(auth, "settings", s)
    body = {"profile": {"titles": ["backend engineer"], "skills": ["Python"], "years": 4}, "top": 10}
    r = client.post("/api/match", json=body)
    assert r.status_code == 401 and "Sign in" in r.json()["error"]
    client.cookies.set(auth.SESSION_COOKIE, auth.session_token({"email": "a@b.co", "provider": "email"}))
    assert client.post("/api/match", json=body).status_code == 200
