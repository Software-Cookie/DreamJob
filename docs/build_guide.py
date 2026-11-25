"""Generates the DreamJob build and production guide (PDF).

    pip install reportlab
    python docs/build_guide.py                      # writes docs/DreamJob_Build_and_Production_Guide.pdf
    python docs/build_guide.py "D:/some/folder"     # writes the PDF into that folder instead
"""
import sys
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
OUT = (Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT) / "DreamJob_Build_and_Production_Guide.pdf"

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
    box(165, H - 75, 150, 70, "FastAPI app", ["/api/analyze, /api/match", "/api/pay/* (Razorpay)", "CSP, rate limit, gzip", "uvicorn workers"], fill=INK, stroke=INK, tc=colors.white)
    box(365, H - 62, 115, 56, "Résumé reader", ["pypdf / python-docx", "in memory only"])
    box(365, H - 130, 115, 56, "Profile builder", ["skills, titles,", "years, level, keywords"])
    box(165, 8, 150, 92, "Job index (memory)", ["last month's jobs with", "full descriptions,", "skills, levels, TF-IDF", "one worker crawls,", "others read snapshot"], fill=colors.HexColor("#F3F4F6"), stroke=INK3)
    box(0, 8, 120, 92, "Job sources", ["~186 company career", "sites (hourly)", "7 boards + Hacker News", "optional: JSearch,", "Adzuna, Jooble"], fill=PAPER)
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
table([["Version", "2.0.0 (autofill extension, Razorpay payments, full descriptions, unlimited skills, more sources)"],
       ["Date", date.today().strftime("%d %B %Y")],
       ["Running cost", "$0 per month (free tiers only). Razorpay charges only a fee per successful payment"],
       ["Recommended host", "Hugging Face Spaces (free CPU: 2 vCPU, 16 GB RAM)"],
       ["Repository", "github.com/Software-Cookie/DreamJob"],
       ["Stack", "Python 3.12, FastAPI, plain HTML/CSS/JS, Chrome/Edge extension (Manifest V3), Razorpay, Docker"]],
      [45 * mm, 120 * mm], header=False)
story.append(PageBreak())

# ---------------------------------------------------------------- contents
H1("Contents")
toc = [
    ("1", "What DreamJob is"), ("2", "The logo and visual identity"), ("3", "How it was built"),
    ("4", "The autofill extension (Workday and other application forms)"),
    ("5", "Payments with Razorpay: complete setup"),
    ("6", "Quality, speed and capacity: test results"), ("7", "Going live: step-by-step production guide"),
    ("8", "After launch: monitoring, upkeep and troubleshooting"), ("9", "Known limitations"),
    ("10", "Next steps and roadmap"), ("11", "Cost summary"), ("12", "What changed in versions 1.1 and 2.0"),
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
    "See for each job: a <b>match score (0-100%)</b>, plain-language reasons, an <b>experience verdict</b> "
    "(\"Asks for 3-5 years of experience; you have about 4\"), the skills they match, the skills the job also asks for "
    "(a learning list), a <b>score breakdown</b>, the <b>full job description</b>, salary when published, and a link to apply.",
    "Correct the profile (role, years, skills) and change filters: results update instantly without uploading again. "
    "<b>Add as many skills as you like</b>, several at once separated by commas; skills DreamJob doesn't know are "
    "matched against each job's full description.",
    "Open the same search on <b>LinkedIn, Indeed, Naukri, Glassdoor, Google Jobs and Wellfound</b> with one click.",
    "Install the free <b>DreamJob Autofill</b> extension, save the profile once, and fill Workday, Greenhouse, Lever and "
    "other application forms in one click (section 4).",
    "Optionally buy <b>DreamJob Pro</b> (Top 20 and Top 30) with UPI, card, net banking or wallet through Razorpay (section 5).",
])
H2("Principles")
bullets([
    "<b>Free to run.</b> No paid AI APIs, no database, free job APIs and free hosting. Payments are optional.",
    "<b>Private.</b> Résumés are read in memory and discarded; nothing about the user is stored.",
    "<b>Fast.</b> A warm search returns in about 0.25 seconds; 100 simultaneous uploads all succeed.",
    "<b>Professional and calm.</b> A full-width layout in black, white and greys with one green accent; subtle entrance and scroll animations, buttons that lift on hover and press into a rounded pill when clicked, all switched off for visitors who prefer reduced motion.",
    "<b>Honest.</b> Every score comes with its reasons, every job shows its exact posting date and links to the "
    "original posting. Only sources that report the real posting date are used.",
])
image("screenshot-home.png", 165, "The landing page: a clear promise, live job statistics and the upload form side by side, using the full width of the screen.")
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
    ["Skills", "36%", "55% x (share of the job's skills you have) + 45% x (how many you match, full credit at 4). "
                      "Generic skills such as Git, Excel or 'communication' count about a third as much."],
    ["Title", "30%", "1.0 if one of your titles appears in the job title; otherwise word overlap of the core title "
                     "words (synonyms like developer = engineer); at least 0.5 when both are in the same role family "
                     "(20 families such as software, data, design, sales, finance, healthcare)."],
    ["Text", "14%", "TF-IDF cosine similarity between your résumé keywords and the job text, using word rarity "
                    "learned from the whole job index."],
    ["Experience", "20%", "Your years against the job's required range ('3-5 years', '5+ years of experience'), or against "
                          "the seniority in the title (intern, junior, senior, lead, director). Far more experience than a "
                          "range asks for counts a little less."],
], [26 * mm, 18 * mm, 124 * mm])
P("<b>Experience gate (on by default).</b> A job's seniority is read from the required years (English, German and French), the title (Intern, Junior, I, II, Senior, Staff, Principal, Director...) and, if neither says anything, wording in the description ('entry level', 'new grad', 'mehrjährige Berufserfahrung'). With <b>Match my experience level</b> ticked, roles that need clearly more experience than you have (more than max(1.5 years, 35%) above yours, or two levels higher) and roles clearly too junior (two levels lower, or a range you exceed by 5+ years) are hidden, and the results say how many. Tested on the live index: a fresher saw no Senior or Staff roles (903 hidden) and a senior engineer saw no junior roles. Jobs that list four or more specific skills, none of them yours, under a different title are dropped, and newer postings win between similar scores.")
P("<b>Experience verdict.</b> Every result also gets a plain-language verdict: <i>Experience fits</i>, <i>Slightly under "
  "the ask</i> (within a year), <i>Below the experience asked</i>, <i>More experience than asked</i> or <i>Experience not "
  "stated</i>, with the sentence behind it, for example \"Asks for 3-5 years of experience; you have about 4 years.\"")
