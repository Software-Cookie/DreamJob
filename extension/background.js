/* Keyboard shortcut (Alt+Shift+F by default) fills the current tab. */
async function fillTab(tab, opts = {}) {
  if (!tab || !/^https?:/.test(tab.url || "")) return { error: "Open a job application page first." };
  const target = { tabId: tab.id, allFrames: true };
  try {
    await chrome.scripting.executeScript({ target, files: ["filler.js", "runner.js"] });
  } catch {
    target.allFrames = false; // some frames may be off limits; the main page still works
    await chrome.scripting.executeScript({ target, files: ["filler.js", "runner.js"] });
  }
  const results = await chrome.scripting.executeScript({ target, func: (o) => globalThis.DreamJobRun(o), args: [opts] });
  const sum = { filled: 0, resume: false, noProfile: false };
  for (const r of results) {
    if (!r.result) continue;
    sum.filled += r.result.filled || 0;
    sum.resume = sum.resume || !!r.result.resume;
    sum.noProfile = sum.noProfile || !!r.result.noProfile;
  }
  return sum;
}

chrome.commands.onCommand.addListener(async (command) => {
  if (command !== "fill-form") return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  try { await fillTab(tab); } catch (e) { console.warn("DreamJob fill failed", e); }
});

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg && msg.type === "fill-active-tab") {
    chrome.tabs.query({ active: true, currentWindow: true })
      .then(([tab]) => fillTab(tab, msg.opts || {}))
      .then(reply, (e) => reply({ error: String(e && e.message || e) }));
    return true;
  }
  return false;
});

chrome.runtime.onInstalled.addListener((d) => {
  if (d.reason === "install") chrome.runtime.openOptionsPage();
});
