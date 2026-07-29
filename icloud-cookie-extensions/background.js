const LOCAL_HOSTS = new Set(["127.0.0.1", "localhost"]);

async function readICloudCookies(host) {
  const suffix = host === "icloud.com.cn" ? "icloud.com.cn" : "icloud.com";
  const urls = [
    `https://${suffix}/`,
    `https://www.${suffix}/`,
    `https://setup.${suffix}/`,
  ];
  const batches = await Promise.all(urls.map((url) => chrome.cookies.getAll({ url })));
  const cookies = {};
  for (const batch of batches) {
    for (const cookie of batch) cookies[cookie.name] = cookie.value;
  }
  if (!Object.keys(cookies).length) {
    throw new Error(`Chrome 中未找到 ${suffix} Cookie，请先登录 iCloud`);
  }
  return cookies;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type !== "ICLOUD_HME_UPDATE_COOKIES") return;

  (async () => {
    const senderUrl = new URL(sender.url || sender.tab?.url || "http://invalid/");
    const apiUrl = new URL(message.apiBase);
    if (
      senderUrl.protocol !== "http:" ||
      apiUrl.protocol !== "http:" ||
      !LOCAL_HOSTS.has(senderUrl.hostname) ||
      !LOCAL_HOSTS.has(apiUrl.hostname)
    ) throw new Error("仅接受本机 iCloud HME 页面请求");

    const cookies = await readICloudCookies(message.host);
    const response = await fetch(
      `${apiUrl.origin}/api/accounts/${encodeURIComponent(message.accountId)}/cookies`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cookie_input: JSON.stringify(cookies) }),
      },
    );
    const result = await response.json();
    sendResponse(result);
  })().catch((error) => sendResponse({ ok: false, error: error.message }));

  return true;
});
