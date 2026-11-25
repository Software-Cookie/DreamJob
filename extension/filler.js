/* DreamJob Autofill: fills job application forms from a saved profile.
 * Works on any page; tuned for Workday, Greenhouse, Lever, Ashby, SmartRecruiters, Workable and iCIMS.
 * It only fills fields. It never clicks Submit, Next or any consent box: you review and submit yourself.
 */
(() => {
  "use strict";
  if (globalThis.DreamJobFiller) return;

  const MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"];
  // "workExperience-1--roleDescription" -> "work experience 1 role description"
  const norm = (s) => String(s ?? "").replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase().replace(/[’']/g, "")
    .replace(/[^a-z0-9+#]+/g, " ").trim();
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const has = (v) => v !== undefined && v !== null && String(v).trim() !== "";

  // ------------------------------------------------------------------ describing a field
  function text(node) { return node ? node.textContent || "" : ""; }

  function ownLabel(el) {
    const parts = [];
    if (el.getAttribute("aria-label")) parts.push(el.getAttribute("aria-label"));
    const lb = el.getAttribute("aria-labelledby");
    if (lb) lb.split(/\s+/).forEach((id) => parts.push(text(document.getElementById(id))));
    if (el.id) {
      try { document.querySelectorAll(`label[for="${CSS.escape(el.id)}"]`).forEach((l) => parts.push(text(l))); } catch { /* bad id */ }
    }
    const wrap = el.closest("label");
    if (wrap && el.type !== "radio" && el.type !== "checkbox") parts.push(text(wrap));
    return parts.join(" ");
  }

  function containerLabel(el) {
    const box = el.closest('[data-automation-id^="formField"], .application-question, .application-field, .field, .form-group, .form-field, [class*="question" i], [class*="Field" i], fieldset, li');
    if (!box) return "";
    const l = box.querySelector("label, legend, [data-automation-id=\"richText\"], [class*=\"label\" i]");
    return l && !l.contains(el) ? text(l) : (box.matches("fieldset") ? text(box.querySelector("legend")) : "");
  }

  function describe(el) {
    const auto = [el.getAttribute("data-automation-id"), el.closest("[data-automation-id^=\"formField\"]")?.getAttribute("data-automation-id")];
    const own = ownLabel(el);
    const raw = [own || containerLabel(el), el.getAttribute("placeholder"), el.name, el.id, ...auto, el.getAttribute("autocomplete")].filter(Boolean).join(" ");
    return " " + norm(raw).slice(0, 300) + " ";
  }

  // The question text for a radio group or checkbox (not the option's own text).
  function questionFor(el) {
    const group = el.closest('[role="radiogroup"], fieldset, [data-automation-id^="formField"], .application-question, .form-group, .field, li');
    if (!group) return describe(el);
    const lb = group.getAttribute("aria-labelledby");
    const q = (lb && text(document.getElementById(lb))) || text(group.querySelector("legend, label:not(:has(input)), [class*=\"label\" i]"));
    return " " + norm(q || group.getAttribute("aria-label") || "").slice(0, 300) + " ";
  }

  // Nearest heading before an element: tells which section (work experience, education) it is in.
  let headings = [];
  function collectHeadings() {
    headings = [...document.querySelectorAll('h1, h2, h3, h4, legend, [role="heading"], [data-automation-id*="Heading" i], [data-automation-id*="sectionHeader" i]')];
  }
  function sectionOf(el) {
    const id = norm([el.id, el.name, el.getAttribute("data-automation-id"),
      el.closest("[data-automation-id*=\"workExperience\" i], [data-automation-id*=\"education\" i], [id*=\"experience\" i], [id*=\"education\" i]")?.getAttribute("data-automation-id"),
      el.closest("[id*=\"experience\" i], [id*=\"education\" i]")?.id].join(" "));
    if (/work experience|workexperience|employment|experience \d/.test(id)) return "work";
    if (/education|school/.test(id)) return "edu";
    let h = null;
    for (const node of headings) {
      if (node.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) h = node; else break;
    }
    const t = norm(text(h));
    if (/work experience|employment|work history|professional experience|experience/.test(t)) return "work";
    if (/education|academic/.test(t)) return "edu";
    return "";
  }

  // ------------------------------------------------------------------ setting values (React/Angular safe)
  function setValue(el, value) {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
      : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    el.focus({ preventScroll: true });
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, key: "Tab" }));
    el.blur();
    el.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
  }

  function setChecked(el, on) {
    if (el.checked === on) return;
    el.click(); // a real click keeps React/Workday state in sync
    if (el.checked !== on) {
      el.checked = on;
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && getComputedStyle(el).visibility !== "hidden";
  const editable = (el) => !el.disabled && !el.readOnly && el.getAttribute("aria-disabled") !== "true";

  function score(optText, want) {
    const o = norm(optText), w = norm(want);
    if (!o || !w) return 0;
    if (o === w) return 100;
    if (o.startsWith(w) || w.startsWith(o)) return 80;
    if ((" " + o + " ").includes(" " + w + " ")) return 60;
    if (o.includes(w)) return 40;
    return 0;
  }

  function pickOption(select, want) {
    let best = null, bestScore = 0;
    for (const opt of select.options) {
      if (opt.disabled || !opt.value && !opt.text.trim()) continue;
      const s = Math.max(score(opt.text, want), score(opt.value, want));
      if (s > bestScore) { best = opt; bestScore = s; }
    }
    return bestScore >= 40 ? best : null;
  }

  // Workday-style dropdown: a button that opens a listbox somewhere else in the page.
  async function chooseFromListbox(button, want) {
    button.click();
    for (let i = 0; i < 20; i++) {
      await sleep(75);
      const opts = [...document.querySelectorAll('[role="listbox"] [role="option"], [data-automation-id="promptOption"]')].filter(visible);
      if (!opts.length) continue;
      let best = null, bestScore = 0;
      for (const o of opts) {
        const s = score(o.getAttribute("data-automation-label") || o.textContent, want);
        if (s > bestScore) { best = o; bestScore = s; }
      }
      if (best && bestScore >= 40) {
        best.scrollIntoView({ block: "nearest" });
        best.click();
        await sleep(60);
        return true;
      }
      break;
    }
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    button.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    return false;
  }

  // ------------------------------------------------------------------ what goes where
  const yes = (v) => (v === true || /^y/i.test(String(v)) ? "Yes" : v === false || /^n/i.test(String(v)) ? "No" : "");
  const fullName = (p) => [p.first_name, p.middle_name, p.last_name].filter(has).join(" ");
  const monthName = (m) => (m ? MONTHS[m - 1].replace(/^./, (c) => c.toUpperCase()) : "");

  // Order matters: the first matching rule wins, so specific patterns come before general ones.
  const RULES = [
    ["email", / e ?mail /, (p) => p.email],
    ["skip", / extension | ext | otp | verification code | captcha | password /, () => ""],
    ["phone_type", / phone (device )?type /, (p) => p.phone_type || "Mobile"],
    ["phone_code", / (country phone code|phone country|country code|dialing code|dial code|calling code) /, (p) => p.phone_country_code],
    ["phone", / (phone|mobile|telephone|cell|contact number|whatsapp) /, (p) => p.phone],
    ["first", / (first ?name|given ?name|fname|forename|legal name section first) /, (p) => p.first_name],
    ["middle", / middle ?name /, (p) => p.middle_name],
    ["last", / (last ?name|family ?name|surname|lname) /, (p) => p.last_name],
    ["preferred", / (preferred|nick) ?name /, (p) => p.preferred_name || p.first_name],
    // a bare "Name" label only counts at the start of the description, so "Company name" is not a person's name
    ["full", /^ name | (full ?name|your name|legal name|candidate name|applicant name) /, (p) => fullName(p)],
    ["linkedin", / linked ?in /, (p) => p.linkedin],
    ["github", / git ?hub /, (p) => p.github],
    ["twitter", / (twitter|x profile) /, (p) => p.twitter],
    ["website", / (website|portfolio|personal site|blog|homepage|other url|url) /, (p) => p.website],
    ["address2", / (address line 2|address 2|addressline2|apartment|suite) /, (p) => p.address2],
    ["address1", / (address line 1|addressline1|street|address 1|^ address | address ) /, (p) => p.address1],
    ["postal", / (postal|zip|pin ?code|postcode) /, (p) => p.postal_code],
    ["city", / (city|town|locality) /, (p) => p.city],
    ["state", / (state|province|region|county) /, (p) => p.state],
    ["country", / (country|nationality) /, (p) => p.country],
    ["location", / (current location|location|where are you based|where do you live) /, (p) => [p.city, p.state, p.country].filter(has).join(", ")],
    ["cur_company", / (current (company|employer|organization)|present employer|most recent employer) /, (p) => p.experience?.[0]?.company],
    ["cur_title", / (current (job )?title|current (role|position|designation)) /, (p) => p.experience?.[0]?.title],
    ["cur_salary", / (current (salary|ctc|compensation)|present ctc) /, (p) => p.current_salary],
    ["exp_salary", / (expected (salary|ctc|compensation)|salary expectation|desired (salary|pay|compensation)|compensation expectation) /, (p) => p.expected_salary],
    ["notice", / (notice period|earliest start|start date availability|when can you (start|join)|available to start) /, (p) => p.notice_period],
    ["years", / (years of (relevant )?experience|total experience|how many years) /, (p) => p.years],
    ["hear", / (how did you hear|referral source|where did you (find|hear)) /, (p) => p.source],
    ["gender", / gender /, (p) => p.gender],
    ["ethnicity", / (race|ethnicity) /, (p) => p.ethnicity],
    ["veteran", / veteran /, (p) => p.veteran],
    ["disability", / disabilit /, (p) => p.disability],
    ["cover", / cover letter /, (p) => p.cover_letter],
    ["summary", / (summary|about yourself|about you|introduce yourself|headline) /, (p) => p.summary],
  ];

  const WORK = [ // description first: "Role description" is not a job title
    ["description", / (description|responsibilit|achievements|summary) /],
    ["title", / (job title|position title|title|role|designation) /],
    ["company", / (company|employer|organization|organisation) /],
    ["location", / (location|city) /],
  ];
  const EDU = [
    ["school", / (school|university|college|institution) /],
    ["degree", / (degree|qualification) /],
    ["field", / (field of study|major|discipline|specialization|specialisation) /],
    ["gpa", / (gpa|grade|cgpa|percentage|overall result) /],
  ];

  const YESNO = [
    [/ (authori[sz]ed|eligible|right) to work | work (permit|authori[sz]ation) | legally (authori[sz]ed|eligible|allowed) /, "work_authorized"],
    [/ sponsor/, "needs_sponsorship"],
    [/ relocat/, "willing_to_relocate"],
    [/ (18 years|age of 18|over 18|at least 18) /, "over_18"],
    [/ (previously (worked|been employed)|former employee|worked (for|at|with) .{0,40} before|current or former) /, "previously_employed"],
  ];

  function customAnswer(p, q) {
    for (const a of p.answers || []) {
      const k = " " + norm(a.q) + " ";
      if (k.trim() && q.includes(k)) return a.a;
    }
    return null;
  }

  function dateParts(d) {
    if (!d || !d.year) return null;
    return { m: d.month || 1, y: d.year };
  }

  function dateValue(el, d, desc) {
    const pd = dateParts(d);
    if (!pd) return "";
    const mm = String(pd.m).padStart(2, "0");
    if (el.type === "month") return `${pd.y}-${mm}`;
    if (el.type === "date") return `${pd.y}-${mm}-01`;
    if (/ month /.test(desc)) return el.tagName === "SELECT" ? monthName(pd.m) : mm;
    if (/ year /.test(desc)) return String(pd.y);
    const ph = (el.getAttribute("placeholder") || "").toLowerCase();
    if (/yyyy-mm/.test(ph)) return `${pd.y}-${mm}`;
    if (/dd\/mm|mm\/dd/.test(ph)) return ph.startsWith("dd") ? `01/${mm}/${pd.y}` : `${mm}/01/${pd.y}`;
    return `${mm}/${pd.y}`;
  }

  // ------------------------------------------------------------------ main
  async function fill(profile, opts = {}) {
    const p = profile || {};
    const overwrite = !!opts.overwrite;
    const report = { filled: 0, skipped: 0, fields: [], resume: false };
    collectHeadings();
    const mark = (el, key) => {
      report.filled++;
      report.fields.push(key);
      (el.closest('[data-automation-id^="formField"]') || el).classList.add("dj-filled");
    };

    const counters = { work: -1, edu: -1 };
    const all = [...document.querySelectorAll('input, textarea, select, button[aria-haspopup="listbox"]')]
      .filter((el) => visible(el) && editable(el));

    // 1. text-like inputs, textareas, selects and listbox buttons
    for (const el of all) {
      const type = (el.type || "").toLowerCase();
      if (el.tagName === "INPUT" && ["hidden", "submit", "button", "reset", "image", "radio", "checkbox", "file", "password", "search"].includes(type)) continue;
      if (el.tagName === "BUTTON" && !el.matches('[aria-haspopup="listbox"]')) continue;
      const desc = describe(el);
      const isListbox = el.tagName === "BUTTON";
      const current = isListbox ? norm(el.textContent) : el.value;
      const empty = isListbox ? (!current || /^select( one)?$|^choose/.test(current)) : !has(current);
      const section = sectionOf(el);
      const isStart = / (start|from|begin)/.test(desc);
      const isEnd = / (end|to |until|finish|graduat)/.test(desc);
      // count work/education blocks even when a field is skipped, so block N always gets entry N
      if ((section === "work" || section === "edu") && / (title|school|university|institution) /.test(desc) && !isStart && !isEnd
          && !/ (description|responsibilit) /.test(desc)) counters[section]++;
      if (!empty && !overwrite) { report.skipped++; continue; }

      let value = customAnswer(p, desc);
      let key = value != null ? "answer" : "";

      if (value == null && (section === "work" || section === "edu")) {
        const list = section === "work" ? (p.experience || []) : (p.education || []);
        const rules = section === "work" ? WORK : EDU;
        const item = list[Math.max(0, counters[section])];
        if (item) {
          if (isStart || isEnd) {
            value = dateValue(el, isStart ? item.start : (item.current ? null : item.end), desc);
            key = `${section}.${isStart ? "start" : "end"}`;
          } else {
            const r = rules.find(([, re]) => re.test(desc));
            if (r) { value = item[r[0]]; key = `${section}.${r[0]}`; }
          }
        }
      }
      if ((value == null || !has(value)) && (el.tagName === "SELECT" || isListbox)) {
        const hit = YESNO.find(([re]) => re.test(desc)); // yes/no questions shown as dropdowns
        if (hit) { value = yes(p[hit[1]]); key = hit[1]; }
      }
      if (value == null || !has(value)) {
        const r = RULES.find(([, re]) => re.test(desc));
        if (r && r[0] !== "skip") { value = r[2](p); key = r[0]; }
      }
      if (!has(value)) continue;
      value = String(value);

      if (isListbox) {
        if (await chooseFromListbox(el, value)) mark(el, key);
      } else if (el.tagName === "SELECT") {
        const opt = pickOption(el, value);
        if (opt && el.value !== opt.value) { setValue(el, opt.value); mark(el, key); }
      } else {
        if (type === "number") value = String(parseFloat(value) || "");
        if (!value) continue;
        setValue(el, value.slice(0, el.maxLength > 0 ? el.maxLength : 20000));
        mark(el, key);
      }
    }

    // 2. yes/no radio questions (only when you answered them in your profile)
    const groups = new Map();
    for (const r of document.querySelectorAll('input[type="radio"], [role="radio"]')) {
      if (!visible(r) && !(r.labels && [...r.labels].some(visible))) continue;
      const g = r.name || r.closest('[role="radiogroup"], fieldset')?.id || questionFor(r);
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push(r);
    }
    for (const radios of groups.values()) {
      if (radios.some((r) => r.checked || r.getAttribute("aria-checked") === "true")) continue;
      const q = questionFor(radios[0]);
      let want = customAnswer(p, q);
      if (want == null) {
        const hit = YESNO.find(([re]) => re.test(q));
        if (hit) want = yes(p[hit[1]]);
        else {
          const r = RULES.find(([k, re]) => ["gender", "ethnicity", "veteran", "disability", "hear"].includes(k) && re.test(q));
          if (r) want = r[2](p);
        }
      }
      if (!has(want)) continue;
      let best = null, bestScore = 0;
      for (const r of radios) {
        const label = (r.labels && r.labels[0] ? r.labels[0].textContent : "") || r.getAttribute("aria-label") || r.value || r.textContent;
        const s = score(label, want);
        if (s > bestScore) { best = r; bestScore = s; }
      }
      if (best && bestScore >= 60) {
        if (best.tagName === "INPUT") setChecked(best, true); else best.click();
        mark(best, "question");
      }
    }

    // 3. "I currently work here" checkboxes inside work experience
    let wi = -1;
    for (const c of document.querySelectorAll('input[type="checkbox"]')) {
      if (!visible(c) && !(c.labels && [...c.labels].some(visible))) continue;
      const d = describe(c) + questionFor(c) + " " + norm(c.labels?.[0]?.textContent);
      if (/ (currently work|current(ly)? (employed|job|role|position)|i work here|present) /.test(d)) {
        wi++;
        const item = (p.experience || [])[wi];
        if (item && item.current && !c.checked) { setChecked(c, true); mark(c, "work.current"); }
      }
    }

    // 4. résumé upload
    if (p.resume && p.resume.data) {
      for (const f of document.querySelectorAll('input[type="file"]')) {
        const d = describe(f) + questionFor(f) + norm(f.closest("div, section")?.textContent?.slice(0, 200));
        if (f.files && f.files.length) continue;
        if (!/ (resume|cv|curriculum) /.test(" " + d + " ") && document.querySelectorAll('input[type="file"]').length > 1) continue;
        try {
          const blob = await (await fetch(p.resume.data)).blob();
          const file = new File([blob], p.resume.name || "resume.pdf", { type: p.resume.type || blob.type || "application/pdf" });
          const dt = new DataTransfer();
          dt.items.add(file);
          f.files = dt.files;
          f.dispatchEvent(new Event("input", { bubbles: true }));
          f.dispatchEvent(new Event("change", { bubbles: true }));
          report.resume = true;
          mark(f, "resume");
        } catch { /* the page blocked it: user uploads manually */ }
        break;
      }
    }
    return report;
  }

  // Adds missing work-experience / education blocks (Workday "Add" buttons) before filling.
  async function addSections(profile) {
    collectHeadings();
    let added = 0;
    const plan = [["work", (profile.experience || []).length, /work experience|employment/], ["edu", (profile.education || []).length, /education/]];
    for (const [section, want, re] of plan) {
      if (!want) continue;
      const titles = () => [...document.querySelectorAll("input")].filter((el) => visible(el) && sectionOf(el) === section
        && / (title|school|university|institution) /.test(describe(el))).length;
      for (let i = titles(); i < Math.min(want, 6); i++) {
        const btn = [...document.querySelectorAll('button, [role="button"]')].find((b) => {
          if (!visible(b) || !/^add( another)?$/i.test((b.textContent || b.getAttribute("aria-label") || "").trim())) return false;
          const box = b.closest("[data-automation-id], section, fieldset, div");
          const label = norm((b.getAttribute("aria-label") || "") + " " + (box?.getAttribute("aria-labelledby") ? text(document.getElementById(box.getAttribute("aria-labelledby"))) : "") + " " + text(box?.querySelector("h2, h3, h4, legend")));
          return re.test(label) || sectionOf(b) === section;
        });
        if (!btn) break;
        btn.click();
        added++;
        await sleep(450);
        collectHeadings();
      }
    }
    return added;
  }

  globalThis.DreamJobFiller = { fill, addSections, describe, version: "2.0.0" };
})();
