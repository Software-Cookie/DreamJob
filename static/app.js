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
  const DEFAULTS = { window: "1w", top: "10", location: "", remote_only: false, exp_match: true };
  const MAX_SKILLS = 300;

  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
    del(k) { try { localStorage.removeItem(k); } catch { /* private mode */ } },
  };

  const state = {
    prefs: { ...DEFAULTS, ...store.get("dj.prefs.v2", {}) },
    file: null,
    profile: null,
    seq: 0,           // id of the newest request; older responses are ignored
    controller: null, // aborts the in-flight request when a newer one starts
    config: { payments: { enabled: false, pro_tops: [] } },
    pass: null,       // { token, expires_at } once DreamJob Pro is bought
    pendingTop: null, // the Top N the user picked before being asked to upgrade
    user: null,       // signed-in account, if any
    auth: { email: false, google: false, required: false },
  };
  if (!WINDOWS[state.prefs.window]) state.prefs.window = DEFAULTS.window;
  if (!["3", "10", "20", "30"].includes(String(state.prefs.top))) state.prefs.top = DEFAULTS.top;

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

  class ApiError extends Error { constructor(msg, status) { super(msg); this.status = status; } }

  async function api(path, opts = {}) {
    const headers = { ...(opts.headers || {}) };
    if (passActive()) headers["X-DreamJob-Pass"] = state.pass.token;
    let res;
    try {
      res = await fetch(path, { ...opts, headers });
    } catch (e) {
      if (e.name === "AbortError") throw e;
      throw new ApiError("We couldn't reach DreamJob. Check your connection and try again.", 0);
    }
    let body = null;
    try { body = await res.json(); } catch { /* not JSON */ }
    if (!res.ok) {
      const msg = body?.error || (Array.isArray(body?.detail) ? "Some values are invalid. Check them and try again." : null);
      throw new ApiError(msg || `The server returned an error (${res.status}). Try again in a minute.`, res.status);
    }
    return body;
  }

  function showError(id, msg) { const el = $(id); el.textContent = msg; el.hidden = false; }
  function hideError(id) { $(id).hidden = true; }

  let toastTimer;
  function toast(msg) {
    const t = $("toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 6000);
  }

  // ------------------------------------------------------------------ DreamJob Pro
  const pay = () => state.config.payments || {};
  const proTops = () => (pay().enabled ? (pay().pro_tops || []).map(String) : []);
  const needsPro = (top) => proTops().includes(String(top));
  function passActive() { return !!(state.pass && state.pass.expires_at * 1000 > Date.now()); }

  function loadPass() {
    const p = store.get("dj.pass", null);
    state.pass = p && p.token && p.expires_at * 1000 > Date.now() ? p : null;
    if (!state.pass) store.del("dj.pass");
  }

  function renderPro() {
    const on = !!pay().enabled;
    $("pricingLink").hidden = !on;
    $("proBtn").hidden = !on || passActive();
    $("proBadge").hidden = !on || !passActive();
    if (on && passActive()) $("proBadge").textContent = `Pro until ${fullDate(state.pass.expires_at)}`;
    document.querySelectorAll('[data-name="top"] option').forEach((o) => {
      o.textContent = `Top ${o.value}${needsPro(o.value) && !passActive() ? " (Pro)" : ""}`;
    });
    if (on) {
      const price = `₹${pay().price}`;
      $("proPrice").textContent = price;
      $("proDays").textContent = `for ${pay().days} days`;
      $("payBtn").textContent = `Pay ${price}`;
      $("proTopsLine").textContent = `${(pay().pro_tops || []).map((t) => "Top " + t).join(" and ")} matches per search`;
    }
  }

  function openPro(reason) {
    if (!pay().enabled) return;
    hideError("proError");
    $("payBtn").disabled = false;
    if (reason) showError("proError", reason);
    const d = $("proDialog");
    if (!d.open) d.showModal();
  }
  $("proDialog").addEventListener("close", () => { state.pendingTop = null; syncFilters(); });
  $("proDialog").addEventListener("click", (e) => { if (e.target === $("proDialog")) $("proDialog").close(); });
  $("proBtn").addEventListener("click", () => openPro());

  function activatePass(p) {
    state.pass = { token: p.token, expires_at: p.expires_at };
    store.set("dj.pass", state.pass);
    const top = state.pendingTop;
    state.pendingTop = null;
    $("proDialog").close();
    renderPro();
    toast(`DreamJob Pro is active until ${fullDate(p.expires_at)}. Thank you!`);
    if (top) setPref("top", top);
  }

  let checkoutScript = null;
  function loadCheckout() {
    if (window.Razorpay) return Promise.resolve();
    if (!checkoutScript) {
      checkoutScript = new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = "https://checkout.razorpay.com/v1/checkout.js";
        s.async = true;
        s.onload = () => resolve();
        s.onerror = () => { checkoutScript = null; reject(new Error("The payment window could not load. Check your connection or turn off a blocker for checkout.razorpay.com, then try again.")); };
        document.head.appendChild(s);
      });
    }
    return checkoutScript;
  }

  let paying = false;
  $("payBtn").addEventListener("click", async () => {
    if (paying) return;
    paying = true;
    const btn = $("payBtn");
    const label = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Opening secure payment…";
    hideError("proError");
    const done = () => { paying = false; btn.disabled = false; btn.textContent = label; };
    try {
      const [order] = await Promise.all([api("/api/pay/order", { method: "POST" }), loadCheckout()]);
      const rzp = new window.Razorpay({
        key: order.key_id,
        order_id: order.order_id,
        amount: order.amount,
        currency: order.currency,
        name: state.config.business_name || "DreamJob",
        description: `DreamJob Pro, ${pay().days} days`,
        image: location.origin + "/static/logo-512.png",
        theme: { color: "#111827" },
        prefill: state.user ? { email: state.user.email, name: state.user.name || "" } : {},
        modal: { confirm_close: true, ondismiss: done },
        handler: async (resp) => {
          btn.textContent = "Confirming payment…";
          try {
            const p = await api("/api/pay/verify", {
              method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(resp),
            });
            activatePass(p);
          } catch (err) {
            showError("proError", `${err.message} Your payment ID is ${resp.razorpay_payment_id}. Keep it to restore your purchase.`);
          } finally { done(); }
        },
      });
      rzp.on("payment.failed", (r) => {
        const why = r?.error?.description || "The payment did not go through.";
        showError("proError", `${why} No money was taken, or it will be returned by your bank. You can try again.`);
      });
      rzp.open();
    } catch (err) {
      showError("proError", err.message);
      done();
    }
  });

  $("restoreToggle").addEventListener("click", (e) => {
    const f = $("restoreForm");
    f.hidden = !f.hidden;
    if (state.user && !$("restoreEmail").value) $("restoreEmail").value = state.user.email;
    e.currentTarget.setAttribute("aria-expanded", String(!f.hidden));
    if (!f.hidden) $("restoreId").focus();
  });
  $("restoreForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = $("restoreId").value.trim();
    const email = $("restoreEmail").value.trim();
    hideError("proError");
    if (!/^pay_[A-Za-z0-9]+$/.test(id)) return showError("proError", "Enter the payment ID from your receipt. It starts with pay_");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return showError("proError", "Enter the email address you paid with.");
    const btn = $("restoreBtn");
    btn.disabled = true;
    btn.textContent = "Checking…";
    try {
      activatePass(await api("/api/pay/restore", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ payment_id: id, email }),
      }));
    } catch (err) {
      showError("proError", err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Restore";
    }
  });

  // A pass the server no longer accepts (expired or refunded): drop it and fall back to a free option.
  function handlePaywall(err) {
    if (err.status !== 402) return false;
    state.pass = null;
    store.del("dj.pass");
    state.pendingTop = state.prefs.top;
    state.prefs.top = DEFAULTS.top;
    store.set("dj.prefs.v2", state.prefs);
    renderPro();
    syncFilters();
    openPro(err.message);
    return true;
  }

  // ------------------------------------------------------------------ sign in
  const AUTH_ERRORS = {
    link_expired: "That sign-in link has expired or was already used. Request a new one.",
    google_cancelled: "Google sign-in was cancelled.",
    google_failed: "Google sign-in didn't complete. Please try again.",
    google_unverified: "Your Google account's email address isn't verified. Use email sign-in instead.",
    google_unavailable: "Google sign-in isn't available right now. Use email sign-in instead.",
  };

  function renderAuth() {
    const any = state.auth.email || state.auth.google;
    const u = state.user;
    $("signInBtn").hidden = !any || !!u;
    $("account").hidden = !u;
    if (u) {
      const label = (u.name || u.email).trim();
      const btn = $("accountBtn");
      btn.textContent = "";
      if (u.picture && /^https:\/\//.test(u.picture)) {
        const img = document.createElement("img");
        img.src = u.picture; img.alt = ""; img.referrerPolicy = "no-referrer";
        img.onerror = () => { btn.textContent = label.charAt(0).toUpperCase(); };
        btn.appendChild(img);
      } else {
        btn.textContent = label.charAt(0).toUpperCase();
      }
      $("accountName").textContent = u.name || "Signed in";
      $("accountEmail").textContent = u.email;
    }
    $("googleBtn").hidden = !state.auth.google;
    $("emailForm").hidden = !state.auth.email;
    $("authOr").hidden = !(state.auth.google && state.auth.email);
  }

  function openAuth(reason) {
    if (!(state.auth.email || state.auth.google)) return;
    $("authStart").hidden = false;
    $("authSent").hidden = true;
    hideError("authError");
    $("authLead").textContent = reason || "Save time on every search. No password needed.";
    const next = location.pathname + location.search;
    $("googleBtn").href = "/auth/google/start?next=" + encodeURIComponent(next);
    const d = $("authDialog");
    if (!d.open) d.showModal();
  }

  async function loadAuth() {
    try {
      const me = await api("/api/auth/me");
      state.user = me.user;
      state.auth = { email: !!me.email, google: !!me.google, required: !!me.required };
    } catch { /* sign-in stays hidden */ }
    renderAuth();
    const params = new URLSearchParams(location.search);
    const err = params.get("auth_error");
    if (params.get("signed_in") && state.user) toast(`Signed in as ${state.user.email}`);
    if (err) { openAuth(); showError("authError", AUTH_ERRORS[err] || "Sign-in didn't complete. Please try again."); }
    if (params.has("signed_in") || err) {
      params.delete("signed_in"); params.delete("auth_error");
      history.replaceState(null, "", location.pathname + (params.toString() ? "?" + params : "") + location.hash);
    }
  }

  $("signInBtn").addEventListener("click", () => openAuth());
  $("authDialog").addEventListener("click", (e) => { if (e.target === $("authDialog")) $("authDialog").close(); });
  $("authBack").addEventListener("click", () => { $("authSent").hidden = true; $("authStart").hidden = false; $("authEmail").focus(); });
  $("emailForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    hideError("authError");
    const email = $("authEmail").value.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return showError("authError", "Enter a valid email address.");
    const btn = $("emailBtn");
    btn.disabled = true;
    btn.textContent = "Sending…";
    try {
      const r = await api("/api/auth/email/start", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, next: location.pathname }),
      });
      $("authSentText").textContent = `${r.message} It was sent to ${email}.`;
      $("authStart").hidden = true;
      $("authSent").hidden = false;
    } catch (err) {
      showError("authError", err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Email me a sign-in link";
    }
  });

  const menu = $("accountMenu");
  $("accountBtn").addEventListener("click", (e) => {
    e.stopPropagation();
    menu.hidden = !menu.hidden;
    $("accountBtn").setAttribute("aria-expanded", String(!menu.hidden));
  });
  document.addEventListener("click", (e) => { if (!menu.hidden && !menu.contains(e.target)) { menu.hidden = true; $("accountBtn").setAttribute("aria-expanded", "false"); } });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !menu.hidden) { menu.hidden = true; $("accountBtn").focus(); } });
  $("signOutBtn").addEventListener("click", async () => {
    try { await api("/api/auth/logout", { method: "POST" }); } catch { /* cookie may already be gone */ }
    state.user = null;
    menu.hidden = true;
    renderAuth();
    toast("You're signed out.");
  });

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
    top.addEventListener("change", () => {
      if (needsPro(top.value) && !passActive()) {
        state.pendingTop = top.value;
        top.value = String(state.prefs.top);
        openPro();
        return;
      }
      setPref("top", top.value);
    });

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
    const exp = container.querySelector('[data-name="exp_match"]');
    exp.id = `${prefix}-exp`;
    exp.addEventListener("change", () => setPref("exp_match", exp.checked));
  }

  function syncFilters() {
    document.querySelectorAll(".seg").forEach((g) => {
      g.querySelectorAll("input").forEach((i) => { i.checked = String(state.prefs[g.dataset.name]) === i.value; });
    });
    document.querySelectorAll('[data-name="top"]').forEach((s) => { s.value = String(state.prefs.top); });
    document.querySelectorAll('[data-name="location"]').forEach((i) => { if (i !== document.activeElement) i.value = state.prefs.location; });
    document.querySelectorAll('[data-name="remote_only"]').forEach((i) => { i.checked = !!state.prefs.remote_only; });
    document.querySelectorAll('[data-name="exp_match"]').forEach((i) => { i.checked = state.prefs.exp_match !== false; });
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
  fileInput.addEventListener("change", () => { setFile(fileInput.files[0]); fileInput.value = ""; });
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

  // Progress messages while a deep search runs (it waits for every connected job site, up to ~20 s).
  function loadingMessages() {
    const portals = state.config.live_portals || [];
    const steps = ["Analysing your résumé…"];
    if (portals.length) {
      const named = portals.slice(0, 4).join(", ") + (portals.length > 4 ? " and more" : "");
      steps.push(`Searching ${named}…`, "Checking more job sites for the newest openings…");
    } else {
      steps.push("Scanning company career sites and job boards…");
    }
    steps.push("Matching roles to your experience and skills…", "Ranking your best matches…");
    let i = 0;
    $("loadingText").textContent = steps[0];
    const t = setInterval(() => { i = Math.min(i + 1, steps.length - 1); $("loadingText").textContent = steps[i]; }, 2600);
    return () => clearInterval(t);
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
    // pasted text wins when the text box is open (or when no file was chosen)
    if (state.auth.required && !state.user) { openAuth("Sign in to see your matches. It takes a few seconds."); return; }
    const usePaste = text.length >= 80 && (!state.file || !$("pasteWrap").hidden);
    if (!state.file && !usePaste) {
      return showError("formError", text ? "Paste a bit more of your résumé (at least a few lines)." : "Add your résumé first: drop a file above or paste the text.");
    }
    hideError("formError");
    // pick up a typed location even if the user didn't press Enter
    const loc = document.querySelector("#search-location");
    if (loc) state.prefs.location = loc.value.trim();
    store.set("dj.prefs.v2", state.prefs);

    const fd = new FormData();
    if (usePaste) fd.append("text", text); else fd.append("file", state.file);
    fd.append("window", state.prefs.window);
    fd.append("top", state.prefs.top);
    fd.append("location", state.prefs.location);
    fd.append("remote_only", state.prefs.remote_only ? "true" : "false");
    fd.append("exp_match", state.prefs.exp_match === false ? "false" : "true");

    const req = startRequest();
    $("submitBtn").disabled = true;
    const stopMessages = loadingMessages();
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
      if (err.status === 401) { openAuth(err.message); return; }
      if (!handlePaywall(err)) showError("formError", err.message);
    } finally {
      stopMessages();
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
          exp_match: state.prefs.exp_match !== false,
        }),
      });
      if (req.id !== state.seq) return; // a newer filter change is already on its way
      renderResults(data);
    } catch (err) {
      if (err.name === "AbortError") return;
      if (req.id === state.seq && err.status === 401) openAuth(err.message);
      else if (req.id === state.seq && !handlePaywall(err)) showError("resultsError", err.message);
    } finally {
      if (req.id === state.seq) {
        $("updating").hidden = true;
        $("jobList").classList.remove("is-updating");
      }
    }
  }

  $("updateBtn").addEventListener("click", () => { addTypedSkills(); runMatch(); });
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
    $("clearSkills").hidden = skills.length === 0;
    const frag = document.createDocumentFragment();
    skills.forEach((s) => {
      const li = document.createElement("li");
      li.innerHTML = `<span>${esc(s)}</span><button type="button" aria-label="Remove ${esc(s)}">×</button>`;
      li.querySelector("button").addEventListener("click", () => {
        state.profile.skills = state.profile.skills.filter((x) => x !== s);
        renderChips();
      });
      frag.appendChild(li);
    });
    ul.appendChild(frag);
  }

  // "python, sql; power bi" -> three skills. Returns how many were new.
  function addTypedSkills() {
    const raw = $("addSkill").value;
    if (!raw.trim() || !state.profile) return 0;
    const have = new Set((state.profile.skills || []).map((s) => s.toLowerCase()));
    const fresh = [];
    raw.split(/[,;\n]+/).map((s) => s.trim().replace(/\s+/g, " ")).filter((s) => s.length >= 1 && s.length <= 60).forEach((s) => {
      if (!have.has(s.toLowerCase())) { have.add(s.toLowerCase()); fresh.push(s); }
    });
    const room = MAX_SKILLS - (state.profile.skills || []).length;
    state.profile.skills = [...fresh.slice(0, Math.max(0, room)), ...(state.profile.skills || [])];
    $("addSkill").value = "";
    renderChips();
    if (fresh.length > room) toast(`You can keep up to ${MAX_SKILLS} skills. Remove a few to add more.`);
    return fresh.length;
  }

  $("addSkillForm").addEventListener("submit", (e) => { e.preventDefault(); addTypedSkills(); $("addSkill").focus(); });
  $("clearSkills").addEventListener("click", () => {
    if (!state.profile) return;
    state.profile.skills = [];
    renderChips();
    $("addSkill").focus();
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
      ["LinkedIn", `https://www.linkedin.com/jobs/search/?keywords=${q}&location=${l}&f_TPR=r${w.hours * 3600}${remote ? "&f_WT=2" : ""}`],
      ["Indeed", `https://${india ? "in." : uk ? "uk." : "www."}indeed.com/jobs?q=${q}&l=${remote && !loc ? "Remote" : l}&fromage=${w.days}${remote ? "&remotejob=032b3046-06a3-4876-8dfd-474eb5e7ed11" : ""}`],
      ["Naukri", `https://www.naukri.com/${slug(role) || "jobs"}-jobs${loc ? "-in-" + slug(loc) : ""}?k=${q}${loc ? "&l=" + l : ""}&jobAge=${near(w.days, [1, 3, 7, 15, 30])}${remote ? "&wfhType=2" : ""}`],
      ["Glassdoor", `https://www.glassdoor.${india ? "co.in" : uk ? "co.uk" : "com"}/Job/jobs.htm?sc.keyword=${q}&locKeyword=${l}&fromAge=${near(w.days, [1, 3, 7, 14, 30])}${remote ? "&remoteWorkType=1" : ""}`],
      ["Google Jobs", `https://www.google.com/search?q=${encodeURIComponent(`${role} jobs ${remote ? "remote" : loc}`.trim())}&ibp=htl;jobs&htichips=date_posted:${{ "24h": "today", "48h": "3days", "72h": "3days", "1w": "week", "1m": "month" }[state.prefs.window]}`],
      ["Wellfound", `https://wellfound.com/jobs?query=${q}`],
    ];
    $("extLinks").innerHTML = sites.map(([name, url]) =>
      `<li><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${name}<span>Opens in new tab</span></a></li>`).join("");
    $("elsewhereHint").textContent = `“${role || "your role"}”${loc ? " in " + loc : ""}, posted in ${w.label}${remote ? ", remote only" : ""}. Naukri and Glassdoor use their nearest date option.`;
  }

  // ------------------------------------------------------------------ results
  const FIT = {
    good: ["Strong experience fit", "fit-good"],
    over: ["Exceeds the experience required", "fit-over"],
    close: ["Close to the requirement", "fit-close"],
    short: ["Below the experience required", "fit-short"],
    unknown: ["No experience requirement stated", "fit-unknown"],
  };

  function bar(label, v) {
    if (v === null || v === undefined) return "";
    return `<div class="bar"><span>${label}</span><span class="bar-track"><span class="bar-fill" style="width:${Math.max(2, Math.min(100, v))}%"></span></span><span class="bar-num">${v}%</span></div>`;
  }

  function jobItem(j) {
    const li = document.createElement("li");
    li.className = "job";
    const matched = j.matched_skills || [];
    const skills = matched.map((s) => `<span class="skill">${esc(s)}</span>`).join("");
    const missing = (j.missing_skills || []).join(", ");
    const why = (j.reasons || []).filter((r) => !/years; you have/.test(r)).join(" · ");
    const exp = j.experience || { fit: "unknown", text: "" };
    const [fitLabel, fitClass] = FIT[exp.fit] || FIT.unknown;
    const b = j.breakdown || {};
    const hasDesc = !!(j.description || j.snippet);
    li.innerHTML = `
      <div class="job-top">
        <div>
          <h3><a href="${esc(safeUrl(j.url))}" target="_blank" rel="noopener noreferrer">${esc(j.title)}</a></h3>
          <p class="company"><b>${esc(j.company || "Company not listed")}</b> · ${esc(j.location || "Location not listed")}${j.remote ? '<span class="badge">Remote</span>' : ""}${Date.now() / 1000 - j.posted_at < 86400 ? '<span class="badge badge-new">New</span>' : ""}</p>
        </div>
        <span class="score ${j.score >= 70 ? "strong" : ""}" title="How closely this role matches your résumé">${j.score}% match</span>
      </div>
      <p class="meta">
        <span class="posted" title="${esc(new Date(j.posted_at * 1000).toLocaleString())}">Posted ${esc(ago(j.posted_at))} (${esc(fullDate(j.posted_at))})</span>
        <span>Source: ${esc(j.source)}</span>
        ${j.salary ? `<span>${esc(j.salary)}</span>` : ""}
        ${j.job_type ? `<span>${esc(j.job_type)}</span>` : ""}
      </p>
      <p class="exp ${fitClass}"><span class="dot" aria-hidden="true"></span><b>${esc(fitLabel)}.</b> ${esc(exp.text)}</p>
      ${why ? `<p class="why">${esc(why)}</p>` : ""}
      ${skills ? `<div class="skills" aria-label="Skills you have">${skills}</div>` : ""}
      ${missing ? `<p class="missing">Missing from your résumé: ${esc(missing)}</p>` : ""}
      <div class="job-actions">
        <a class="btn btn-primary" href="${esc(safeUrl(j.url))}" target="_blank" rel="noopener noreferrer">Apply now</a>
        ${hasDesc ? '<button type="button" class="text-btn" data-act="desc" aria-expanded="false">View description</button>' : ""}
        <button type="button" class="text-btn" data-act="why" aria-expanded="false">Score breakdown</button>
      </div>
      <div class="breakdown" hidden>
        ${bar("Required skills you have", b.skills)}
        ${bar("Role fit", b.title)}
        ${bar("Experience fit", b.experience)}
      </div>
      ${hasDesc ? `<div class="desc" hidden></div>` : ""}`;
    li.querySelectorAll("[data-act]").forEach((btn) => btn.addEventListener("click", () => {
      const panel = li.querySelector(btn.dataset.act === "desc" ? ".desc" : ".breakdown");
      if (btn.dataset.act === "desc" && !panel.dataset.ready) {
        panel.textContent = j.description || j.snippet; // textContent: description text is never treated as HTML
        panel.dataset.ready = "1";
      }
      panel.hidden = !panel.hidden;
      btn.setAttribute("aria-expanded", String(!panel.hidden));
    }));
    return li;
  }

  function renderResults(data) {
    const list = $("jobList");
    list.innerHTML = "";
    const n = data.results.length;
    const w = WINDOWS[data.window];
    $("resultsTitle").textContent = n ? `Your top ${n} match${n === 1 ? "" : "es"}` : "No matches yet";
    const filters = [data.location ? `in ${data.location}` : "", data.remote_only ? "remote only" : "",
      data.exp_match ? "matched to your experience" : ""].filter(Boolean).join(", ");
    $("resultsMeta").textContent = `Posted within ${w.label}${filters ? ", " + filters : ""} · ranked from ${data.considered.toLocaleString()} openings`;
    const srcs = Object.entries(data.by_source || {}).map(([k, v]) => `${k} ${v.toLocaleString()}`).join(" · ");
    const hid = data.hidden_experience || 0;
    $("resultsSources").textContent = (srcs ? `Sources: ${srcs}` : "")
      + (data.exp_match && hid ? ` · ${hid.toLocaleString()} roles hidden because their experience requirement doesn't fit yours` : "");
    $("emptyState").hidden = n > 0;
    if (!n) {
      const canWiden = data.window !== "1m";
      const hasFilters = data.location || data.remote_only;
      $("emptyState").innerHTML = `
        <h3>No strong matches within ${esc(w.label)}${hasFilters ? " for these filters" : ""}</h3>
        <p>Widen the date range${hasFilters ? ", clear the location filters" : ""} or add more skills. You can also continue your search on the job sites listed alongside.</p>
        ${canWiden ? '<button type="button" class="btn btn-secondary" data-act="month">Show the past month</button>' : ""}
        ${hasFilters ? '<button type="button" class="btn btn-secondary" data-act="clear">Clear location filters</button>' : ""}
        ${data.exp_match && hid ? '<button type="button" class="btn btn-secondary" data-act="exp">Include all experience levels</button>' : ""}`;
      $("emptyState").querySelector('[data-act="month"]')?.addEventListener("click", () => setPref("window", "1m"));
      $("emptyState").querySelector('[data-act="exp"]')?.addEventListener("click", () => setPref("exp_match", false));
      $("emptyState").querySelector('[data-act="clear"]')?.addEventListener("click", () => { state.prefs.location = ""; setPref("remote_only", false); });
    }
    const frag = document.createDocumentFragment();
    data.results.forEach((j, i) => { const li = jobItem(j); li.style.setProperty("--i", Math.min(i, 12)); frag.appendChild(li); });
    list.appendChild(frag);
  }

  // ------------------------------------------------------------------ boot
  async function loadStats() {
    try {
      const s = await api("/api/stats");
      const mins = s.last_refresh ? Math.round((Date.now() / 1000 - s.last_refresh) / 60) : null;
      $("indexStatus").innerHTML = s.jobs
        ? `${s.jobs.toLocaleString()} live jobs<span class="upd"> · updated ${mins === null || mins < 1 ? "just now" : mins + " min ago"}</span>`
        : "Building the job index. This takes about a minute after a restart.";
      countUp($("statJobs"), s.jobs);
      countUp($("statToday"), s.by_window ? s.by_window["24h"] : 0);
      countUp($("statCompanies"), s.companies);
      if (s.jobs) $("heroLive").textContent = `Live index · updated ${mins === null || mins < 1 ? "just now" : mins + " min ago"}`;
      $("sourcesNote").textContent = `Searches ${s.companies} company career sites and ${(s.enabled || []).length - 1} job boards.`;
      if (!s.jobs) setTimeout(loadStats, 8000);
    } catch { $("indexStatus").textContent = ""; }
  }

  async function loadSkills() {
    try {
      const { skills } = await api("/api/skills");
      $("skillList").innerHTML = skills.map((s) => `<option value="${esc(s)}">`).join("");
    } catch { /* optional */ }
  }

  async function loadConfig() {
    try { state.config = await api("/api/config"); } catch { /* payments stay off */ }
    loadPass();
    // a stored Top 20/30 without a pass (e.g. after it expired) falls back to the free default
    if (needsPro(state.prefs.top) && !passActive()) { state.prefs.top = DEFAULTS.top; store.set("dj.prefs.v2", state.prefs); }
    renderPro();
    syncFilters();
    const params = new URLSearchParams(location.search);
    if (params.get("upgrade") && pay().enabled) {
      history.replaceState(null, "", location.pathname);
      if (!passActive()) openPro();
    }
    if (passActive()) { // confirm the pass is still valid (e.g. not refunded); quiet if offline
      api("/api/pay/status", { method: "POST" }).then((r) => {
        if (r && !r.active) { state.pass = null; store.del("dj.pass"); renderPro(); }
      }).catch(() => {});
    }
  }

  // ------------------------------------------------------------------ landing-page motion
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function countUp(el, target) {
    if (!el || !target) return;
    const prev = Number(el.dataset.v || 0);
    el.dataset.v = target;
    if (calm || prev === target) { el.textContent = target.toLocaleString(); return; }
    const start = performance.now(), dur = 900;
    const tick = (t) => {
      const k = Math.min(1, (t - start) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = Math.round(prev + (target - prev) * e).toLocaleString();
      if (k < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
  if ("IntersectionObserver" in window && !calm) {
    document.documentElement.classList.add("motion");
    const io = new IntersectionObserver((entries) => entries.forEach((en) => {
      if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
    }), { rootMargin: "0px 0px -8% 0px" });
    document.querySelectorAll(".reveal").forEach((el) => io.observe(el));
  } else {
    document.querySelectorAll(".reveal").forEach((el) => el.classList.add("in"));
  }
  $("ctaBtn").addEventListener("click", (e) => {
    e.preventDefault();
    $("searchForm").scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "center" });
    setTimeout(() => drop.focus({ preventScroll: true }), calm ? 0 : 450);
  });

  mountFilters(document.querySelector('[data-filters="search"]'), "search");
  mountFilters(document.querySelector('[data-filters="results"]'), "results");
  syncFilters();
  loadConfig();
  loadAuth();
  loadStats();
  loadSkills();
})();