P("<b>Unlimited and custom skills.</b> A profile can hold up to 300 skills (a safety limit, not a product limit). Skills "
  "in the built-in vocabulary are matched through the pre-computed skill lists. Any other skill the user types "
  "(for example 'Zephyr RTOS' or a company tool) is turned into one whole-word search and run against each "
  "candidate job's full title, tags and description, then counted like any other matched skill.")
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
    ["Company career sites", "~186 employers (Stripe, Databricks, Snowflake, MongoDB, OpenAI, Anthropic, Freshworks, "
     "Meesho, CRED, Paytm, ServiceNow, Bosch...) via the official job APIs of Greenhouse, Lever, Ashby and "
     "SmartRecruiters, with full descriptions (SmartRecruiters descriptions fetched once per new job)",
     "The employer's own first-publish date", "No"],
    ["Hacker News 'Who is hiring?'", "Startup jobs from the last two monthly threads (public Algolia API); only posts "
     "in the requested 'Company | Role | Location' format are used", "Time of the post", "No"],
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
P("<b>Sources tested and left out in 2.0.</b> Workday career sites answered with HTTP 429 (rate limited) even at one "
  "request every few seconds and do not list jobs newest-first, so crawling them would be unreliable and impolite; "
  "DreamJob helps with Workday through the autofill extension instead. The Muse sits behind a bot challenge. "
  "Recruitee, Personio and Breezy work, but very few matching employers were found. Naukri has no public API.")
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
    "<b>Multiple workers, one crawler.</b> Two Uvicorn workers use both CPUs on Hugging Face Spaces. Only the worker "
    "holding <font face='%s'>data/crawler.lock</font> calls the job sources; the others reload its snapshot when it "
    "changes. Each employer API is called once, not once per worker." % MONO,
    "<b>Polite crawling.</b> At most 6 boards at a time; a board that answers 429 is retried once after 10 seconds, and "
    "a board that still fails keeps the jobs it had. Descriptions are downloaded once per job and reused.",
    "<b>Snapshot on disk.</b> The index is saved after each refresh (atomically, one temporary file per process), so a "
    "restart serves jobs immediately.",
    "<b>Small, cached frontend.</b> About 30 KB of HTML/CSS/JS, gzip-compressed, no framework.",
])
H2("3.6 Security and privacy")
bullets([
    "Résumés are never written to disk or logs; only the public job index is saved.",
    "Upload limits: 5 MB, at most 12 PDF pages and 60,000 characters of text.",
    "Rate limit per visitor IP. The IP is read from the address appended by the host's proxy, so a client cannot "
    "dodge the limit by faking the X-Forwarded-For header.",
    "All job data is HTML-escaped before display (full descriptions are inserted as plain text), and only http(s) "
    "links are rendered, which blocks script injection from third-party job text.",
    "Security headers: a Content Security Policy that allows scripts only from DreamJob and Razorpay Checkout, "
    "X-Frame-Options DENY, HSTS, nosniff, a referrer policy and a permissions policy. API responses are not cached.",
    "Payment secrets come only from environment variables. They are never sent to the browser (tested) or logged. "
    "The order amount is set by the server. Payment and webhook signatures are checked with constant-time comparison.",
    "Separate rate limits for searches (30/min), payments (10/min), purchase restores (5/min) and résumé imports (10/min).",
    "Input validation on every API field (allowed windows, top values, list sizes, Razorpay ID formats).",
    "The repository ignores .env files, keys and certificates, the job snapshot and generated PDFs, so secrets "
    "cannot be committed by accident. The container runs as a non-root user.",
])
H2("3.7 Code map")
table([
    ["File", "Responsibility"],
    ["app/main.py", "API routes, rate limiting, security headers, policy pages, extension download, startup/shutdown"],
    ["app/payments.py", "Razorpay orders, payment and webhook signatures, capture, signed Pro passes, restore, refunds"],
    ["app/index.py", "Job index, crawler lock, background refresh, live-search cache, disk snapshot"],
    ["app/sources.py", "One connector per source (company sites, job boards, Hacker News, keyed APIs), all normalised to one format"],
    ["app/companies.py", "The verified list of ~186 company career boards (add more with one line each)"],
    ["app/matcher.py", "Résumé reading, profile building, scoring, experience verdicts, explanations and ranking"],
    ["app/nlp.py", "Tokenizer, skill/title/seniority/experience extraction, contact and work-history extraction, TF-IDF"],
    ["app/skills.py", "Skill vocabulary (with aliases) and job titles by role family"],
    ["app/config.py", "All settings, read from environment variables"],
    ["static/", "index.html, styles.css, app.js, logos (served as files)"],
    ["app/pages/", "Pricing, terms, privacy, refunds, contact and autofill pages, filled from your business settings"],
    ["extension/", "DreamJob Autofill: manifest, fill engine (filler.js), popup, profile page, floating button"],
    ["tests/", "41 offline tests: parsing, ranking, time windows, filters, sources, payments, pages, headers, crawler"],
    ["scripts/load_test.py", "Simulates N users uploading at the same moment"],
    ["Dockerfile, render.yaml", "Container and Render blueprint"],
    [".github/workflows/", "ci.yml runs tests on every push; keepalive.yml pings the site"],
], [45 * mm, 123 * mm])
story.append(PageBreak())

