"""Generates docs/DreamJob_Build_and_Production_Guide.pdf.

    pip install reportlab
    python docs/build_guide.py
"""
from datetime import date
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, Preformatted,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
OUT = ROOT / "DreamJob_Build_and_Production_Guide.pdf"

INK = colors.HexColor("#111827")
INK2 = colors.HexColor("#374151")
INK3 = colors.HexColor("#6B7280")
COBALT = colors.HexColor("#111827")
MINT = colors.HexColor("#15803D")
HL = colors.HexColor("#D1D5DB")
PAPER = colors.HexColor("#F9FAFB")
LINE = colors.HexColor("#E5E7EB")

# ---------------------------------------------------------------- fonts (Segoe UI on Windows, Helvetica elsewhere)
BODY, BOLD, MONO = "Helvetica", "Helvetica-Bold", "Courier"
_win = Path("C:/Windows/Fonts")
try:
    pdfmetrics.registerFont(TTFont("Segoe", str(_win / "segoeui.ttf")))
    pdfmetrics.registerFont(TTFont("Segoe-Bold", str(_win / "segoeuib.ttf")))
    pdfmetrics.registerFont(TTFont("Consolas", str(_win / "consola.ttf")))
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily("Segoe", normal="Segoe", bold="Segoe-Bold", italic="Segoe", boldItalic="Segoe-Bold")
    BODY, BOLD, MONO = "Segoe", "Segoe-Bold", "Consolas"
except Exception:
    pass

S = {
    "title": ParagraphStyle("title", fontName=BOLD, fontSize=30, leading=35, textColor=INK, spaceAfter=10),
    "subtitle": ParagraphStyle("subtitle", fontName=BODY, fontSize=14, leading=20, textColor=INK2),
    "h1": ParagraphStyle("h1", fontName=BOLD, fontSize=21, leading=26, textColor=INK, spaceBefore=4, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=14.5, leading=19, textColor=INK, spaceBefore=12, spaceAfter=5),
    "h3": ParagraphStyle("h3", fontName=BOLD, fontSize=11.5, leading=15, textColor=COBALT, spaceBefore=8, spaceAfter=3),
    "body": ParagraphStyle("body", fontName=BODY, fontSize=10.3, leading=15.2, textColor=INK, spaceAfter=6, alignment=TA_LEFT),
    "small": ParagraphStyle("small", fontName=BODY, fontSize=8.8, leading=12, textColor=INK3),
    "cell": ParagraphStyle("cell", fontName=BODY, fontSize=9.2, leading=12.6, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName=BOLD, fontSize=9.2, leading=12.6, textColor=INK),
    "bullet": ParagraphStyle("bullet", fontName=BODY, fontSize=10.3, leading=15, textColor=INK, leftIndent=14, bulletIndent=2, spaceAfter=2),
    "step": ParagraphStyle("step", fontName=BODY, fontSize=10.3, leading=15, textColor=INK, leftIndent=20, bulletIndent=0, spaceAfter=3),
    "code": ParagraphStyle("code", fontName=MONO, fontSize=8.6, leading=11.6, textColor=INK, backColor=PAPER,
                           borderColor=LINE, borderWidth=0.6, borderPadding=7, leftIndent=7, rightIndent=7,
                           spaceBefore=4, spaceAfter=10),
    "callout": ParagraphStyle("callout", fontName=BODY, fontSize=10, leading=14.5, textColor=INK, backColor=colors.HexColor("#F3F4F6"),
                              borderColor=HL, borderWidth=0, borderPadding=8, leftIndent=8, rightIndent=8, spaceBefore=6, spaceAfter=10),
}

story = []
P = lambda t, s="body": story.append(Paragraph(t, S[s]))
H1 = lambda t: story.append(Paragraph(t, S["h1"]))
H2 = lambda t: story.append(Paragraph(t, S["h2"]))
H3 = lambda t: story.append(Paragraph(t, S["h3"]))
SP = lambda h=6: story.append(Spacer(1, h))


def bullets(items):
    for it in items:
        story.append(Paragraph(it, S["bullet"], bulletText="•"))
    SP(4)


def steps(items):
    for i, it in enumerate(items, 1):
        story.append(Paragraph(it, S["step"], bulletText=f"{i}."))
    SP(4)


def code(text):
    story.append(Preformatted(text.strip("\n"), S["code"]))


def callout(text):
    story.append(Paragraph(text, S["callout"]))


def table(rows, widths, header=True):
    data = [[Paragraph(str(c), S["cellb" if (header and r == 0) else "cell"]) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
          ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
          ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), PAPER), ("LINEBELOW", (0, 0), (-1, 0), 1, INK)]
    t.setStyle(TableStyle(st))
    story.append(t)
    SP(10)


def image(name, width_mm, caption=None):
    path = ASSETS / name
    if not path.exists():
        return
    from reportlab.lib.utils import ImageReader
    iw, ih = ImageReader(str(path)).getSize()
    w = width_mm * mm
    items = [Image(str(path), width=w, height=w * ih / iw)]
    if caption:
        items.append(Paragraph(caption, S["small"]))
    story.append(KeepTogether(items + [Spacer(1, 8)]))


