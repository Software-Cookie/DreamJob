"""Fast offline tests for parsing and matching (no network)."""
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app import nlp
from app.index import featurize, index
from app.matcher import build_profile, rank, read_resume, ResumeError

SAMPLE = (Path(__file__).resolve().parent.parent / "scripts" / "sample_resume.txt").read_text(encoding="utf-8")


def _job(i, title, text, hours_ago=2, company=None, remote=True, location="Worldwide"):
    return featurize({
        "id": f"t:{i}", "source": "Test", "url": f"https://example.com/{i}", "title": title,
        "company": company or f"Co{i}", "location": location, "remote": remote,
        "posted_at": time.time() - hours_ago * 3600, "text": text, "tags": [],
    })


def test_skill_extraction_handles_symbols_and_ambiguity():
    s = nlp.extract_skills("C++, C#, .NET, Node.js, CI/CD and scikit-learn. We go to market. Go and Golang.")
    for k in ("C++", "C#", ".NET", "Node.js", "CI/CD", "scikit-learn", "Go"):
        assert k in s, k
    assert "Go" not in nlp.extract_skills("we go to the office")


def test_profile_from_resume():
    p = build_profile(SAMPLE)
    assert p.titles[0] == "backend engineer"
    assert {"Python", "Kafka", "Kubernetes", "PostgreSQL"} <= set(p.skills)
    assert 5 <= p.years <= 10
    assert p.level in ("senior", "lead")


def test_years_ignore_education():
    assert nlp.years_of_experience("B.Tech, Some University 2014 - 2018\nAnalyst, Acme Jan 2020 - Dec 2022") == 3.0


def test_ranking_prefers_relevant_role_and_respects_window():
    p = build_profile(SAMPLE)
    jobs = [
        _job(1, "Senior Backend Engineer (Python)", "Python, Django, PostgreSQL, Kafka, Kubernetes, AWS. 5+ years of experience."),
        _job(2, "Registered Nurse", "Patient care in a busy hospital ward. EHR experience."),
        _job(3, "Graphic Designer", "Adobe Photoshop, Illustrator and Figma."),
        _job(4, "Backend Engineer", "Go, Python, Redis, Docker", hours_ago=60),
    ]
    idx_idf, d = {}, 5.0
    for j in jobs:
        j.vec = nlp.tfidf(j.terms, idx_idf, d)
    res, considered, _ = rank(p, jobs, idx_idf, d, hours=24, top=10)
    assert considered == 3  # job 4 is older than 24h
    assert res[0]["title"] == "Senior Backend Engineer (Python)"
    assert res[0]["score"] >= 70
    assert all(r["title"] != "Registered Nurse" or r["score"] < 40 for r in res)
    res72, _, _ = rank(p, jobs, idx_idf, d, hours=72, top=3)
    assert any(r["title"] == "Backend Engineer" for r in res72)


def test_location_and_remote_filters():
    p = build_profile(SAMPLE)
    jobs = [_job(1, "Backend Engineer", "Python", remote=False, location="Berlin, Germany"),
            _job(2, "Backend Engineer", "Python Kafka", remote=False, location="Bengaluru, India", company="X")]
    for j in jobs:
        j.vec = nlp.tfidf(j.terms, {}, 5.0)
    res, _, _ = rank(p, jobs, {}, 5.0, hours=24, top=10, location="india")
    assert [r["location"] for r in res] == ["Bengaluru, India"]
    res, _, _ = rank(p, jobs, {}, 5.0, hours=24, top=10, location="Bangalore")  # city alias
    assert [r["location"] for r in res] == ["Bengaluru, India"]
    res, _, _ = rank(p, jobs, {}, 5.0, hours=24, top=10, remote_only=True)
    assert res == []


def test_unreadable_file_is_rejected():
    try:
        read_resume("cv.pdf", b"%PDF-1.4 garbage")
    except ResumeError as e:
        assert "read" in str(e).lower() or "text" in str(e).lower()
    else:
        raise AssertionError("expected ResumeError")