# =====================================================================================================
# 4. AUTOFILL EXTENSION
# =====================================================================================================
H1("4. The autofill extension (Workday and other application forms)")
P("Applying on Workday means typing the same name, address, phone, work history and education on every company's "
  "site, often across five or six steps. <b>DreamJob Autofill</b> is a free browser extension for Chrome and Edge that "
  "fills those forms from one saved profile.")
H2("4.1 What it fills")
table([
    ["Group", "Fields"],
    ["Personal", "First, middle, last and preferred name; email; phone, phone country code and phone type"],
    ["Address", "Address lines, city, state, PIN/postal code, country (also Workday's country dropdown)"],
    ["Links", "LinkedIn, GitHub, portfolio or website"],
    ["Common questions", "Total experience, current and expected salary/CTC, notice period, how you heard about the job"],
    ["Yes/no questions", "Authorised to work, needs sponsorship, willing to relocate, 18 or older, worked here before. "
                         "Only answered if you set them; otherwise left for you"],
    ["Work experience", "Job title, company, location, start and end month/year, 'I currently work here', description. "
                        "Block 1 gets your most recent job, block 2 the next, and so on. On Workday, missing blocks are added"],
    ["Education", "School, degree (including Workday's degree dropdown), field of study, dates, grade"],
    ["Your own answers", "Any question containing words you choose, e.g. 'notice period' -> '30 days'. These win over everything else"],
    ["Résumé file", "Attached to the résumé/CV upload field"],
    ["Voluntary self-ID", "Gender, ethnicity, veteran and disability status: never filled unless you enter them"],
], [32 * mm, 136 * mm])
H2("4.2 How it works")
bullets([
    "<b>Finding the right field.</b> For every visible input, dropdown and radio group it reads the label, ARIA label, "
    "placeholder, name, id and Workday's <font face='%s'>data-automation-id</font>, then applies about 40 rules ordered "
    "from specific to general (for example 'Company name' is never treated as your name)." % MONO,
    "<b>Setting values the way a person would.</b> Values are set through the browser's native setter and followed by "
    "input, change and blur events, so React, Angular and Workday register them. Workday's custom dropdowns are opened, "
    "the closest option is chosen and the list is closed.",
    "<b>Sections.</b> The nearest heading tells it whether a field belongs to work experience or education, and blocks "
    "are counted in order, even when some fields are already filled.",
    "<b>Safety.</b> It only fills empty fields (unless you tick 'Replace fields that already have a value'), outlines "
    "what it filled in green, and never clicks Submit, Next, Apply or any consent box.",
    "<b>Privacy.</b> The profile and résumé live in the browser's extension storage on your device. The extension "
    "reads a page only when you press Fill. 'Import details from résumé' sends the file once to your own DreamJob server "
    "(after you grant permission for that address), which reads it in memory and returns the details.",
])
H2("4.3 Where it works")
P("A 'Fill with DreamJob' button appears on Workday (myworkdayjobs.com, myworkdaysite.com), Greenhouse, Lever, Ashby, "
  "SmartRecruiters, Workable, iCIMS, SuccessFactors, Taleo, Recruitee, Breezy, Personio, BambooHR, Jobvite and Oracle "
  "Recruiting sites, including Greenhouse forms embedded in company pages. On any other site, click the extension "
  "icon and choose <b>Fill this page</b>, or press <b>Alt+Shift+F</b>. Workday shows one step at a time, so fill each "
  "step as it appears.")