def architecture():
    d = Drawing(170 * mm, 92 * mm)
    W, H = 170 * mm, 92 * mm

    def box(x, y, w, h, title, sub, fill=colors.white, stroke=INK, tc=INK):
        d.add(Rect(x, y, w, h, rx=6, ry=6, fillColor=fill, strokeColor=stroke, strokeWidth=1))
        d.add(String(x + 8, y + h - 15, title, fontName=BOLD, fontSize=9.5, fillColor=tc))
        for i, line in enumerate(sub):
            d.add(String(x + 8, y + h - 28 - i * 11, line, fontName=BODY, fontSize=7.8, fillColor=INK2 if tc == INK else tc))

    def arrow(x1, y1, x2, y2, color=INK3):
        d.add(Line(x1, y1, x2, y2, strokeColor=color, strokeWidth=1.2))
        import math
        a = math.atan2(y2 - y1, x2 - x1)
        L = 6
        d.add(Polygon([x2, y2, x2 - L * math.cos(a - .4), y2 - L * math.sin(a - .4),
                       x2 - L * math.cos(a + .4), y2 - L * math.sin(a + .4)], fillColor=color, strokeColor=color))

    # columns
    box(0, H - 62, 120, 56, "Browser", ["index.html, app.js", "upload + preferences", "renders ranked jobs"], fill=PAPER)
    box(165, H - 75, 150, 70, "FastAPI app", ["POST /api/analyze", "POST /api/match", "rate limit, gzip, static", "uvicorn, 2 workers"], fill=INK, stroke=INK, tc=colors.white)
    box(365, H - 62, 115, 56, "Résumé reader", ["pypdf / python-docx", "in memory only"])
    box(365, H - 130, 115, 56, "Profile builder", ["skills, titles,", "years, level, keywords"])
    box(165, 8, 150, 92, "Job index (memory)", ["~8,000 jobs, last month", "pre-computed skills,", "titles, levels, TF-IDF", "disk snapshot for", "instant restarts"], fill=colors.HexColor("#F3F4F6"), stroke=INK3)
    box(0, 8, 120, 92, "Job sources", ["~150 company career", "sites (hourly)", "6 job boards (30 min)", "optional: JSearch,", "Adzuna, Jooble"], fill=PAPER)
    box(365, 8, 115, 70, "Matcher", ["filter by window,", "location, remote", "score 0-100 + reasons", "top 3/10/20/30"], fill=colors.HexColor("#F0FDF4"), stroke=MINT)
    # arrows
    arrow(120, H - 34, 165, H - 34, COBALT)
    arrow(315, H - 30, 365, H - 30, COBALT)
    arrow(422, H - 62, 422, H - 74, COBALT)
    arrow(422, H - 130, 422, 78, COBALT)
    arrow(120, 54, 165, 54)
    arrow(315, 44, 365, 44)
    arrow(240, H - 75, 240, 100)
    d.add(String(244, H - 92, "live search per role (cached, shared)", fontName=BODY, fontSize=7.4, fillColor=INK3))
    d.add(String(125, 60, "background", fontName=BODY, fontSize=7, fillColor=INK3))
    return d


def on_page(canvas, doc):
    canvas.saveState()
    w, h = A4
    if doc.page > 1:
        logo = ASSETS.parent.parent / "static" / "logo-512.png"
        if logo.exists():
            canvas.drawImage(str(logo), 18 * mm, h - 14 * mm, 6 * mm, 6 * mm, mask="auto")
        canvas.setFont(BOLD, 8.5)
        canvas.setFillColor(INK)
        canvas.drawString(26 * mm, h - 12 * mm, "DreamJob")
        canvas.setFont(BODY, 8.5)
        canvas.setFillColor(INK3)
        canvas.drawRightString(w - 18 * mm, h - 12 * mm, "Build and production guide")
        canvas.setStrokeColor(LINE)
        canvas.line(18 * mm, h - 16 * mm, w - 18 * mm, h - 16 * mm)
        canvas.drawRightString(w - 18 * mm, 11 * mm, f"Page {doc.page}")
    canvas.restoreState()


# =====================================================================================================
# COVER
# =====================================================================================================
SP(40)
image("logo-lockup.png", 120)
SP(30)
P("Build and Production Guide", "title")
P("Everything about the project: what it does, how it was built, how it was tested, and a "
  "step-by-step plan to put it online for the public at zero cost.", "subtitle")
SP(30)
table([["Version", "1.1 (sources, date accuracy and UI update)"], ["Date", date.today().strftime("%d %B %Y")],
       ["Running cost", "$0 per month (free tiers only)"],
       ["Recommended host", "Hugging Face Spaces (free CPU: 2 vCPU, 16 GB RAM)"],
       ["Stack", "Python 3.12, FastAPI, plain HTML/CSS/JS, Docker"]], [45 * mm, 120 * mm], header=False)
story.append(PageBreak())

# ---------------------------------------------------------------- contents
H1("Contents")
toc = [
    ("1", "What DreamJob is"), ("2", "The logo and visual identity"), ("3", "How it was built"),
    ("4", "Quality, speed and capacity: test results"), ("5", "Going live: step-by-step production guide"),
    ("6", "After launch: monitoring, upkeep and troubleshooting"), ("7", "Known limitations"),
    ("8", "Next steps and roadmap"), ("9", "Cost summary"), ("10", "What changed in version 1.1"),
]
table([["Part", "Section"]] + [list(r) for r in toc], [18 * mm, 150 * mm])
story.append(PageBreak())

# =====================================================================================================
# 1. WHAT IT IS
# =====================================================================================================
H1("1. What DreamJob is")
P("Job seekers waste hours scrolling boards that are full of old postings and roles that don't fit them. "
  "<b>DreamJob</b> turns that around: you upload your résumé once, and it reads your skills, job titles and "
  "years of experience, then ranks freshly posted jobs by how well they fit you.")
