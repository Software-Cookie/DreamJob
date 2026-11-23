/* DreamJob frontend: no framework, no build step. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const WINDOWS = {
    "24h": { label: "the last 24 hours", hours: 24, days: 1 },
    "48h": { label: "the last 48 hours", hours: 48, days: 2 },
    "72h": { label: "the last 72 hours", hours: 72, days: 3 },
    "1w": { label: "the last week", hours: 168, days: 7 },
    "1m": { label: "the last month", hours: 720, days: 30 },
  };
  const DEFAULTS = { window: "1w", top: "10", location: "", remote_only: false };

  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
  };

  const state = {
    prefs: { ...DEFAULTS, ...store.get("dj.prefs.v2", {}) },
    file: null,
    profile: null,
    seq: 0,          // id of the newest request; older responses are ignored
    controller: null, // aborts the in-flight request when a newer one starts
  };
  if (!WINDOWS[state.prefs.window]) state.prefs.window = DEFAULTS.window;

  // ------------------------------------------------------------------ helpers
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");
  const ACRONYMS = { ui: "UI", ux: "UX", qa: "QA", sre: "SRE", bi: "BI", ml: "ML", ai: "AI", hr: "HR", it: "IT", sdet: "SDET", seo: "SEO" };
  const titleCase = (s) => (s || "").split(" ").map((w) => ACRONYMS[w] || (w.charAt(0).toUpperCase() + w.slice(1))).join(" ");

  function ago(ts) {
    const s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min ago`;
    if (s < 86400) { const h = Math.round(s / 3600); return `${h} hour${h === 1 ? "" : "s"} ago`; }
    const d = Math.floor(s / 86400);
    return d === 1 ? "1 day ago" : `${d} days ago`;
  }
  const fullDate = (ts) => new Date(ts * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

  async function api(path, opts = {}) {
    let res;
    try {
      res = await fetch(path, opts);
    } catch (e) {
      if (e.name === "AbortError") throw e;
      throw new Error("Can't reach DreamJob. Check your connection and try again.");
    }
    let body = null;
    try { body = await res.json(); } catch { /* not JSON */ }
    if (!res.ok) {
      const msg = body?.error || (Array.isArray(body?.detail) ? "Some settings are invalid. Reload the page and try again." : null);
      throw new Error(msg || `The server returned an error (${res.status}). Try again in a minute.`);
    }
    return body;
  }

  function showError(id, msg) { const el = $(id); el.textContent = msg; el.hidden = false; }
  function hideError(id) { $(id).hidden = true; }

  // ------------------------------------------------------------------ filters (rendered on both pages)
  function mountFilters(container, prefix) {
    container.appendChild($("filtersTpl").content.cloneNode(true));
    container.querySelectorAll(".seg").forEach((group) => {
      group.querySelectorAll("input").forEach((inp) => {
        inp.name = `${prefix}-${group.dataset.name}`;
        inp.addEventListener("change", () => setPref(group.dataset.name, inp.value));
      });
    });
    const top = container.querySelector('[data-name="top"]');
    top.id = `${prefix}-top`;
    top.addEventListener("change", () => setPref("top", top.value));

    const loc = container.querySelector('[data-name="location"]');
    loc.id = `${prefix}-location`;
    const applyLoc = () => { if (loc.value.trim() !== state.prefs.location) setPref("location", loc.value.trim()); };
    loc.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); applyLoc(); } });
    loc.addEventListener("change", applyLoc);
    container.querySelector('[data-act="apply-location"]').addEventListener("click", applyLoc);
    // The search page applies everything with the main button, so no separate Apply there.
    if (prefix === "search") container.querySelector('[data-act="apply-location"]').hidden = true;

    const rem = container.querySelector('[data-name="remote_only"]');
    rem.id = `${prefix}-remote`;
    rem.addEventListener("change", () => setPref("remote_only", rem.checked));
  }

  function syncFilters() {
    document.querySelectorAll(".seg").forEach((g) => {
      g.querySelectorAll("input").forEach((i) => { i.checked = String(state.prefs[g.dataset.name]) === i.value; });
    });
    document.querySelectorAll('[data-name="top"]').forEach((s) => { s.value = String(state.prefs.top); });
    document.querySelectorAll('[data-name="location"]').forEach((i) => { if (i !== document.activeElement) i.value = state.prefs.location; });
    document.querySelectorAll('[data-name="remote_only"]').forEach((i) => { i.checked = !!state.prefs.remote_only; });
  }

  function setPref(name, value) {
    state.prefs[name] = value;
    store.set("dj.prefs.v2", state.prefs);
    syncFilters();
    renderExternalLinks();
    // On the results page every filter change fetches new results immediately.
    if (state.profile && !$("resultsView").hidden) runMatch();
  }

  // ------------------------------------------------------------------ upload
  const drop = $("drop");
  const fileInput = $("file");

  function setFile(f) {
    if (!f) return;
    if (!/\.(pdf|docx|txt|md)$/i.test(f.name)) return showError("formError", "Upload a PDF, DOCX or TXT file.");
    if (f.size > 5 * 1024 * 1024) return showError("formError", "The file is larger than 5 MB. Upload a smaller file.");
    state.file = f;
    hideError("formError");
    drop.classList.add("has-file");
    $("dropTitle").textContent = f.name;
    $("dropHint").textContent = `${Math.max(1, Math.round(f.size / 1024))} KB. Click to choose a different file.`;
  }

  drop.addEventListener("click", () => fileInput.click());
  drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } });
  fileInput.addEventListener("change", () => setFile(fileInput.files[0]));
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => setFile(e.dataTransfer.files[0]));

  $("pasteToggle").addEventListener("click", (e) => {
    const wrap = $("pasteWrap");
    wrap.hidden = !wrap.hidden;
    e.currentTarget.setAttribute("aria-expanded", String(!wrap.hidden));
    e.currentTarget.textContent = wrap.hidden ? "Paste text instead" : "Hide text box";
    if (!wrap.hidden) $("pasteText").focus();
  });

  // ------------------------------------------------------------------ views
  function show(view) {
    $("searchView").hidden = view !== "search";
    $("loadingView").hidden = view !== "loading";
    $("resultsView").hidden = view !== "results";
    window.scrollTo({ top: 0 });
  }

  // ------------------------------------------------------------------ requests
  function startRequest() {
    if (state.controller) state.controller.abort();
    state.controller = new AbortController();
    return { id: ++state.seq, signal: state.controller.signal };
  }

  $("searchForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = $("pasteText").value.trim();
    if (!state.file && text.length < 80) {
      return showError("formError", text ? "Paste a bit more of your résumé (at least a few lines)." : "Add your résumé first: drop a file above or paste the text.");
    }
    hideError("formError");
    // pick up a typed location even if the user didn't press Enter
    const loc = document.querySelector('#search-location');
    if (loc) state.prefs.location = loc.value.trim();

    const fd = new FormData();
    if (state.file) fd.append("file", state.file); else fd.append("text", text);
    fd.append("window", state.prefs.window);
    fd.append("top", state.prefs.top);
    fd.append("location", state.prefs.location);
    fd.append("remote_only", state.prefs.remote_only ? "true" : "false");

    const req = startRequest();
    $("submitBtn").disabled = true;
    $("loadingText").textContent = "Reading your résumé and ranking jobs…";
    show("loading");
    try {
      const data = await api("/api/analyze", { method: "POST", body: fd, signal: req.signal });
      if (req.id !== state.seq) return;
      state.profile = data.profile;
      renderProfile();
      syncFilters();
      renderResults(data);
      show("results");
    } catch (err) {
      if (err.name === "AbortError") return;
      show("search");
      showError("formError", err.message);
    } finally {
      $("submitBtn").disabled = false;
    }
  });

  async function runMatch() {
    if (!state.profile) return;
    readProfileEdits();
    const req = startRequest();
    $("updating").hidden = false;
    $("jobList").classList.add("is-updating");
    hideError("resultsError");
    try {
      const data = await api("/api/match", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: req.signal,
        body: JSON.stringify({
          profile: state.profile, window: state.prefs.window, top: Number(state.prefs.top),
          location: state.prefs.location, remote_only: !!state.prefs.remote_only,
        }),
      });
      if (req.id !== state.seq) return; // a newer filter change is already on its way
      renderResults(data);
    } catch (err) {
      if (err.name === "AbortError") return;
      if (req.id === state.seq) showError("resultsError", err.message);
    } finally {
      if (req.id === state.seq) {
        $("updating").hidden = true;
        $("jobList").classList.remove("is-updating");
      }
    }
  }

  $("updateBtn").addEventListener("click", runMatch);
  $("restartBtn").addEventListener("click", () => {
    if (state.controller) state.controller.abort();
    state.profile = null;
    show("search");
    drop.focus();
  });

  // ------------------------------------------------------------------ profile panel
  function readProfileEdits() {
    const role = $("roleInput").value.trim().toLowerCase();
    const rest = (state.profile.titles || []).slice(1).filter((t) => t !== role);
    state.profile.titles = role ? [role, ...rest] : rest;
    const y = parseFloat($("yearsInput").value);
    if (!Number.isNaN(y)) { state.profile.years = Math.max(0, Math.min(50, y)); state.profile.level = null; }
  }

  function renderProfile() {
    const p = state.profile;
    $("roleInput").value = titleCase(p.titles?.[0] || "");
    $("yearsInput").value = p.years || 0;
    renderChips();
    renderExternalLinks();
  }

  function renderChips() {
    const ul = $("skillChips");
    ul.innerHTML = "";
    const skills = state.profile.skills || [];
    $("skillCount").textContent = `(${skills.length})`;
    skills.forEach((s, i) => {
      const li = document.createElement("li");
      li.innerHTML = `<span>${esc(s)}</span><button type="button" aria-label="Remove ${esc(s)}">×</button>`;
      li.querySelector("button").addEventListener("click", () => { state.profile.skills.splice(i, 1); renderChips(); });
      ul.appendChild(li);
    });
  }

  $("addSkillForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const v = $("addSkill").value.trim();
    if (!v || !state.profile) return;
    if (!state.profile.skills.some((s) => s.toLowerCase() === v.toLowerCase())) state.profile.skills.unshift(v);
    $("addSkill").value = "";
    renderChips();
  });
  $("roleInput").addEventListener("keydown", (e) => { if (e.key === "Enter") runMatch(); });
  $("yearsInput").addEventListener("keydown", (e) => { if (e.key === "Enter") runMatch(); });

  // ------------------------------------------------------------------ other job sites
  function slug(s) { return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); }

  function renderExternalLinks() {
    if (!state.profile) return;
    const p = state.profile;
    const role = $("roleInput").value.trim() || titleCase(p.titles?.[0] || "") || (p.skills || []).slice(0, 2).join(" ");
    const loc = state.prefs.location || p.location || "";
    const w = WINDOWS[state.prefs.window];
    const remote = !!state.prefs.remote_only;
    const q = encodeURIComponent(role);
    const l = encodeURIComponent(loc);
    const india = /india|bengaluru|bangalore|hyderabad|pune|mumbai|chennai|delhi|gurgaon|gurugram|noida|kolkata|ahmedabad/i.test(loc);
    const uk = /united kingdom|\buk\b|london|england/i.test(loc);
    const near = (days, allowed) => allowed.find((d) => d >= days) || allowed[allowed.length - 1];

    const sites = [
      ["LinkedIn", `https://www.linkedin.com/jobs/search/?keywords=${q}&location=${l}&f_TPR=r${w.hours * 3600}${remote ? "&f_WT=2" : ""}`, w.label],
      ["Indeed", `https://${india ? "in." : uk ? "uk." : "www."}indeed.com/jobs?q=${q}&l=${remote && !loc ? "Remote" : l}&fromage=${w.days}${remote ? "&remotejob=032b3046-06a3-4876-8dfd-474eb5e7ed11" : ""}`, w.label],
      ["Naukri", `https://www.naukri.com/${slug(role) || "jobs"}-jobs${loc ? "-in-" + slug(loc) : ""}?k=${q}${loc ? "&l=" + l : ""}&jobAge=${near(w.days, [1, 3, 7, 15, 30])}${remote ? "&wfhType=2" : ""}`, null],
      ["Glassdoor", `https://www.glassdoor.${india ? "co.in" : uk ? "co.uk" : "com"}/Job/jobs.htm?sc.keyword=${q}&locKeyword=${l}&fromAge=${near(w.days, [1, 3, 7, 14, 30])}${remote ? "&remoteWorkType=1" : ""}`, null],
      ["Google Jobs", `https://www.google.com/search?q=${encodeURIComponent(`${role} jobs ${remote ? "remote" : loc}`.trim())}&ibp=htl;jobs&htichips=date_posted:${{ "24h": "today", "48h": "3days", "72h": "3days", "1w": "week", "1m": "month" }[state.prefs.window]}`, null],
    ];
    $("extLinks").innerHTML = sites.map(([name, url]) =>
      `<li><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${name}<span>Opens in new tab</span></a></li>`).join("");
    $("elsewhereHint").textContent = `“${role || "your role"}”${loc ? " in " + loc : ""}, posted in ${w.label}${remote ? ", remote only" : ""}. Naukri and Glassdoor use their nearest date option.`;
  }

  // ------------------------------------------------------------------ results
  function jobItem(j, i) {
    const li = document.createElement("li");
    li.className = "job";
    const skills = (j.matched_skills || []).map((s) => `<span class="skill">${esc(s)}</span>`).join("");
    const missing = (j.missing_skills || []).join(", ");
    const why = (j.reasons || []).join(" · ");
    li.innerHTML = `
      <div class="job-top">
        <div>
          <h3><a href="${esc(safeUrl(j.url))}" target="_blank" rel="noopener noreferrer">${esc(j.title)}</a></h3>
          <p class="company"><b>${esc(j.company || "Company not listed")}</b> · ${esc(j.location || "Location not listed")}${j.remote ? '<span class="badge">Remote</span>' : ""}</p>
        </div>
        <span class="score ${j.score >= 70 ? "strong" : ""}" title="How well this job fits your résumé">${j.score}% match</span>
      </div>
      <p class="meta">
        <span class="posted" title="${esc(new Date(j.posted_at * 1000).toLocaleString())}">Posted ${esc(ago(j.posted_at))} (${esc(fullDate(j.posted_at))})</span>
        <span>Source: ${esc(j.source)}</span>
        ${j.salary ? `<span>${esc(j.salary)}</span>` : ""}
        ${j.job_type ? `<span>${esc(j.job_type)}</span>` : ""}
      </p>
      ${why ? `<p class="why">${esc(why)}</p>` : ""}
      ${skills ? `<div class="skills">${skills}</div>` : ""}
      ${missing ? `<p class="missing">Not on your résumé: ${esc(missing)}</p>` : ""}
      <div class="job-actions">
        <a class="btn btn-primary" href="${esc(safeUrl(j.url))}" target="_blank" rel="noopener noreferrer">Apply</a>
        ${j.snippet ? '<button type="button" class="text-btn" data-act="desc" aria-expanded="false">Show description</button>' : ""}
      </div>
      ${j.snippet ? `<p class="desc" hidden>${esc(j.snippet)}</p>` : ""}`;
    const btn = li.querySelector('[data-act="desc"]');
    if (btn) btn.addEventListener("click", () => {
      const d = li.querySelector(".desc");
      d.hidden = !d.hidden;
      btn.setAttribute("aria-expanded", String(!d.hidden));
      btn.textContent = d.hidden ? "Show description" : "Hide description";
    });
    return li;
  }

  function renderResults(data) {
    const list = $("jobList");
    list.innerHTML = "";
    const n = data.results.length;
    const w = WINDOWS[data.window];
    $("resultsTitle").textContent = n ? `Top ${n} matching job${n === 1 ? "" : "s"}` : "No matching jobs";
    const filters = [data.location ? `in ${data.location}` : "", data.remote_only ? "remote only" : ""].filter(Boolean).join(", ");
    $("resultsMeta").textContent = `Posted in ${w.label}${filters ? ", " + filters : ""}. Ranked from ${data.considered.toLocaleString()} jobs.`;
    const srcs = Object.entries(data.by_source || {}).map(([k, v]) => `${k} ${v.toLocaleString()}`).join(" · ");
    $("resultsSources").textContent = srcs ? `Searched: ${srcs}` : "";
    $("emptyState").hidden = n > 0;
    if (!n) {
      const canWiden = data.window !== "1m";
      const hasFilters = data.location || data.remote_only;
      $("emptyState").innerHTML = `
        <h3>No jobs like yours were posted in ${esc(w.label)}${hasFilters ? " with these filters" : ""}</h3>
        <p>Try a longer time range${hasFilters ? " or clear the location filters" : ""}, or use the links on the right to search other job sites.</p>
        ${canWiden ? '<button type="button" class="btn btn-secondary" data-act="month">Show the last month</button>' : ""}
        ${hasFilters ? '<button type="button" class="btn btn-secondary" data-act="clear">Clear location filters</button>' : ""}`;
      $("emptyState").querySelector('[data-act="month"]')?.addEventListener("click", () => setPref("window", "1m"));
      $("emptyState").querySelector('[data-act="clear"]')?.addEventListener("click", () => { state.prefs.location = ""; setPref("remote_only", false); });
    }
    const frag = document.createDocumentFragment();
    data.results.forEach((j, i) => frag.appendChild(jobItem(j, i)));
    list.appendChild(frag);
  }

  // ------------------------------------------------------------------ boot
  async function loadStats() {
    try {
      const s = await api("/api/stats");
      const mins = s.last_refresh ? Math.round((Date.now() / 1000 - s.last_refresh) / 60) : null;
      $("indexStatus").innerHTML = s.jobs
        ? `${s.jobs.toLocaleString()} jobs from the last month<span class="upd"> · updated ${mins === null || mins < 1 ? "just now" : mins + " min ago"}</span>`
        : "Collecting jobs. This takes about a minute after a restart.";
      $("sourcesNote").textContent = `Searching ${s.companies} company career sites and ${(s.enabled || []).length - 1} job boards`
        + (s.by_window ? ` (${s.by_window["24h"].toLocaleString()} jobs posted in the last 24 hours).` : ".");
      if (!s.jobs) setTimeout(loadStats, 8000);
    } catch { $("indexStatus").textContent = ""; }
  }

  async function loadSkills() {
    try {
      const { skills } = await api("/api/skills");
      $("skillList").innerHTML = skills.map((s) => `<option value="${esc(s)}">`).join("");
    } catch { /* optional */ }
  }

  mountFilters(document.querySelector('[data-filters="search"]'), "search");
  mountFilters(document.querySelector('[data-filters="results"]'), "results");
  syncFilters();
  loadStats();
  loadSkills();
})();