H2("4.4 Install it")
steps([
    "Open your DreamJob site and go to <b>/autofill</b>. Click <b>Download the extension</b> and unzip it.",
    "Open <font face='%s'>chrome://extensions</font> (Chrome) or <font face='%s'>edge://extensions</font> (Edge) and turn on "
    "<b>Developer mode</b>." % (MONO, MONO),
    "Click <b>Load unpacked</b> and choose the <b>dreamjob-autofill</b> folder. The profile page opens.",
    "Choose your résumé, enter your DreamJob address and click <b>Import details from résumé</b>. Check every field, "
    "add your answers, then click <b>Save profile</b>.",
    "Pin the extension from the puzzle-piece menu.",
])
image("extension-profile.png", 150, "The profile page: fill it once, or import it from your résumé.")
image("extension-popup.png", 70, "The toolbar popup. On supported job sites a 'Fill with DreamJob' button also appears in the corner.")
H2("4.5 Publishing it in the stores (optional)")
table([
    ["Store", "Cost", "Notes"],
    ["Microsoft Edge Add-ons", "Free", "Register at partner.microsoft.com, upload the zip, fill in the listing and the privacy "
                                       "details (data stays on the device). Review usually takes a few days."],
    ["Chrome Web Store", "One-time US$5 developer registration", "Upload the zip at the Chrome Web Store developer dashboard. "
                                       "Explain each permission: storage (your profile), activeTab and scripting "
                                       "(fill the page you ask it to), host access to job sites (show the Fill button)."],
], [40 * mm, 40 * mm, 88 * mm])
P("Until it is in a store, the 'Load unpacked' install above works in Chrome and Edge at no cost.", "small")
story.append(PageBreak())

# =====================================================================================================
# 5. RAZORPAY
# =====================================================================================================
H1("5. Payments with Razorpay: complete setup")
P("DreamJob is free. If you want income, turn on <b>DreamJob Pro</b>: a one-time payment (default ₹99 for 30 days) that "
  "unlocks Top 20 and Top 30 results. Payments are off until you add Razorpay keys, and every price and limit is a setting.")
H2("5.1 What it costs")
table([
    ["Item", "Cost (Razorpay standard plan, India)"],
    ["Account, setup, annual maintenance", "Free: no setup fee and no annual fee"],
    ["Test mode", "Free and unlimited; works before your account is activated"],
    ["Each successful domestic payment", "About 2% of the amount plus 18% GST on that fee (about ₹2.34 on ₹99)"],
    ["Settlement to your bank", "Automatic, usually 2 working days after payment"],
    ["New-merchant offer (2026)", "Razorpay advertised 0% platform fee for 90 days or ₹5 lakh, for merchants activated "
                                  "from 1 July 2026. Check the pricing page; offers change"],
], [60 * mm, 108 * mm])
P("Always confirm current rates at razorpay.com/pricing before launch.", "small")
H2("5.2 How DreamJob takes a payment")
steps([
    "The visitor picks Top 20 or Top 30 (or clicks <b>Get Pro</b>) and sees the price, what they get and the refund policy.",
    "<b>Pay</b> calls <font face='%s'>POST /api/pay/order</font>. The server creates a Razorpay order with the amount "
    "from its own settings and a <font face='%s'>product: dreamjob_pro</font> note. The browser cannot change the price." % (MONO, MONO),
    "Razorpay Checkout opens (UPI, cards, net banking, wallets). Card and UPI details go to Razorpay only.",
    "On success, Checkout returns the order ID, payment ID and a signature. The server (<font face='%s'>/api/pay/verify</font>) "
    "checks the signature: HMAC-SHA256 of order_id|payment_id with your key secret." % MONO,
    "The server then asks Razorpay's API for the payment and the order, and checks that the payment belongs to that "
    "order, is in rupees, matches the order amount, is for DreamJob Pro and is not refunded. If the account uses manual "
    "capture, it captures the payment.",
    "The server returns a <b>Pro pass</b>: a small token signed with HMAC that holds the payment ID and expiry date. "
    "The browser keeps it and sends it with searches. No database is needed.",
    "<b>Restore access</b> (another device, or cleared browser): the visitor enters the payment ID from Razorpay's "
    "receipt email and the email they paid with. The server checks both with Razorpay and issues the pass again.",
    "<b>Refunds.</b> A refund webhook revokes the pass at once. Each server worker also re-checks a pass's payment "
    "with Razorpay at most every 6 hours, so a refund is honoured even if a webhook is missed.",
])
image("pro-dialog.png", 150, "The DreamJob Pro window. 'Pay' opens Razorpay Checkout; 'Restore access' brings a pass back on any device.")
callout("<b>If something goes wrong:</b> if Checkout is closed, nothing is charged and the button resets. If a payment "
        "fails, Razorpay's reason is shown and the visitor can retry. If verification fails after money was taken, the "
        "payment ID is shown so they can use Restore or email you. If Razorpay is unreachable, the visitor sees "
        "\"You have not been charged twice\" and can retry.")