H2("What a user can do")
bullets([
    "Upload a résumé as <b>PDF, DOCX or TXT</b> (up to 5 MB), or paste the text.",
    "Choose how recent the jobs must be: <b>last 24 hours, 48 hours, 72 hours, 1 week or 1 month</b>.",
    "Choose how many results to see: <b>top 3, 10, 20 or 30</b>.",
    "Optionally filter by <b>location</b> (e.g. India, Berlin, USA) and <b>remote only</b>.",
    "See for each job: a <b>match score (0-100%)</b>, plain-language reasons, the skills they match "
    "(highlighted), the skills the job also asks for (a learning list), salary when published, and a link to apply.",
    "Correct the profile (role, years, add or remove skills) and change filters: results update instantly "
    "without uploading again.",
    "Open the same search on <b>LinkedIn, Indeed, Naukri, Glassdoor and Google Jobs</b> with one click, with the "
    "role, location and date filter already applied.",
])
H2("Principles")
bullets([
    "<b>Free to run.</b> No paid AI APIs, no database, free job APIs and free hosting.",
    "<b>Private.</b> Résumés are read in memory and discarded; nothing about the user is stored.",
    "<b>Fast.</b> A warm search returns in about 0.25 seconds; 100 simultaneous uploads all succeed.",
    "<b>Honest.</b> Every score comes with its reasons, every job shows its exact posting date and links to the "
    "original posting. Only sources that report the real posting date are used.",
])
image("screenshot-home.png", 165, "The search screen.")
image("screenshot-results.png", 165, "Results: filters across the top apply instantly; the editable profile and links to other job sites are on the right.")
story.append(PageBreak())

# =====================================================================================================
# 2. LOGO
# =====================================================================================================
H1("2. The logo and visual identity")
P("The logo is a <b>DJ</b> monogram (DreamJob) on a dark rounded badge. The top of the <b>J</b> is drawn "
  "as a green <b>check mark</b>: the letter itself says <i>job found</i>. The interface follows the same restraint: "
  "white and neutral greys, black buttons, and green used only for match scores and matched skills.")
image("logo-lockup.png", 110)
table([
    ["Token", "Colour", "Used for"],
    ["Ink", "#111827", "Text, logo badge, buttons, selected filters"],
    ["Grey", "#6B7280", "Secondary text"],
    ["Border", "#E5E7EB", "Card and input borders"],
    ["Green", "#22C55E / #15803D", "The check in the logo; match scores and matched skills"],
    ["White", "#FFFFFF", "Page background (the site always uses the light theme)"],
], [35 * mm, 30 * mm, 100 * mm])
P("Type: the device's system font (Segoe UI on Windows, San Francisco on Apple devices, Roboto on Android). It looks "
  "native, loads instantly and needs no font download. The interface works down to phone width, has visible "
  "keyboard focus and respects reduced-motion settings.")
P("Logo files: <font face='%s'>static/logo.svg</font> (vector, use this wherever possible), "
  "<font face='%s'>static/favicon.svg</font>, <font face='%s'>static/logo-512.png</font> (social preview) and "
  "<font face='%s'>docs/assets/logo-lockup.png</font> (logo with wordmark)." % (MONO, MONO, MONO, MONO))
story.append(PageBreak())

# =====================================================================================================
# 3. HOW IT WAS BUILT
# =====================================================================================================
H1("3. How it was built")
H2("3.1 Architecture")
P("DreamJob is one small web service. The same process serves the website and the API, keeps an index of recent "
  "jobs in memory, and does all matching itself. There is no database and no external AI service.")
story.append(architecture())
SP(8)
H2("3.2 What happens when a user clicks “Find matching jobs”")
steps([
    "The browser sends the file and preferences to <b>POST /api/analyze</b>.",
    "The server checks the visitor's rate limit (30 searches per minute) and the file size (5 MB).",
    "The <b>résumé reader</b> extracts text: <i>pypdf</i> for PDF, <i>python-docx</i> for DOCX (including tables). "
    "Scanned or password-protected PDFs get a clear error asking for another format.",
    "The <b>profile builder</b> finds skills, likely job titles, years of experience, seniority level and the most "
    "important keywords.",
    "In parallel, a <b>live search</b> for the user's main role runs against Remotive, plus JSearch (LinkedIn, Indeed, "
    "Glassdoor, Naukri via Google for Jobs), Adzuna and Jooble when their keys are set. It is capped at 4 seconds and "
    "cached (JSearch for 6 hours, to protect its small free quota); identical searches from different users share one "
    "upstream request.",
    "The <b>matcher</b> filters the index plus live results by time window, location and remote, removes duplicates, "
    "scores every remaining job and returns the top N with reasons.",
    "The browser shows the results. Changing filters or editing the profile calls <b>POST /api/match</b> with the "
    "profile JSON, so the résumé is never uploaded again.",
])
H2("3.3 The matching method")
P("Each job gets four sub-scores between 0 and 1, which are combined into a percentage:")
table([
    ["Signal", "Weight", "How it is measured"],
    ["Skills", "38%", "55% x (share of the job's skills you have) + 45% x (how many you match, full credit at 4). "
                      "Generic skills such as Git, Excel or 'communication' count about a third as much."],
    ["Title", "32%", "1.0 if one of your titles appears in the job title; otherwise word overlap of the core title "
                     "words (synonyms like developer = engineer); at least 0.5 when both are in the same role family "
                     "(20 families such as software, data, design, sales, finance, healthcare)."],
    ["Text", "17%", "TF-IDF cosine similarity between your résumé keywords and the job text, using word rarity "
                    "learned from the whole job index."],
    ["Experience", "13%", "Your years against the job's required years ('5+ years of experience'), or against the "
                          "seniority in the title (intern, junior, senior, lead, director)."],
], [26 * mm, 18 * mm, 124 * mm])
P("Two safeguards keep results sensible: a job that is a different kind of role <i>and</i> shares at most one "
  "skill is cut to about half its score, and at most three jobs per company are shown. If no title is found in the "
  "résumé, the weights shift to skills (55%), text (30%) and experience (15%). The final value goes through a "
  "gentle curve (raw<super>0.8</super>) so that genuinely strong fits read in the 80s and 90s.")
