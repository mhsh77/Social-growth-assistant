// Isolated content script: relays captures from hook.js to the background worker.
window.addEventListener("message", (event) => {
  if (event.source !== window || !event.data || event.data.__sga !== true) return;
  const { operation, pageUrl, payload } = event.data;
  chrome.runtime.sendMessage({ type: "sga-capture", operation, pageUrl, payload });
});