H2("5.3 Step by step: from zero to accepting payments")
H3("A. Create the account and test (no documents needed)")
steps([
    "Go to <b>dashboard.razorpay.com</b> and sign up with your email and mobile number. Choose your business type: "
    "<b>Individual</b> or <b>Proprietorship</b> works for a personal project, and Razorpay supports freelancers and "
    "individuals.",
    "In the dashboard, switch the mode toggle to <b>Test Mode</b>.",
    "Open <b>Account &amp; Settings → API Keys → Generate Test Key</b>. Copy the <b>Key ID</b> (starts with "
    "<font face='%s'>rzp_test_</font>) and the <b>Key Secret</b>. The secret is shown once; store it in a password manager." % MONO,
    "Run DreamJob locally with the keys (never put them in a file inside the repository):",
])
code("""
# Windows PowerShell
$env:RAZORPAY_KEY_ID="rzp_test_xxxxxxxxxxxx"
$env:RAZORPAY_KEY_SECRET="xxxxxxxxxxxxxxxxxxxx"
$env:CONTACT_EMAIL="you@example.com"
uvicorn app.main:app --port 8000

# macOS / Linux
RAZORPAY_KEY_ID=rzp_test_xxx RAZORPAY_KEY_SECRET=xxx CONTACT_EMAIL=you@example.com uvicorn app.main:app --port 8000
""")
steps([
    "Open the site, upload a résumé and choose <b>Top 20</b>. The Pro window opens. Click <b>Pay ₹99</b>.",
    "Pay with a test card: <b>4100 2800 0000 1007</b> (Visa, India), any future expiry date and any CVV, then click "
    "<b>Success</b> on Razorpay's mock bank page. Or choose UPI and use a test UPI ID from Razorpay's 'Test Card Details' "
    "page (for example <font face='%s'>success@razorpay</font>)." % MONO,
    "The window closes, a message confirms Pro, and Top 20 results appear. The header shows 'Pro until ...'.",
    "Test the failure path too: use the mock bank page's <b>Failure</b> button. DreamJob shows the reason and lets you retry.",
    "Test Restore: open the site in a private window, choose Top 20, click <b>Already purchased? Restore access</b>, and "
    "enter the test payment ID (Dashboard → Transactions → Payments) and the email you typed at checkout.",
])
H3("B. Add the webhook (refunds and reconciliation)")
steps([
    "Your site must be online first (section 7). In the dashboard, open <b>Account &amp; Settings → Webhooks → "
    "Add New Webhook</b>.",
    "Webhook URL: <font face='%s'>https://&lt;your-site&gt;/api/pay/webhook</font>. Secret: a long random string you "
    "make up. Alert email: yours." % MONO,
    "Active events: <b>payment.captured</b>, <b>payment.failed</b>, <b>refund.created</b>, <b>refund.processed</b>.",
    "Save, and add the same secret to your host as <b>RAZORPAY_WEBHOOK_SECRET</b>.",
    "Use the dashboard's test-delivery feature, or make a test payment, and check the site's logs for a line like "
    "'razorpay webhook payment.captured pay_...'.",
])
H3("C. Activate the account and go live")
steps([
    "Fill in the business details in the dashboard: PAN (personal PAN for individuals), bank account in your name, "
    "address, and the website <b>https://&lt;your-site&gt;</b>. Aadhaar-based e-KYC or video KYC may be asked for. "
    "Razorpay's current rules say Terms, Privacy and Refund pages are no longer required at onboarding, but they "
    "still check the website before issuing live keys. DreamJob already has /terms, /privacy, /refunds, /contact and /pricing.",
    "Set <b>CONTACT_EMAIL</b> (and <b>BUSINESS_NAME</b>, <b>BUSINESS_ADDRESS</b>) so those pages show real details. Make sure "
    "the live site shows the price clearly and loads without errors.",
    "When activation is approved, switch the dashboard to <b>Live Mode</b> and generate <b>Live Keys</b> "
    "(<font face='%s'>rzp_live_...</font>)." % MONO,
    "In your host's <b>Secrets</b>, replace the test keys with the live keys, add a live-mode webhook (same URL and "
    "events, new secret) and update RAZORPAY_WEBHOOK_SECRET. Optionally set PASS_SECRET to a long random string.",
    "Make one real ₹99 payment yourself, check it in the dashboard, then refund it there (Transactions → Payments → "
    "Refund). Confirm your pass stops working after the refund.",
])
H2("5.4 Settings")
table([
    ["Variable", "Example", "Meaning"],
    ["RAZORPAY_KEY_ID", "rzp_live_AbC...", "Public key ID (safe to show in the browser)"],
    ["RAZORPAY_KEY_SECRET", "(secret)", "Signs and checks payments. Host Secrets only"],
    ["RAZORPAY_WEBHOOK_SECRET", "(secret)", "Checks webhook signatures. Host Secrets only"],
    ["PASS_SECRET", "(optional secret)", "Signs Pro passes. If empty, derived from the key secret"],
    ["PRO_PRICE_INR / PRO_DAYS", "99 / 30", "Price in rupees (including GST if you charge it) and length of a pass"],
    ["PRO_TOPS", "20,30", "Result sizes that need Pro (e.g. '30' to keep Top 20 free)"],
    ["BUSINESS_NAME / CONTACT_EMAIL / BUSINESS_ADDRESS", "DreamJob / you@... / Hyderabad, Telangana", "Shown on the policy and contact pages"],
], [55 * mm, 40 * mm, 73 * mm])
H2("5.5 Rules to follow")
bullets([
    "<b>Never commit keys.</b> .env files are ignored by Git; use the host's Secrets page. If a secret ever leaks, "
    "regenerate it in the dashboard at once.",
    "<b>Refunds:</b> the built-in policy promises a full refund within 7 days on request. Process refunds from the dashboard.",
    "<b>Tax:</b> GST registration is generally required only above the turnover threshold (₹20 lakh for most service "
    "businesses); income from sales is taxable. Ask a chartered accountant before you earn significant amounts.",
    "<b>Customer support:</b> answer emails within 2 working days (as the Contact page promises). Unanswered complaints "
    "lead to chargebacks.",
])
H2("5.6 Razorpay resources")
table([
    ["What", "Where"],
    ["Sign up / dashboard", "dashboard.razorpay.com"],
    ["Pricing", "razorpay.com/pricing"],
    ["Standard Checkout integration guide", "razorpay.com/docs/developer-tools/integrations/standard-checkout/"],
    ["Test cards and test UPI IDs", "razorpay.com/docs/payments/payments/test-card-details"],
    ["Account activation and KYC help", "razorpay.com/docs/payments/account-activation-support"],
    ["Webhooks (setup and signature check)", "razorpay.com/docs/webhooks/"],
    ["Payments FAQ", "razorpay.com/docs/payments/faqs"],
    ["Support", "Dashboard → Help &amp; Support (raise a ticket)"],
], [60 * mm, 108 * mm])
story.append(PageBreak())

