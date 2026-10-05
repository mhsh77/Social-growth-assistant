// Sends captures to the local assistant. The only network destination is 127.0.0.1.
const ENDPOINT = "http://127.0.0.1:8765/ingest";

chrome.runtime.onMessage.addListener((message) => {
  if (!message || message.type !== "sga-capture") return;
  fetch(ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      operation: message.operation,
      pageUrl: message.pageUrl,
      payload: message.payload,
    }),
  })
    .then((response) => response.json())
    .then((result) => {
      chrome.action.setBadgeBackgroundColor({ color: "#1d9bf0" });
      chrome.action.setBadgeText({ text: String(result.total ?? "") });
    })
    .catch(() => {
      // The assistant isn't running (`sga collect`), so nothing is captured.
      chrome.action.setBadgeBackgroundColor({ color: "#888888" });
      chrome.action.setBadgeText({ text: "off" });
    });
});