P("Skill detection uses a hand-curated vocabulary of about 300 skills with aliases (k8s, React.js, Postgres, "
  "C/C++, CI/CD...). It matches the longest phrase first, keeps symbols such as C++, C#, .NET and Node.js intact, "
  "and treats words that are also ordinary English (Go, R, Swift, Excel, Rust) as skills only when written with "
  "the right capitalisation. Years of experience are calculated by merging the date ranges in the work history, "
  "ignoring lines about education.")
H2("3.4 Job sources")
P("Rule number one: a source is only used if it reports the date the job was really posted. Otherwise the time "
  "filters cannot be trusted.")
table([
    ["Source", "What it adds", "Posting date from", "Key"],
    ["Company career sites", "~150 employers (Stripe, Databricks, MongoDB, Okta, Zscaler, Freshworks, Meesho, CRED, "
     "Rubrik, ServiceNow, Bosch...) via the official job APIs of Greenhouse, Lever, Ashby and SmartRecruiters",
     "The employer's own first-publish date", "No"],
    ["Remotive", "Remote tech jobs (feed + live search)", "Board posting date", "No"],
    ["Remote OK", "Remote jobs (slow API, read in the background)", "Board posting date", "No"],
    ["We Work Remotely", "Remote jobs (RSS feed)", "Board posting date", "No"],
    ["Jobicy, Working Nomads", "Remote jobs", "Board posting date", "No"],
    ["Arbeitnow", "Europe, mostly Germany", "Board posting date", "No"],
    ["JSearch (optional)", "Google for Jobs: LinkedIn, Indeed, Glassdoor, Naukri, company sites", "Publisher's date", "Free"],
    ["Adzuna (optional)", "On-site jobs in 19 countries incl. India", "Adzuna posting date", "Free"],
    ["Jooble (optional)", "Large aggregator with India coverage", "Jooble update date", "Free"],
], [32 * mm, 72 * mm, 44 * mm, 14 * mm])
P("<b>LinkedIn.</b> LinkedIn has no public jobs API, and its User Agreement forbids scraping; it also blocks "
  "cloud servers quickly, so a scraper would break within days on a free host and could get the project banned. "
  "DreamJob therefore reaches LinkedIn jobs in two legitimate ways: through JSearch (Google for Jobs) when a key is "
  "set, and through the <b>Search other job sites</b> panel, which opens LinkedIn, Indeed, Naukri, Glassdoor and "
  "Google Jobs with the role, location and date filter already filled in.")
P("<b>Himalayas was removed.</b> We compared its dates with the employers' own Greenhouse boards: Himalayas "
  "reported the date it re-imported a job, which lagged the real posting by 1-4 days for most jobs and by up to four "
  "weeks for some (a Stripe job first published on 16 Oct appeared as 14 Nov). That is why 'last 24 hours' showed "
  "month-old jobs in version 1.0.")
P("These APIs ask for attribution and a link back. DreamJob names the source on every result, links to the original "
  "posting and does not republish jobs elsewhere. Read each provider's terms before launch.")
H2("3.5 Designed for 100 users at once")
bullets([
    "<b>Index in memory.</b> Jobs are fetched in the background and pre-processed once (skills, title family, "
    "seniority, TF-IDF vector), so a search only does cheap comparisons.",
    "<b>Each source lands independently.</b> A slow board (Remote OK) never delays the others; a failing board keeps "
    "its previous jobs.",
    "<b>Shared, cached live search.</b> 100 users searching for 'data analyst' trigger one upstream call, not 100.",
    "<b>Pre-screening.</b> Jobs that share no skill and no role family are skipped before scoring.",
    "<b>Heavy work off the event loop.</b> PDF parsing and ranking run in a thread pool; the server keeps accepting requests.",
    "<b>Multiple workers.</b> Two Uvicorn workers use both CPUs on Hugging Face Spaces.",
    "<b>Snapshot on disk.</b> The index is saved after each refresh, so a restart serves jobs immediately.",
    "<b>Small, cached frontend.</b> About 30 KB of HTML/CSS/JS, gzip-compressed, no framework.",
])
H2("3.6 Security and privacy")
bullets([
    "Résumés are never written to disk or logs; only the public job index is saved.",
    "Upload limits: 5 MB, at most 12 PDF pages and 60,000 characters of text.",
    "Rate limit per visitor IP. The IP is read from the address appended by the host's proxy, so a client cannot "
    "dodge the limit by faking the X-Forwarded-For header.",
    "All job data is HTML-escaped before display, and only http(s) links are rendered, which blocks script "
    "injection from third-party job text.",
    "Security headers (nosniff, referrer policy); the container runs as a non-root user.",
    "Input validation on every API field (allowed windows, top values, list sizes).",
])
H2("3.7 Code map")
table([
    ["File", "Responsibility"],
    ["app/main.py", "API routes, rate limiting, headers, static files, startup/shutdown"],
    ["app/index.py", "Job index, background refresh, per-source updates, live-search cache, disk snapshot"],
    ["app/sources.py", "One connector per source (company sites, job boards, keyed APIs), all normalised to one format"],
    ["app/companies.py", "The verified list of ~150 company career boards (add more with one line each)"],
    ["app/matcher.py", "Résumé reading, profile building, scoring, explanations and ranking"],
    ["app/nlp.py", "Tokenizer, skill/title/seniority/experience extraction, TF-IDF"],
    ["app/skills.py", "Skill vocabulary (with aliases) and job titles by role family"],
    ["app/config.py", "All settings, read from environment variables"],
    ["static/", "index.html, styles.css, app.js, logo and favicon"],
    ["tests/test_core.py", "13 offline tests: parsing, ranking, strict time windows, filters, sources, API, rate limit"],
    ["scripts/load_test.py", "Simulates N users uploading at the same moment"],
    ["Dockerfile, render.yaml", "Container and Render blueprint"],
    [".github/workflows/", "ci.yml runs tests on every push; keepalive.yml pings the site"],
], [45 * mm, 123 * mm])
story.append(PageBreak())

