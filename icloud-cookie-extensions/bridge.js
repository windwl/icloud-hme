window.addEventListener("message", (event) => {
  const message = event.data || {};
  if (
    event.source !== window ||
    event.origin !== window.location.origin ||
    message.type !== "ICLOUD_HME_EXTENSION_UPDATE"
  ) return;

  window.postMessage({
    type: "ICLOUD_HME_EXTENSION_ACK",
    requestId: message.requestId,
  }, window.location.origin);

  chrome.runtime.sendMessage({
    type: "ICLOUD_HME_UPDATE_COOKIES",
    accountId: message.accountId,
    host: message.host,
    apiBase: message.apiBase,
  }, (result) => {
    const error = chrome.runtime.lastError && chrome.runtime.lastError.message;
    window.postMessage({
      type: "ICLOUD_HME_EXTENSION_RESPONSE",
      requestId: message.requestId,
      result: error ? { ok: false, error } : result,
    }, window.location.origin);
  });
});