# =====================================================================================================
# 6. TESTS
# =====================================================================================================
H1("6. Quality, speed and capacity: test results")
P("Version 2.0 measured on 25 November 2026 on a Windows laptop, against the real job sources, in Microsoft Edge.")
table([
    ["Check", "Result"],
    ["Automated tests (pytest)", "41 passed (also run by GitHub Actions on every push)"],
    ["Jobs indexed after a full refresh", "8,890 (company career sites 7,594 from 186 boards; job boards 1,296 incl. 307 from Hacker News)"],
    ["Jobs per window", "24 h: 1,230   48 h: 2,145   72 h: 2,609   1 week: 4,242   1 month: 8,846"],
    ["First full crawl of company sites", "3 minutes (182 s), including full descriptions; later refreshes only download new jobs"],
    ["Web app in the browser", "Upload, 10 results, experience verdict on every result, full description and score bars open; "
                               "3 skills added in one go; 'Clear all' then update works; 24 h filter shows only jobs from the last "
                               "24 hours; Top 3 shows 3; no JavaScript errors; no sideways scrolling at 390 px; all six pages load"],
    ["Payments (test keys)", "Top 20 opens the Pro window and stays on Top 10; the API refuses Top 20 without a pass (402); "
                             "rejected keys show 'Nothing was charged'; Razorpay Checkout loads under the security policy; "
                             "no secret appears in the page or /api/config"],
    ["Payment logic (automated, Razorpay mocked)", "Order amount from server; signature check; capture of authorized payments; "
                                                    "wrong amount, wrong product, failed payment and wrong restore email rejected; refund "
                                                    "webhook revokes the pass; bad webhook signature rejected"],
    ["Autofill extension (Edge, practice forms)", "Workday-style form: 30 fields filled across personal details, 2 work-experience "
                                                   "blocks (added automatically), education, dropdowns, dates, a radio question, a "
                                                   "custom answer and the résumé file; consent box and Submit untouched; a second run "
                                                   "changes nothing. Greenhouse-style form: 10 fields, existing values kept"],
    ["Extension installed for real", "Loads in Edge; profile saves and survives reload; popup shows the profile; Fill button on a "
                                     "Greenhouse address fills the form; 'hide on this site' is remembered"],
    ["Single search, warm", "0.15 seconds"],
    ["100 users uploading at the same instant (2 workers)", "100 of 100 succeeded; p50 2.6 s, p95 3.6 s"],
    ["Crawling with 2 workers", "Only one worker calls the job sources; the other loads its snapshot"],
    ["Memory per worker", "about 270-310 MB (full descriptions are now kept)"],
], [62 * mm, 106 * mm])
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
H1("7. Going live: step-by-step production guide")
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