# =====================================================================================================
# 4. TESTS
# =====================================================================================================
H1("4. Quality, speed and capacity: test results")
P("Measured on 17 November 2026 on a Windows laptop, against the real job sources.")
table([
    ["Check", "Result"],
    ["Automated tests (pytest)", "13 passed"],
    ["Jobs indexed after a full refresh", "about 7,800 (company sites 6,500; boards 2,500); 0 of 153 company boards failing"],
    ["Jobs per window", "24 h: 1,147   48 h: 1,416   72 h: 1,898   1 week: 3,932   1 month: 7,779"],
    ["Strict time windows (browser test)", "Oldest job shown: 24 h window 15.6 h; 48 h 44.5 h; 72 h 65 h; 1 week 149 h; 1 month 702 h"],
    ["Fast filter clicks (24 h, then 1 month, then 48 h)", "Screen ends on the 48 h results; older responses are discarded"],
    ["Top 3 / 10 / 20 / 30", "Exactly 3 / 10 / 20 / 30 jobs shown"],
    ["Location 'India' (Enter key) and Remote only", "Only Indian cities or worldwide-remote jobs; 'Remote - US' jobs excluded"],
    ["First full crawl of company sites", "about 5 minutes in the background; later refreshes only download new jobs"],
    ["Single search, warm", "0.3 seconds"],
    ["100 users uploading at the same instant (2 workers)", "100 of 100 succeeded; p95 2.8-3.7 s"],
    ["Memory per worker", "about 185 MB"],
    ["Browser test", "No JavaScript errors; no sideways scrolling at phone width"],
], [70 * mm, 98 * mm])
H2("What the matcher returned for the sample résumé")
P("Sample: a senior backend engineer with Python, Go, Kafka, Kubernetes and AWS. Top results were senior backend "
  "roles at 85-90% from company career sites and job boards, with skills like Kotlin or BigQuery listed under "
  "'Not on your résumé'. Unrelated roles (nursing, design) scored under 40%.")
callout("<b>What “100 users at a time” means here.</b> 100 people using the site at once is easy: most are reading "
        "results, not uploading. The test above is the extreme case, with 100 uploads in the same second, and every "
        "request still finished in under 4 seconds on 2 CPUs.")
story.append(PageBreak())

# =====================================================================================================
# 5. PRODUCTION
# =====================================================================================================
H1("5. Going live: step-by-step production guide")
P("Follow the steps in order. You need about an hour, a GitHub account and a Hugging Face account, and no credit card.")
H2("Step 0. Choose where to host")
table([
    ["Host", "Free resources", "Sleeps?", "Best for"],
    ["<b>Hugging Face Spaces</b> (recommended)", "2 vCPU, 16 GB RAM, Docker", "After about 48 h with no visitors; wakes on the next visit",
     "Real traffic, 100 concurrent users"],
    ["Render (free web service)", "0.1 CPU, 512 MB RAM", "After 15 min idle; wakes in about 30-60 s",
     "Backup host, custom domain"],
    ["Oracle Cloud Always Free (advanced)", "Up to 4 ARM cores, 24 GB RAM VM", "No",
     "Heavy traffic; requires a card for identity check and manual server setup"],
], [38 * mm, 38 * mm, 48 * mm, 44 * mm])
P("Free-tier limits change from time to time; check each provider's pricing page on the day you deploy.", "small")

H2("Step 1. Put the code on GitHub")
steps([
    "Create a free account at github.com and click <b>New repository</b>. Name it <b>dreamjob</b>, choose Public or "
    "Private, and do not add a README (the project has one).",
    "Install Git if needed (git-scm.com). Then, in the project folder, run:",
])
code("""
cd D:\\Agents\\DreamJob
git init
git add .
git commit -m "DreamJob v1.0"
git branch -M main
git remote add origin https://github.com/<your-username>/dreamjob.git
git push -u origin main
""")
P("The <font face='%s'>.gitignore</font> already excludes the virtual environment, caches and the job snapshot. "
  "On GitHub, open the <b>Actions</b> tab: the CI workflow runs the tests on every push." % MONO)

