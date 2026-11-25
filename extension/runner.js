/* Loads the saved profile, fills the current page and shows a short notice. */
(() => {
  "use strict";
  if (globalThis.DreamJobRun) return;

  function toast(message, kind = "ok") {
    const old = document.getElementById("dreamjob-toast");
    if (old) old.remove();
    const host = document.createElement("div");
    host.id = "dreamjob-toast";
    const root = host.attachShadow({ mode: "open" });
    const color = kind === "warn" ? "#B45309" : kind === "ok" ? "#15803D" : "#374151";
    root.innerHTML = `<style>
      .t{position:fixed;right:20px;bottom:84px;z-index:2147483647;max-width:340px;background:#111827;color:#fff;
         font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;padding:12px 14px 12px 12px;
         border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.25);display:flex;gap:10px;align-items:flex-start}
      .d{width:8px;height:8px;border-radius:50%;margin-top:6px;flex:none;background:${color}}
      button{background:none;border:0;color:#9CA3AF;font-size:18px;line-height:1;cursor:pointer;padding:0 0 0 4px}
    </style><div class="t" role="status"><span class="d"></span><span></span><button aria-label="Close">×</button></div>`;
    root.querySelector("span:nth-child(2)").textContent = message;
    root.querySelector("button").addEventListener("click", () => host.remove());
    document.documentElement.appendChild(host);
    setTimeout(() => host.remove(), 7000);
  }

  globalThis.DreamJobRun = async (opts = {}) => {
    const { profile, settings } = await chrome.storage.local.get(["profile", "settings"]);
    const top = window === window.top;
    if (!profile || !(profile.first_name || profile.email)) {
      if (top) toast("Set up your profile first: click the DreamJob icon and choose “Edit profile”.", "warn");
      return { filled: 0, noProfile: true };
    }
    let added = 0;
    if (!settings || settings.addSections !== false) added = await globalThis.DreamJobFiller.addSections(profile);
    const r = await globalThis.DreamJobFiller.fill(profile, { overwrite: !!opts.overwrite });
    r.added = added;
    if (r.filled || top) {
      toast(r.filled
        ? `Filled ${r.filled} field${r.filled === 1 ? "" : "s"}${r.resume ? " and attached your résumé" : ""}. Check them before you continue.`
        : "Nothing new to fill here. Fields that already have a value are left as they are.", r.filled ? "ok" : "info");
    }
    return r;
  };
})();
