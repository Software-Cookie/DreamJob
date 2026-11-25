(async () => {
  const $ = (id) => document.getElementById(id);
  const { profile } = await chrome.storage.local.get("profile");
  const name = profile && [profile.first_name, profile.last_name].filter(Boolean).join(" ");
  $("who").textContent = name ? `Profile: ${name}${profile.email ? " · " + profile.email : ""}` : "No profile yet. Add your details once, then fill any form in one click.";
  if (!name) { $("fill").textContent = "Set up my profile"; }

  try {
    const cmds = await chrome.commands.getAll();
    const c = cmds.find((x) => x.name === "fill-form");
    $("shortcut").textContent = c && c.shortcut ? `Shortcut: ${c.shortcut}` : "Set a shortcut in chrome://extensions/shortcuts";
  } catch { /* not supported */ }

  $("edit").addEventListener("click", () => chrome.runtime.openOptionsPage());
  $("fill").addEventListener("click", async () => {
    if (!name) return chrome.runtime.openOptionsPage();
    const btn = $("fill");
    btn.disabled = true;
    btn.textContent = "Filling…";
    const res = $("result");
    res.hidden = false;
    res.className = "result";
    try {
      const r = await chrome.runtime.sendMessage({ type: "fill-active-tab", opts: { overwrite: $("overwrite").checked } });
      if (r && r.error) throw new Error(r.error);
      if (r.filled) {
        res.textContent = `Filled ${r.filled} field${r.filled === 1 ? "" : "s"}${r.resume ? " and attached your résumé" : ""}. Check them, then continue.`;
        res.classList.add("ok");
      } else {
        res.textContent = "Nothing new to fill on this page. Fields that already have a value are left as they are.";
      }
    } catch (e) {
      res.textContent = /Cannot access|chrome:\/\/|extensions gallery/i.test(String(e.message))
        ? "Chrome does not allow extensions on this page. Open the job application form and try again."
        : e.message || "Could not fill this page.";
      res.classList.add("warn");
    } finally {
      btn.disabled = false;
      btn.textContent = "Fill this page";
    }
  });
})();