def test_api_analyze_with_text(monkeypatch):
    jobs = [_job(1, "Senior Backend Engineer", "Python Django Kafka Kubernetes AWS PostgreSQL")]
    for j in jobs:
        j.vec = nlp.tfidf(j.terms, {}, 5.0)

    async def no_live(*_a, **_k):
        return []

    async def noop(*_a, **_k):
        return None

    monkeypatch.setattr(index, "live", no_live)
    monkeypatch.setattr(index, "run_forever", noop)
    monkeypatch.setattr(index, "_load_snapshot", lambda: None)
    monkeypatch.setattr(index, "_rebuild", lambda: None)
    index.jobs = jobs
    from app.main import app
    with TestClient(app) as c:
        r = c.post("/api/analyze", data={"text": SAMPLE, "window": "24h", "top": "3"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["results"][0]["title"] == "Senior Backend Engineer"
        r2 = c.post("/api/match", json={"profile": body["profile"], "window": "1w", "top": 10})
        assert r2.status_code == 200
        assert c.post("/api/analyze", data={"text": "too short"}).status_code == 422
        assert c.post("/api/analyze", data={"text": SAMPLE, "top": "7"}).status_code == 422
        assert c.get("/").status_code == 200
        assert c.get("/static/app.js").headers["content-type"].startswith("application/javascript")


def test_rate_limit_returns_429(monkeypatch):
    from app import main
    import dataclasses
    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, rate_limit_per_minute=3))
    main._hits.clear()
    body = {"profile": {"titles": ["data analyst"], "skills": ["SQL"], "years": 2}, "top": 3}
    async def no_live(*_a, **_k):
        return []
    async def noop(*_a, **_k):
        return None
    monkeypatch.setattr(index, "live", no_live)
    monkeypatch.setattr(index, "run_forever", noop)
    monkeypatch.setattr(index, "_load_snapshot", lambda: None)
    index.jobs = []
    with TestClient(main.app) as c:
        codes = [c.post("/api/match", json=body, headers={"X-Forwarded-For": "1.2.3.4"}).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]


def test_every_window_is_strict():
    """Each window must return only jobs posted inside it (the bug users saw with old posts)."""
    p = build_profile(SAMPLE)
    ages = [1, 30, 50, 70, 100, 200, 400, 700, 900]  # hours
    jobs = [_job(i, "Senior Backend Engineer", "Python Kafka Kubernetes AWS", hours_ago=h, company=f"C{i}")
            for i, h in enumerate(ages)]
    for j in jobs:
        j.vec = nlp.tfidf(j.terms, {}, 5.0)
    now = time.time()
    for hours in (24, 48, 72, 168, 720):
        res, considered, _ = rank(p, jobs, {}, 5.0, hours=hours, top=30)
        assert considered == sum(1 for h in ages if h <= hours)
        assert all(now - r["posted_at"] <= hours * 3600 for r in res)


def test_sources_parse_dates():
    from app.sources import _ts
    assert abs(_ts("Mon, 16 Nov 2026 18:32:34 +0000") - _ts("2026-11-16T18:32:34Z")) < 1
    assert _ts(1794855653000) == 1794855653.0
    assert _ts("garbage") is None


def test_greenhouse_reuses_known_jobs(monkeypatch):
    """Already-indexed company jobs are not downloaded again on the next refresh."""
    import asyncio
    from app import sources
    recent = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
    calls = []

    async def fake_get_json(_client, url, timeout=None, **_params):
        calls.append(url)
        if url.endswith("/jobs"):
            return {"jobs": [{"id": 1, "title": "Backend Engineer", "first_published": recent, "absolute_url": "https://x/1"},
                             {"id": 2, "title": "Data Analyst", "first_published": recent, "absolute_url": "https://x/2"}]}
        return {"content": "&lt;p&gt;Python and SQL&lt;/p&gt;"}

    monkeypatch.setattr(sources, "_get_json", fake_get_json)
    monkeypatch.setattr(sources, "KNOWN_JOB_IDS", {"gh:acme:1"})
    out = asyncio.run(sources.greenhouse(None, "acme", "Acme", asyncio.Semaphore(2)))
    assert [d.get("_reuse", False) for d in out] == [True, False]
    assert out[1]["text"] == "Python and SQL"
    assert sum("/jobs/" in u for u in calls) == 1