H2("Step 1. Keep the code on GitHub")
P("The project lives at <b>github.com/Software-Cookie/DreamJob</b> (public). To publish changes:")
code("""
cd D:\\Agents\\BestMatch
git status                      # check: no .env, keys or data/ files listed
git add -A
git commit -m "Describe the change"
git push
""")
P("The <font face='%s'>.gitignore</font> excludes the virtual environment, caches, the job snapshot, generated PDFs, "
  ".env files, keys and certificates. On GitHub, open the <b>Actions</b> tab: the CI workflow runs all tests on every "
  "push, and a red cross means do not deploy. Because the repository is public, never put keys in code; if one leaks, "
  "regenerate it at the provider immediately (removing it from Git history is not enough)." % MONO)

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
    "Settings go under <b>Settings > Variables and secrets</b>. Put keys under <b>Secrets</b> (never Variables): "
    "RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET, PASS_SECRET, JSEARCH_API_KEY and so on. Put "
    "CONTACT_EMAIL, BUSINESS_NAME, BUSINESS_ADDRESS, PRO_PRICE_INR and SITE_URL under Variables. The Space restarts "
    "automatically.",
    "Hugging Face keeps files in /app/data only while the Space runs, so after a restart the first crawl takes a few "
    "minutes. That is expected.",
])
H2("Step 2b. Turn on payments and share the extension")
steps([
    "Follow section 5.3: test keys first, then the webhook, then live keys after activation.",
    "Open <b>https://&lt;your-site&gt;/pricing</b>, <b>/terms</b>, <b>/privacy</b>, <b>/refunds</b> and <b>/contact</b> and "
    "check your name and email appear correctly.",
    "Open <b>/autofill</b>, download the extension, install it and use 'Import details from résumé' with your live "
    "address. Fill a real Workday application up to the review step (do not submit) to check it.",
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
P("<b>Why not scrape LinkedIn, Naukri or Monster directly?</b> None of them offers a public jobs API, and their terms "
  "forbid automated scraping. LinkedIn in particular blocks cloud servers and has taken scrapers to court. A scraper "
  "would get a free host's IP blocked within days and put the project at legal risk. JSearch, Jooble, Adzuna and "
  "Careerjet are licensed aggregators that already carry those listings, so DreamJob uses them instead.")
H3("Jooble: large aggregator")
steps([
    "Request a key at <b>jooble.org/api/about</b>; it arrives by email.",
    "Add secret <b>JOOBLE_API_KEY</b>. Usage limits are set per key by Jooble.",
])
H3("Careerjet: Indian and global job sites")
steps([
    "Create a free publisher account at <b>careerjet.com/partners</b> (Register as publisher) and add your site address.",
    "Copy the API key for your site and save it as secret <b>CAREERJET_API_KEY</b>. CAREERJET_LOCALE defaults to en_IN (India).",
    "DreamJob sends the visitor's IP address and browser name with each search, as Careerjet requires, and links every "
    "result to Careerjet's listing page.",
])
H3("Deep search")
P("With any of these keys set, each résumé is searched live up to three times per portal (the top job titles, then the "
  "strongest skills phrased as a role, such as 'Python engineer'). JSearch also receives your experience band "
  "(no experience, under 3 years, over 3 years). DreamJob waits up to 20 seconds while the loading screen names the sites "
  "being searched. Results are cached and shared, so a second person with a similar profile gets them instantly. Tune "
  "this with <b>DEEP_QUERIES</b> (1-5) and <b>DEEP_SEARCH_TIMEOUT</b> (seconds). Each JSearch query uses one request of the "
  "free 200-a-month quota, so keep DEEP_QUERIES at 2-3 on the free plan.")
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
    ["Skills", "Add 'Zephyr RTOS, Terraform, Power BI' in one go, then Update results", "All three appear as chips; matching jobs list them"],
    ["Details", "Open 'Job description' and 'Why this match' on a result", "Full text with paragraphs; three score bars"],
    ["Payments (test keys)", "Choose Top 20, pay with the test card, then refund it in the dashboard", "Pro activates; after the refund, Top 20 asks for Pro again"],
    ["Restore", "Private window → Top 20 → Restore access", "Pro comes back with the payment ID and email"],
    ["Policy pages", "Open /pricing, /terms, /privacy, /refunds, /contact", "Your business name and email are shown"],
    ["Extension", "Install from /autofill, import from résumé, open a Workday job and press Fill", "Fields filled and outlined; nothing submitted"],
    ["Secrets", "View the page source and open /api/config", "Only the rzp_ key ID appears, never a secret"],
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
H1("8. After launch: monitoring, upkeep and troubleshooting")
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
    ["Out of memory on a 512 MB host", "Too many workers or jobs (about 300 MB per worker)", "WEB_CONCURRENCY=1 and ARBEITNOW_PAGES=3"],
    ["Space build fails", "README settings block missing", "Make sure README.md starts with the --- block (Step 2.4)"],
    ["No 'Get Pro' button", "Payment keys missing", "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET as Secrets; restart"],
    ["'Payments are not set up correctly'", "Razorpay rejected the keys", "Copy the key pair again (test and live keys differ); the log says 'razorpay rejected the API keys'"],
    ["Payment window does not open", "Ad blocker or network blocks checkout.razorpay.com", "Ask the user to allow it; the site shows this hint"],
    ["Webhook shows failures in the dashboard", "Wrong secret or site asleep", "Match RAZORPAY_WEBHOOK_SECRET with the dashboard; keep the site awake"],
    ["Paid user lost Pro", "New device or cleared browser", "Restore access with the payment ID and email"],
    ["Extension fills nothing", "No profile saved, or the site uses unusual labels", "Save the profile; add your own answers for those questions"],
    ["Many 'board ... 429' log lines", "An employer API is rate-limiting", "Nothing; it retries and keeps that board's jobs. Raise BOARD_REFRESH_MINUTES if constant"],
], [45 * mm, 50 * mm, 73 * mm])
story.append(PageBreak())

