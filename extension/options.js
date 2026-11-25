(async () => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const LISTS = ["experience", "education", "answers"];
  const MAX_RESUME = 5 * 1024 * 1024;

  let { profile = {}, settings = {} } = await chrome.storage.local.get(["profile", "settings"]);
  let dirty = false;

  // ---------------------------------------------------------------- simple fields
  function fillSimple() {
    document.querySelectorAll("[data-k]").forEach((el) => { el.value = profile[el.dataset.k] ?? ""; });
    $("server").value = profile.server || "";
    $("setButton").checked = settings.hideButton !== true;
    $("setSections").checked = settings.addSections !== false;
    const hidden = settings.hiddenOn || [];
    $("hiddenSites").innerHTML = hidden.length
      ? `Button hidden on: ${hidden.map((h) => `<code>${h.replace(/[<>&"]/g, "")}</code>`).join(", ")} <button type="button" class="text-btn" id="unhide">Show it again everywhere</button>` : "";
    if (hidden.length) $("unhide").addEventListener("click", () => { settings.hiddenOn = []; markDirty(); fillSimple(); });
    showResume();
  }

  function showResume() {
    $("resumeInfo").textContent = profile.resume
      ? `Attached to applications: ${profile.resume.name} (${Math.round(profile.resume.size / 1024)} KB).` : "No résumé saved yet.";
  }

  // ---------------------------------------------------------------- repeatable lists
  function monthSelect(sel) {
    sel.innerHTML = '<option value="">Month</option>' + MONTHS.map((m, i) => `<option value="${i + 1}">${m}</option>`).join("");
  }

  function get(obj, path) { return path.split(".").reduce((o, k) => (o ? o[k] : undefined), obj); }
  function set(obj, path, v) {
    const ks = path.split(".");
    let o = obj;
    ks.slice(0, -1).forEach((k) => { o[k] = o[k] || {}; o = o[k]; });
    o[ks[ks.length - 1]] = v;
  }

  function renderList(name) {
    const box = $(name);
    box.innerHTML = "";
    const items = profile[name] || [];
    if (!items.length) {
      box.innerHTML = `<p class="muted small empty">Nothing added yet.</p>`;
      return;
    }
    items.forEach((item, i) => {
      const node = $(`tpl-${name}`).content.firstElementChild.cloneNode(true);
      node.querySelectorAll("select[data-f$='month']").forEach(monthSelect);
      node.querySelectorAll("[data-f]").forEach((el) => {
        const v = get(item, el.dataset.f);
        if (el.type === "checkbox") el.checked = !!v; else el.value = v ?? "";
        el.addEventListener("input", () => {
          const val = el.type === "checkbox" ? el.checked : el.type === "number" || el.tagName === "SELECT" && el.dataset.f.endsWith("month")
            ? (el.value === "" ? null : Number(el.value)) : el.value;
          set(profile[name][i], el.dataset.f, val);
          markDirty();
        });
      });
      node.querySelector("[data-remove]").addEventListener("click", () => {
        profile[name].splice(i, 1);
        markDirty();
        renderList(name);
      });
      box.appendChild(node);
    });
  }

  document.querySelectorAll("[data-add]").forEach((b) => b.addEventListener("click", () => {
    const name = b.dataset.add;
    profile[name] = profile[name] || [];
    profile[name].push(name === "answers" ? { q: "", a: "" } : name === "experience"
      ? { title: "", company: "", location: "", start: {}, end: {}, current: false, description: "" }
      : { school: "", degree: "", field: "", start: {}, end: {}, gpa: "" });
    markDirty();
    renderList(name);
    $(name).lastElementChild.querySelector("input").focus();
  }));

  // ---------------------------------------------------------------- saving
  function markDirty() { dirty = true; $("saveState").textContent = "Unsaved changes"; }
  document.querySelectorAll("[data-k]").forEach((el) => el.addEventListener("input", markDirty));
  $("server").addEventListener("input", markDirty);
  $("setButton").addEventListener("change", markDirty);
  $("setSections").addEventListener("change", markDirty);

  function collect() {
    document.querySelectorAll("[data-k]").forEach((el) => {
      profile[el.dataset.k] = el.type === "number" ? (el.value === "" ? "" : Number(el.value)) : el.value.trim();
    });
    profile.server = $("server").value.trim().replace(/\/+$/, "");
    settings.hideButton = !$("setButton").checked;
    settings.addSections = $("setSections").checked;
    LISTS.forEach((n) => { profile[n] = (profile[n] || []).filter((x) => Object.values(x).some((v) => v && (typeof v !== "object" || v.year))); });
  }

  async function save() {
    collect();
    try {
      await chrome.storage.local.set({ profile, settings });
      dirty = false;
      $("saveState").textContent = "Saved";
      LISTS.forEach(renderList);
    } catch (e) {
      $("saveState").textContent = "Could not save: " + e.message;
    }
  }
  $("save").addEventListener("click", save);
  document.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(); } });
  window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

  // ---------------------------------------------------------------- résumé file
  $("resumeFile").addEventListener("change", () => {
    const f = $("resumeFile").files[0];
    if (!f) return;
    if (f.size > MAX_RESUME) { $("resumeInfo").textContent = "That file is larger than 5 MB. Choose a smaller one."; return; }
    const reader = new FileReader();
    reader.onload = () => {
      profile.resume = { name: f.name, type: f.type || "application/pdf", size: f.size, data: reader.result };
      markDirty();
      showResume();
    };
    reader.readAsDataURL(f);
  });

  $("importBtn").addEventListener("click", async () => {
    const state = $("importState");
    const f = $("resumeFile").files[0];
    const server = $("server").value.trim().replace(/\/+$/, "");
    state.className = "small";
    if (!f && !profile.resume) { state.textContent = "Choose your résumé file first."; return; }
    let origin;
    try { origin = new URL(server).origin; } catch { state.textContent = "Enter your DreamJob server address, for example https://your-site.hf.space"; return; }
    if (!/^https:|^http:\/\/(localhost|127\.0\.0\.1)/.test(origin)) { state.textContent = "Use an https:// address (or http://localhost for testing)."; return; }
    const granted = await chrome.permissions.request({ origins: [origin + "/*"] }).catch(() => false);
    if (!granted) { state.textContent = "Permission to contact that server was not given."; return; }
    state.textContent = "Reading your résumé…";
    try {
      const fd = new FormData();
      const blob = f || await (await fetch(profile.resume.data)).blob();
      fd.append("file", blob, f ? f.name : profile.resume.name);
      const r = await fetch(origin + "/api/profile/extract", { method: "POST", body: fd });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.error || `The server answered ${r.status}.`);
      collect();
      const c = body.contact || {};
      let n = 0;
      for (const k of ["first_name", "last_name", "email", "phone", "linkedin", "github", "website"]) {
        if (c[k] && !profile[k]) { profile[k] = c[k]; n++; }
      }
      if (body.location && !profile.city) { profile.city = body.location; n++; }
      if (body.years && !profile.years) { profile.years = body.years; n++; }
      if ((body.experience || []).length && !(profile.experience || []).length) {
        profile.experience = body.experience.map((x) => ({ description: "", ...x })); n += body.experience.length;
      }
      if ((body.education || []).length && !(profile.education || []).length) {
        profile.education = body.education.map((x) => ({ field: "", gpa: "", ...x })); n += body.education.length;
      }
      if (body.skills && body.skills.length) profile.skills = body.skills;
      profile.server = origin;
      fillSimple();
      LISTS.forEach(renderList);
      markDirty();
      state.textContent = n ? `Added ${n} item${n === 1 ? "" : "s"}. Check them, then press Save profile.` : "Nothing new found. Fields you had already filled were kept.";
      state.className = "small ok";
    } catch (e) {
      state.textContent = "Import failed: " + (e.message || "the server could not be reached.");
      state.className = "small warn";
    }
  });

  // ---------------------------------------------------------------- backup
  $("exportBtn").addEventListener("click", () => {
    collect();
    const blob = new Blob([JSON.stringify({ profile, settings, exported: new Date().toISOString() }, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "dreamjob-profile.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  });
  $("importJson").addEventListener("change", async () => {
    const f = $("importJson").files[0];
    if (!f) return;
    try {
      const data = JSON.parse(await f.text());
      if (!data || typeof data.profile !== "object") throw new Error("not a DreamJob backup");
      profile = data.profile;
      settings = data.settings || {};
      fillSimple();
      LISTS.forEach(renderList);
      markDirty();
      $("saveState").textContent = "Backup loaded. Press Save profile to keep it.";
    } catch (e) {
      $("saveState").textContent = "That file is not a DreamJob backup.";
    }
  });
  $("wipe").addEventListener("click", async () => {
    if (!confirm("Delete your saved profile, answers and résumé from this browser? This cannot be undone.")) return;
    await chrome.storage.local.clear();
    profile = {};
    settings = {};
    dirty = false;
    fillSimple();
    LISTS.forEach(renderList);
    $("saveState").textContent = "All data deleted";
  });

  fillSimple();
  LISTS.forEach(renderList);
})();