def test_country_filter_excludes_other_countries_remote_jobs():
    p = build_profile(SAMPLE)
    jobs = [_job(1, "Backend Engineer", "Python Kafka", location="Remote - US", company="A"),
            _job(2, "Backend Engineer", "Python Kafka", location="Anywhere in the World", company="B"),
            _job(3, "Backend Engineer", "Python Kafka", remote=False, location="Pune, India", company="C")]
    for j in jobs:
        j.vec = nlp.tfidf(j.terms, {}, 5.0)
    res, _, _ = rank(p, jobs, {}, 5.0, hours=24, top=10, location="India")
    assert sorted(r["company"] for r in res) == ["B", "C"]


def test_keyed_sources_parse_with_mocked_apis(monkeypatch):
    """JSearch (LinkedIn/Indeed/...), Adzuna and Jooble connectors, against recorded response shapes."""
    import asyncio, dataclasses, httpx
    from app import sources
    ts = int(time.time()) - 7200
    iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))

    def handler(req: httpx.Request):
        if "jsearch" in req.url.host:
            assert req.headers["X-RapidAPI-Key"] == "k" and req.url.params["date_posted"] == "today"
            return httpx.Response(200, json={"data": [{
                "job_id": "abc", "job_publisher": "LinkedIn", "job_title": "Backend Engineer", "employer_name": "Acme",
                "job_apply_link": "https://www.linkedin.com/jobs/view/1", "job_city": "Bengaluru", "job_country": "IN",
                "job_is_remote": False, "job_posted_at_timestamp": ts, "job_description": "Python, Kafka, AWS",
                "job_employment_type": "FULLTIME"}]})
        if "adzuna" in req.url.host:
            assert req.url.params["max_days_old"] == "1"
            return httpx.Response(200, json={"results": [{"id": "9", "title": "Data Engineer", "company": {"display_name": "Beta"},
                "location": {"display_name": "Pune"}, "redirect_url": "https://adzuna/9", "created": iso, "description": "Spark SQL"}]})
        if "jooble" in req.url.host:
            return httpx.Response(200, json={"jobs": [{"id": 5, "title": "Python Developer", "company": "Gamma", "location": "Hyderabad",
                "link": "https://jooble/5", "updated": iso, "snippet": "Django", "source": "naukri.com"}]})
        return httpx.Response(404)

    s = dataclasses.replace(sources.settings, jsearch_key="k", adzuna_app_id="i", adzuna_app_key="k", jooble_key="j")
    monkeypatch.setattr(sources, "settings", s)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return (await sources.jsearch(c, "backend engineer", "24h", "Bengaluru"),
                    await sources.adzuna(c, "data engineer", "24h", "Pune"),
                    await sources.jooble(c, "python developer", "24h", "Hyderabad"))
    js, az, jb = asyncio.run(run())
    assert js[0]["source"] == "LinkedIn" and js[0]["url"].startswith("https://www.linkedin.com") and abs(js[0]["posted_at"] - ts) < 2
    assert az[0]["company"] == "Beta" and abs(az[0]["posted_at"] - ts) < 2
    assert jb[0]["source"] == "naukri.com" and jb[0]["location"] == "Hyderabad"
    assert set(k.split("|")[0] for k in sources.live_searches("backend engineer", "24h", "India")) == {"remotive", "jsearch", "adzuna", "jooble"}