# =====================================================================================================
# 7. LIMITATIONS
# =====================================================================================================
H1("9. Known limitations")
bullets([
    "<b>LinkedIn only through legitimate routes.</b> Without a JSearch key, LinkedIn jobs are reached through the "
    "'Search other job sites' links, not inside DreamJob's ranked list. JSearch's free quota (~200 requests a month) "
    "suits a personal or small public tool; heavy traffic needs a paid plan.",
    "<b>Coverage follows the company list.</b> The ~186 company boards lean towards tech employers. Adding Indian "
    "employers to app/companies.py, or adding Adzuna/JSearch keys, widens coverage. Workday-only employers are not "
    "crawled (see 3.4).",
    "<b>Arbeitnow is mostly German jobs.</b> They match on skills but are rarely relevant in India; use the Location "
    "filter, or set ARBEITNOW_PAGES=0 to drop them.",
    "<b>Rule-based reading.</b> Skills outside the vocabulary of about 300 are not detected in the résumé automatically; "
    "users add them in the profile panel, and those custom skills are then matched against job descriptions.",
    "<b>Autofill is rule-based.</b> It was tested end to end in Microsoft Edge on practice forms built like Workday "
    "and Greenhouse, not on every employer's live form, because live forms need accounts and real applications. Unusual "
    "questions are left empty for you. Check the filled fields before you submit.",
    "<b>Pro passes live in the browser.</b> There are no accounts. A pass is restored with the payment ID and email. "
    "Refund status is shared across workers through Razorpay itself (checked at most every 6 hours) and instantly on the "
    "worker that receives the webhook.",
    "<b>The rate limit is per worker process</b> (about 60 searches a minute per visitor with 2 workers).",
    "<b>Free hosts sleep</b>, and the first company-site crawl after a fresh deploy takes about five minutes.",
])

H1("10. Next steps and roadmap")
P("Ordered by value for the effort. Everything listed can still be done for free.")
H2("Next (1-2 weeks)")
table([
    ["Improvement", "Why", "How (free)"],
    ["More Indian employers", "More on-site jobs in India", "Find more Greenhouse, Lever, Ashby and SmartRecruiters boards and add one line each to app/companies.py"],
    ["OCR for scanned PDFs", "Some résumés are images", "Add Tesseract to the Docker image and use it when a PDF has no text"],
    ["Share results", "Users want to save or send their list", "'Copy link' that encodes the profile in the URL, or 'Download as PDF'"],
    ["Feedback buttons", "Learn where matching is wrong", "'Good match / not relevant' per job, counted in a free Google Form or Supabase table"],
    ["Publish the extension", "One-click install for users", "Edge Add-ons (free) now; Chrome Web Store after the US$5 registration"],
    ["Autofill field learning", "Fewer empty questions", "Offer 'Save this answer' for fields the user fills by hand, stored in the extension"],
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
    "Extend the autofill extension to score any job page you visit against your saved profile.",
    "Accounts and subscriptions (Razorpay Subscriptions) once there are enough paying users; this needs a database "
    "(Supabase free tier) for users and passes.",
    "If traffic grows past the free tier: move to Oracle Cloud Always Free, or a paid Hugging Face CPU upgrade. "
    "The app is a single container, so moving is a 10-minute job.",
])
story.append(PageBreak())

# =====================================================================================================
# 9. COST
# =====================================================================================================
H1("11. Cost summary")
table([
    ["Item", "Service", "Cost"],
    ["Hosting", "Hugging Face Spaces (CPU basic) or Render free", "$0"],
    ["Job data", "Company career site APIs, Hacker News, Remotive, Remote OK, We Work Remotely, Jobicy, Working Nomads, Arbeitnow", "$0"],
    ["Payments (optional)", "Razorpay: no setup or annual fee", "About 2% + GST per successful payment"],
    ["Autofill extension", "Load unpacked, or Edge Add-ons", "$0 (Chrome Web Store: one-time US$5, optional)"],
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
        "block to README.md and push to the Space. 4) Set CONTACT_EMAIL and, if you want income, the Razorpay test keys; "
        "test a payment, then switch to live keys after activation. 5) Optionally add a JSearch key for LinkedIn and Indeed "
        "jobs. 6) Add an UptimeRobot monitor. 7) Run the launch checklist, then share the link and the extension.")

story.append(PageBreak())
H1("12. What changed in versions 1.1 and 2.0")
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
H2("Version 2.0")
table([
    ["Request", "What was built"],
    ["Skills were limited", "Custom skills only counted if they were in the built-in list, and profiles were capped at "
                            "60-80 skills. Now up to 300 skills, added several at once; unknown skills are matched in job descriptions"],
    ["Job descriptions", "Full descriptions with paragraphs and bullet points for every source, including SmartRecruiters "
                         "(previously a one-line summary), shown on demand under each result"],
    ["Clear experience match", "Required ranges are read ('3-5 years') and every result shows a verdict and sentence, "
                               "plus a breakdown of skills, title and experience fit"],
    ["More job portals", "33 more verified employers (186 in total, including Paytm, Snowflake, Perplexity, Nubank) and "
                         "Hacker News 'Who is hiring?'. Workday, The Muse, Recruitee, Personio and Breezy were tested; see 3.4"],
    ["Fill Workday forms faster", "DreamJob Autofill browser extension (section 4)"],
    ["Payment gateway (Razorpay)", "DreamJob Pro with server-side orders, signature and amount checks, capture, restore, "
                                   "refund-aware passes, webhooks, policy pages, and a full setup guide (section 5)"],
    ["No errors, production-ready, no leaks", "CI import error fixed (pytest.ini); 34 tests; one crawler per server with "
                                              "polite retries; snapshot write race fixed; CSP and security headers; stricter "
                                              ".gitignore; .env.example rewritten so comments can't become secret values"],
], [45 * mm, 123 * mm])

doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                        topMargin=22 * mm, bottomMargin=18 * mm,
                        title="DreamJob: Build and Production Guide", author="DreamJob")
doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
print("wrote", OUT)