H2("Step 2. Deploy on Hugging Face Spaces (recommended)")
steps([
    "Create a free account at huggingface.co.",
    "Create an access token: <b>Settings > Access Tokens > Create new token</b>, type <b>Write</b>. Copy it; Git "
    "uses it as your password.",
    "Click <b>New > Space</b>. Name: <b>dreamjob</b>. SDK: <b>Docker</b>, template <b>Blank</b>. Hardware: "
    "<b>CPU basic (free)</b>. Visibility: <b>Public</b>. Create the Space.",
    "Hugging Face reads its settings from the top of README.md. Copy the block between the two <font face='%s'>---</font> "
    "lines in <font face='%s'>deploy/huggingface/README.md</font> and paste it at the very top of the project's "
    "README.md (GitHub shows it as a small table, which is harmless). Commit the change." % (MONO, MONO),
    "Push the code to the Space:",
])
code("""
git add README.md
git commit -m "Add Hugging Face Space settings"
git remote add space https://huggingface.co/spaces/<hf-username>/dreamjob
git push space main
# username: your HF username, password: the Write token from step 2
""")
steps([
    "Open the Space page. The status shows <b>Building</b> (2-4 minutes), then <b>Running</b>.",
    "Your public address is <b>https://&lt;hf-username&gt;-dreamjob.hf.space</b>. The first minute after start is "
    "spent collecting jobs; the header shows how many are indexed.",
    "Optional settings (Adzuna key, refresh interval) go under <b>Settings > Variables and secrets</b>. Put keys under "
    "<b>Secrets</b>. The Space restarts automatically.",
])
P("To update the live site later, commit your change and run <font face='%s'>git push origin main</font> (GitHub) "
  "and <font face='%s'>git push space main</font> (the Space)." % (MONO, MONO))

H2("Step 3. Alternative: deploy on Render")
steps([
    "Create a free account at render.com and connect your GitHub account.",
    "Click <b>New > Blueprint</b> and choose the dreamjob repository. Render reads <font face='%s'>render.yaml</font> "
    "(Docker, free plan, 1 worker, health check)." % MONO,
    "Click <b>Apply</b>. After the build, the site is live at <b>https://dreamjob-xxxx.onrender.com</b>.",
    "Free Render services sleep after 15 minutes without visitors. To keep it awake, use Step 5.",
])
P("Render's free plan has a much smaller CPU (0.1). It is fine for light use, but use Hugging Face for real traffic.", "small")

H2("Step 4. Add LinkedIn, Indeed and local jobs (optional, free keys)")
P("Without keys, DreamJob already searches ~150 company career sites and six job boards. To add LinkedIn, Indeed, "
  "Glassdoor and Naukri listings, and more on-site jobs in India, add any of these free keys as <b>Secrets</b> in your "
  "host's settings. The app restarts and uses them automatically.")
H3("JSearch: LinkedIn, Indeed, Glassdoor, Naukri (via Google for Jobs)")
steps([
    "Create a free account at <b>rapidapi.com</b> and open the <b>JSearch</b> API page.",
    "Click <b>Subscribe to Test</b> and choose the free <b>Basic</b> plan (about 200 requests a month).",
    "Copy the <b>X-RapidAPI-Key</b> shown in the code examples and save it as secret <b>JSEARCH_API_KEY</b>.",
    "Results are cached per role, location and date window for 6 hours (<b>JSEARCH_CACHE_MINUTES</b>), so the "
    "free quota lasts. Heavy public traffic would need a paid plan or a longer cache.",
])
H3("Adzuna: on-site jobs in 19 countries")
steps([
    "Register at <b>developer.adzuna.com</b> and create an application; copy the <b>App ID</b> and <b>App Key</b>.",
    "Add secrets <b>ADZUNA_APP_ID</b> and <b>ADZUNA_APP_KEY</b>, and variable <b>ADZUNA_COUNTRY</b> (in, us, gb, de...).",
])
H3("Jooble: large aggregator")
steps([
    "Request a key at <b>jooble.org/api/about</b>; it arrives by email.",
    "Add secret <b>JOOBLE_API_KEY</b>. Usage limits are set per key by Jooble.",
])
P("Set <b>DEFAULT_COUNTRY</b> / <b>DEFAULT_COUNTRY_NAME</b> (default in / India) to your users' country. "
  "Free-plan limits change from time to time; check each provider's page.", "small")

H2("Step 5. Keep it awake and get alerts (free)")
steps([
    "Create a free account at <b>uptimerobot.com</b>. Add an <b>HTTP(s)</b> monitor for "
    "<font face='%s'>https://&lt;your-site&gt;/api/health</font> every 5 minutes, with email alerts." % MONO,
    "This keeps a Render service awake and tells you if the site goes down.",
    "Alternative without new accounts: in GitHub, go to <b>Settings > Secrets and variables > Actions > Variables</b> "
    "and add <b>SITE_URL</b> with your site address. The included <font face='%s'>keepalive.yml</font> workflow "
    "then pings the site every 10 minutes." % MONO,
])
P("Render's free plan includes 750 instance hours a month, which is enough for one service awake all month. Use "
  "pings to keep a public service available, not to work around a provider's rules; if a provider changes its "
  "policy, follow it.", "small")

