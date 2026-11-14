// Clientul API. Dacă backendul nu răspunde, cade pe mock-urile din shared/contracts,
// ca frontendul să poată lucra singur din prima oră.
import mockLive from "@contracts/live_messages.json";
import mockRoute from "@contracts/route_response.json";
import mockSite from "@contracts/site.json";

async function getJson(url, fallback, options) {
  try {
    const res = await fetch(url, options);
    if (!res.ok) throw new Error(res.status);
    return { data: await res.json(), mock: res.headers.get("X-Mock") === "1" };
  } catch {
    return { data: fallback, mock: true };
  }
}

export const getSite = () => getJson("/api/site", mockSite);

export const planRoute = (request) =>
  getJson("/api/route", mockRoute, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

export const injectEvent = (event, params = {}) =>
  fetch("/api/live/event", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event, params }),
  }).catch(() => null);

// Start / pauză / reset / viteză pentru motorul live (vezi shared/contracts/live_control.json).
export const liveControl = (action, extra = {}) =>
  fetch("/api/live/control", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, ...extra }),
  }).catch(() => null);

// Abonare la fluxul live. Întoarce o funcție de dezabonare.
export function subscribeLive(onMessage) {
  let closed = false;
  let timer = null;
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/live`);

  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  ws.onerror = () => {
    // Fără backend: redăm mock-ul în buclă.
    let i = 0;
    timer = setInterval(() => !closed && onMessage(mockLive[i++ % mockLive.length]), 1000);
  };

  return () => {
    closed = true;
    clearInterval(timer);
    ws.close();
  };
}
