// Runs inside the X page. Watches the timeline responses the page itself requests
// and hands a copy to bridge.js. It never makes its own requests to X.
(() => {
  const OPERATIONS = /\/i\/api\/graphql\/[^/]+\/(SearchTimeline|ListLatestTweetsTimeline)\b/;

  // Only forward from the page types we collect from; ignore home timeline, DMs, etc.
  const onCollectedPage = () =>
    location.pathname === "/search" || location.pathname.startsWith("/i/lists/");

  const forward = (url, payload) => {
    const match = OPERATIONS.exec(url);
    if (!match || !onCollectedPage() || !payload) return;
    window.postMessage(
      { __sga: true, operation: match[1], pageUrl: location.href, payload },
      location.origin
    );
  };

  const originalFetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await originalFetch.apply(this, args);
    try {
      const url = typeof args[0] === "string" ? args[0] : (args[0] && args[0].url) || "";
      if (OPERATIONS.test(url)) {
        response.clone().json().then((data) => forward(url, data)).catch(() => {});
      }
    } catch (_) {}
    return response;
  };

  const originalOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__sgaUrl = String(url);
    return originalOpen.call(this, method, url, ...rest);
  };
  const originalSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function (...args) {
    if (this.__sgaUrl && OPERATIONS.test(this.__sgaUrl)) {
      this.addEventListener("load", () => {
        try {
          if (this.responseType === "json") forward(this.__sgaUrl, this.response);
          else if (this.responseType === "" || this.responseType === "text")
            forward(this.__sgaUrl, JSON.parse(this.responseText));
        } catch (_) {}
      });
    }
    return originalSend.apply(this, args);
  };
})();