H2("Step 6. Check everything before you share the link")
table([
    ["Check", "How", "Expected"],
    ["Site is up", "Open /api/health", "\"status\": \"ok\" and jobs above 1000"],
    ["All sources work", "Open /api/stats", "Each source shows ok: true (Remote OK may finish a minute later)"],
    ["Full flow", "Upload a PDF résumé and a DOCX résumé", "Results in a few seconds, sensible top jobs"],
    ["Every option", "Try 24h, 48h, 72h, 1 week, 1 month; top 3, 10, 20, 30", "Counts and lists change accordingly"],
    ["Filters", "Location 'India', then Remote only", "Only matching or worldwide-remote jobs"],
    ["Phone", "Open the site on your phone", "No sideways scrolling; buttons easy to tap"],
    ["Errors", "Upload an image or an empty file", "A clear message, no crash"],
    ["Load", "Run the load test (below)", "All 200 responses, p95 about 2-3 s"],
], [30 * mm, 70 * mm, 68 * mm])
P("Load test against the live site. The rate limiter treats all test requests as one visitor, so raise the limit "
  "first (variable <b>RATE_LIMIT_PER_MINUTE=10000</b>), run the test, then remove the variable:")
code("""
python scripts/load_test.py --url https://<your-site> --users 100
""")

H2("Step 7. Launch")
bullets([
    "Share the link with friends first and ask for feedback on the match quality for their résumés.",
    "Post it on LinkedIn, Reddit (r/jobs, r/developersIndia, r/cscareerquestions; check each community's rules), "
    "college groups and Telegram/WhatsApp job channels.",
    "The page already has a title, description and preview image, so links look good when shared.",
    "Optional custom domain: a domain costs about $10 a year (the only non-free item). Render lets you attach a "
    "custom domain on the free plan; on Hugging Face, use the free hf.space address or check its current custom-domain options.",
])
story.append(PageBreak())

# =====================================================================================================
# 6. OPERATIONS
# =====================================================================================================
H1("6. After launch: monitoring, upkeep and troubleshooting")
H2("Monitoring")
bullets([
    "<b>/api/stats</b> shows the number of indexed jobs, the last refresh time and each source's status and last error.",
    "<b>Logs:</b> the Hugging Face Space 'Logs' tab or the Render dashboard. Each refresh logs a line such as "
    "'index refreshed: 3259 jobs in 90.6s', and failing sources log a warning.",
    "<b>Uptime alerts:</b> UptimeRobot (Step 5).",
    "<b>Privacy-friendly visitor counts (optional, free):</b> Cloudflare Web Analytics or GoatCounter, added as one script tag in index.html.",
])
H2("Regular upkeep")
table([
    ["When", "Task"],
    ["Weekly", "Glance at /api/stats; check that every source is ok."],
    ["Monthly", "Update dependencies in requirements.txt, run pytest, push. (Enable GitHub Dependabot to get update pull requests automatically.)"],
    ["When a source changes", "Edit its function in app/sources.py; the rest of the app is unaffected."],
    ["When users report missed skills", "Add them (with aliases) to SKILLS_RAW in app/skills.py."],
], [40 * mm, 128 * mm])
H2("Troubleshooting")
table([
    ["Symptom", "Likely cause", "Fix"],
    ["Header says 'Collecting jobs'", "Fresh start with no snapshot", "Wait about a minute; company sites follow within ~5 minutes"],
    ["A company's jobs disappear", "The company changed hiring system", "Fix or remove its line in app/companies.py"],
    ["A source shows ok: false", "That API is down or slow", "Nothing; old jobs are kept and it retries every 30 minutes"],
    ["Few results for 24 hours", "Narrow role or strict filters", "Use 1 week, clear location, add an Adzuna key"],
    ["'No readable text was found'", "Scanned (image) PDF", "Upload DOCX or paste text (OCR is on the roadmap)"],
    ["429 'Too many searches'", "Rate limit reached", "Wait a minute, or raise RATE_LIMIT_PER_MINUTE"],
    ["First visit takes ~1 minute", "Free host was asleep", "Set up the keep-alive ping (Step 5)"],
    ["Out of memory on a 512 MB host", "Too many workers or jobs", "WEB_CONCURRENCY=1 and ARBEITNOW_PAGES=10"],
    ["Space build fails", "README settings block missing", "Make sure README.md starts with the --- block (Step 2.4)"],
], [45 * mm, 50 * mm, 73 * mm])
story.append(PageBreak())

# =====================================================================================================
# 7. LIMITATIONS
# =====================================================================================================
H1("7. Known limitations")
bullets([
    "<b>LinkedIn only through legitimate routes.</b> Without a JSearch key, LinkedIn jobs are reached through the "
    "'Search other job sites' links, not inside DreamJob's ranked list. JSearch's free quota (~200 requests a month) "
    "suits a personal or small public tool; heavy traffic needs a paid plan.",
    "<b>Coverage follows the company list.</b> The ~150 company boards lean towards tech employers; most are global "
    "companies, and about 1,200 of their jobs are in India. Adding Indian employers to app/companies.py, or adding "
    "Adzuna/JSearch keys, widens coverage.",
    "<b>Arbeitnow is mostly German jobs.</b> They match on skills but are rarely relevant in India; use the Location "
    "filter, or set ARBEITNOW_PAGES=0 to drop them.",
    "<b>Rule-based reading.</b> Skills outside the vocabulary of about 300 are not detected automatically; users can "
    "add them in the profile panel.",
    "<b>The rate limit is per worker process</b> (about 60 searches a minute per visitor with 2 workers).",
    "<b>Free hosts sleep</b>, and the first company-site crawl after a fresh deploy takes about five minutes.",
])

