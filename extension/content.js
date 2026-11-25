/* On supported job sites: a small "Fill with DreamJob" button in the corner. */
(() => {
  "use strict";
  if (globalThis.__dreamjobButton) return;
  globalThis.__dreamjobButton = true;

  const host = location.hostname;

  function countInputs() {
    return [...document.querySelectorAll("input:not([type=hidden]), textarea, select")].filter((el) => el.offsetWidth || el.offsetHeight).length;
  }

  async function mount() {
    const { settings } = await chrome.storage.local.get("settings");
    if (settings && (settings.hideButton === true || (settings.hiddenOn || []).includes(host))) return;
    if (document.getElementById("dreamjob-fill")) return;
    const el = document.createElement("div");
    el.id = "dreamjob-fill";
    const root = el.attachShadow({ mode: "open" });
    root.innerHTML = `<style>
      .w{position:fixed;right:20px;bottom:20px;z-index:2147483646;display:flex;align-items:center;gap:2px;background:#111827;
         border-radius:999px;box-shadow:0 6px 20px rgba(0,0,0,.22);font:600 14px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
      .f{background:none;border:0;color:#fff;padding:11px 8px 11px 16px;cursor:pointer;display:flex;align-items:center;gap:8px;font:inherit}
      .f:disabled{opacity:.6;cursor:progress}
      .f svg{width:16px;height:16px}
      .x{background:none;border:0;color:#9CA3AF;padding:8px 12px 8px 6px;cursor:pointer;font-size:16px;line-height:1}
      .f:focus-visible,.x:focus-visible{outline:2px solid #22C55E;outline-offset:2px;border-radius:999px}
    </style>
    <div class="w"><button class="f" title="Fill this form from your DreamJob profile (Alt+Shift+F)">
      <svg viewBox="0 0 24 24" fill="none" stroke="#22C55E" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5l5 5L20 6"/></svg>
      Fill with DreamJob</button><button class="x" aria-label="Hide on this site" title="Hide on this site">×</button></div>`;
    const fillBtn = root.querySelector(".f");
    fillBtn.addEventListener("click", async () => {
      fillBtn.disabled = true;
      try { await globalThis.DreamJobRun(); } finally { fillBtn.disabled = false; }
    });
    root.querySelector(".x").addEventListener("click", async () => {
      const { settings: s = {} } = await chrome.storage.local.get("settings");
      s.hiddenOn = [...new Set([...(s.hiddenOn || []), host])];
      await chrome.storage.local.set({ settings: s });
      el.remove();
    });
    document.documentElement.appendChild(el);
  }

  // Show the button once the page has a real form (Workday builds its pages after load).
  let tries = 0;
  const timer = setInterval(() => {
    tries++;
    if (countInputs() >= 2 || (window === window.top && tries > 6)) { clearInterval(timer); if (countInputs() >= 2) mount(); }
    if (tries > 40) clearInterval(timer);
  }, 750);

  // Workday is a single-page app: when it shows a new step, make sure the button is still there.
  if (window === window.top) {
    new MutationObserver(() => {
      if (!document.getElementById("dreamjob-fill") && countInputs() >= 2) mount();
    }).observe(document.documentElement, { childList: true, subtree: true });
  }
})();
