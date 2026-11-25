// Shows this site's address on the autofill page (inline scripts are blocked by the security policy).
document.querySelectorAll("#origin").forEach((el) => { el.textContent = location.origin; });