H1("8. Next steps and roadmap")
P("Ordered by value for the effort. Everything listed can still be done for free.")
H2("Next (1-2 weeks)")
table([
    ["Improvement", "Why", "How (free)"],
    ["More Indian employers", "More on-site jobs in India", "Find more Greenhouse, Lever, Ashby and SmartRecruiters boards and add one line each to app/companies.py"],
    ["OCR for scanned PDFs", "Some résumés are images", "Add Tesseract to the Docker image and use it when a PDF has no text"],
    ["Share results", "Users want to save or send their list", "'Copy link' that encodes the profile in the URL, or 'Download as PDF'"],
    ["Feedback buttons", "Learn where matching is wrong", "'Good match / not relevant' per job, counted in a free Google Form or Supabase table"],
], [38 * mm, 50 * mm, 80 * mm])
H2("Later (1-2 months)")
table([
    ["Improvement", "Why", "How (free)"],
    ["Semantic re-ranking", "Understands meaning, not just words (e.g. 'built pipelines' is close to 'data engineering')",
     "Small embedding model (e.g. all-MiniLM-L6-v2) running on the free 16 GB Space; re-rank the top 100 jobs"],
    ["Larger skill vocabulary", "Detect more skills in every field", "Import the free EU ESCO skills taxonomy"],
    ["Daily job alerts by email", "Users come back without searching", "Supabase free tier for sign-up + Brevo or Resend free email tier, sent by a scheduled GitHub Action"],
    ["Shared cache and exact rate limit", "Consistent across workers and restarts", "Upstash Redis free tier"],
    ["Skill-gap advice", "Turn 'Also asks for' into a learning plan", "Count missing skills across a user's top 30 and link to free courses"],
], [38 * mm, 50 * mm, 80 * mm])
H2("Growth")
bullets([
    "Languages: translate the interface (Hindi, Telugu, Tamil...) and add skill aliases in those languages.",
    "Accessibility audit with a screen reader before a wide launch.",
    "A browser extension that scores any job page you visit against your saved profile.",
    "If traffic grows past the free tier: move to Oracle Cloud Always Free, or a paid Hugging Face CPU upgrade. "
    "The app is a single container, so moving is a 10-minute job.",
])
story.append(PageBreak())

# =====================================================================================================
# 9. COST
# =====================================================================================================
H1("9. Cost summary")
table([
    ["Item", "Service", "Cost"],
    ["Hosting", "Hugging Face Spaces (CPU basic) or Render free", "$0"],
    ["Job data", "Company career site APIs, Remotive, Remote OK, We Work Remotely, Jobicy, Working Nomads, Arbeitnow", "$0"],
    ["LinkedIn, Indeed, Glassdoor (optional)", "JSearch free plan (~200 requests a month)", "$0"],
    ["On-site jobs (optional)", "Adzuna developer key", "$0"],
    ["Code hosting and CI", "GitHub + GitHub Actions", "$0"],
    ["Uptime monitoring", "UptimeRobot free / GitHub Actions ping", "$0"],
    ["Matching / AI", "Built-in matcher (no paid API)", "$0"],
    ["Fonts", "The device's system font", "$0"],
    ["Custom domain (optional)", "Any registrar", "about $10 per year"],
    ["<b>Total</b>", "", "<b>$0 per month</b>"],
], [45 * mm, 90 * mm, 33 * mm])
SP(10)
callout("<b>Quick start recap.</b> 1) Push the code to GitHub. 2) Create a Docker Space on Hugging Face. 3) Add the settings "
        "block to README.md and push to the Space. 4) Optionally add a JSearch key for LinkedIn and Indeed jobs. 5) Add an UptimeRobot monitor. "
        "6) Run the launch checklist, then share the link.")

story.append(PageBreak())
H1("10. What changed in version 1.1")
P("Changes made after testing version 1.0 in real use:")
table([
    ["Problem reported", "Cause found", "Fix"],
    ["'Last 24 hours' showed month-old jobs", "Himalayas reports its re-import date, not the real posting date (gaps of up to 4 weeks)",
     "Himalayas removed; ~150 company career sites added, which report the employer's own publish date. Each job now shows its exact date."],
    ["Results came almost only from Himalayas", "The live search used Himalayas only, and the other free boards are small",
     "Company career sites, We Work Remotely and Working Nomads added: ~7,800 jobs from 7 sources, with a per-source count above the results"],
    ["Wanted LinkedIn and jobs from everywhere", "LinkedIn has no public API and forbids scraping",
     "Optional JSearch key (LinkedIn, Indeed, Glassdoor, Naukri via Google for Jobs), plus one-click searches on LinkedIn, "
     "Indeed, Naukri, Glassdoor and Google Jobs with the same filters"],
    ["Filters did not change the results", "A click during a running request was ignored; location applied only when leaving the field",
     "Every filter change starts a new request and cancels the old one, so the screen always matches the selected filters; "
     "location applies on Enter or the Apply button"],
    ["Whole page looked blue; not professional", "Dark mode turned the page navy; several accent colours",
     "Clean light design: white and greys, black buttons, one green accent; new black-and-green logo"],
    ["'India' showed US-only remote jobs", "Any remote job passed a location filter",
     "Only remote jobs open worldwide pass; city aliases added (Bangalore = Bengaluru, Gurgaon = Gurugram...)"],
], [42 * mm, 56 * mm, 70 * mm])

doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                        topMargin=22 * mm, bottomMargin=18 * mm,
                        title="DreamJob: Build and Production Guide", author="DreamJob")
doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
print("wrote", OUT)
