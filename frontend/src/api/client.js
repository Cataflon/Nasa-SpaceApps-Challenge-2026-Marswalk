import mockLive from '@contracts/live_messages.json';
import mockRoute from '@contracts/route_response.json';
import mockSite from '@contracts/site.json';
import mockChat from '@contracts/chat_stream.json';
const clone = value => structuredClone(value);
export async function loadTerrain() {
  const [grid, model] = await Promise.all([fetch('/terrain/jezero.json'), fetch('/terrain/jezero.glb')]);
  if (!grid.ok || !model.ok) throw new Error('Modelul Jezero nu este disponibil. Folosește vederea 2D.');
  return { grid: await grid.json(), model: await model.arrayBuffer() };
}
async function request(url, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 6000);
  try {
    const response = await fetch(url, { ...options, signal: options.signal ?? controller.signal });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const error = new Error(typeof body?.detail === 'string' ? body.detail : `Cererea nu a reușit (${response.status}).`);
      error.status = response.status; throw error;
    }
    return { data: await response.json(), mock: response.headers.get('X-Mock') === '1' };
  } finally { clearTimeout(timeout); }
}
const post = (url, data) => request(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
async function fallback(call, value) {
  try { return await call(); } catch (error) {
    if (error.status && error.status < 500) throw error;
    return { data: clone(value), mock: true };
  }
}
export const getSite = () => fallback(() => request('/api/site'), mockSite);
export const planRoute = data => fallback(() => post('/api/route', data), mockRoute);
export const getPoint = (row, col, signal) => request(`/api/point?row=${row}&col=${col}`, { signal }).then(r => r.data).catch(() => null);
// Player demonstrativ: valori înregistrate, fără calcule de siguranță în frontend.
const listeners = new Set();
let demo = { state: 'idle', speed: 10, t: 0, path: clone(mockRoute.path), cursor: 0, storm: false, decision: null };
let interval, explanationTimer;
const emit = message => listeners.forEach(fn => fn(clone(message)));
function tick() {
  const base = clone(mockLive[0]);
  const index = Math.min(Math.floor(demo.cursor), demo.path.length - 1);
  const a = demo.path[index], b = demo.path[Math.min(index + 1, demo.path.length - 1)], f = demo.cursor - index;
  const position = [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
  base.t_min = demo.t; base.astronaut = { row: position[0], col: position[1], speed_ms: 0.9 };
  base.remaining_path = [position, ...demo.path.slice(index + 1)];
  base.hazards = demo.storm ? base.hazards.map(h => ({ ...h, forecast: h.forecast.map((f, i) => ({ ...f, t_min: demo.t + (i + 1) * 10 })) })) : [];
  if (demo.decision) base.budget.o2_end_pct = demo.decision.alternatives.find(a => a.id === demo.decision.alternative_id)?.o2_end_pct;
  emit(base);
}
function runDemo() {
  clearInterval(interval);
  if (demo.state !== 'running') return;
  interval = setInterval(() => {
    demo.t += 1; demo.cursor = Math.min(demo.path.length - 1, demo.cursor + 0.06);
    if (demo.t === 72 && !demo.decision) demoEvent('local_storm');
    tick();
    if (demo.cursor >= demo.path.length - 1) { demo.state = 'paused'; clearInterval(interval); emit({ type: 'control', state: 'paused' }); }
  }, 1000 / demo.speed);
}
function demoEvent(event) {
  emit({ type: 'event', event, t_min: demo.t, severity: 'high' });
  if (!['local_storm', 'regional_storm'].includes(event)) return;
  clearTimeout(explanationTimer);
  const decision = clone(mockLive[1]); decision.t_min = demo.t; decision.decision_id = `demo_${demo.t}_${event}`; demo.storm = true;
  if (event === 'regional_storm') { decision.decision = 'RETURN'; decision.alternative_id = 'return'; }
  // Reia scena înregistrată la poziția originală, fără a inventa o rută validată.
  demo.path = clone(decision.alternatives.find(a => a.id === decision.alternative_id).path); demo.cursor = 0; demo.decision = decision;
  emit({ type: 'scene' }); tick(); emit(decision);
  explanationTimer = setTimeout(() => emit({ type: 'explanation', decision_id: decision.decision_id, t_min: decision.t_min, source: 'template', text: event === 'local_storm' ? mockLive[2].text : 'Scenariu demonstrativ: întoarcere la habitat pe alternativa RETURN din contract.' }), 2200);
}
export async function controlLive(data, mock = false) {
  if (!mock) return post('/api/live/control', data);
  if (data.action === 'reset') {
    clearInterval(interval); clearTimeout(explanationTimer);
    demo = { state: 'idle', speed: demo.speed, t: 0, path: clone(mockRoute.path), cursor: 0, storm: false, decision: null };
  } else if (data.action === 'start') demo.state = 'running';
  else if (data.action === 'pause') demo.state = 'paused';
  if (data.speed) demo.speed = data.speed;
  runDemo(); tick(); return { data: { ok: true, state: demo.state, t_min: demo.t }, mock: true };
}
export async function injectEvent(event, mock = false) {
  if (!mock) return post('/api/live/event', { event, params: {} });
  demoEvent(event); return { data: { ok: true }, mock: true };
}
export function subscribeLive(onMessage, onStatus, mock = false) {
  if (mock) {
    listeners.add(onMessage); onStatus('mock'); tick();
    return () => { listeners.delete(onMessage); if (!listeners.size) { clearInterval(interval); clearTimeout(explanationTimer); demo.state = 'idle'; } };
  }
  let socket, retry, stopped = false, attempts = 0;
  function connect() {
    onStatus(attempts ? 'reconnecting' : 'connecting');
    socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/live`);
    socket.onopen = () => { attempts = 0; onStatus('live'); };
    socket.onmessage = e => { try { const msg = JSON.parse(e.data); if (['tick', 'decision', 'explanation', 'event'].includes(msg.type)) onMessage(msg); } catch { onStatus('invalid'); } };
    socket.onclose = () => { if (!stopped) { onStatus('offline'); retry = setTimeout(connect, Math.min(1000 * 2 ** attempts++, 15000)); } };
    socket.onerror = () => socket.close();
  }
  connect(); return () => { stopped = true; clearTimeout(retry); socket?.close(); };
}
export async function streamChat(message, history, onMessage, signal, mock) {
  if (mock) {
    for (const line of mockChat.lines) {
      if (signal.aborted) return;
      await new Promise(resolve => setTimeout(resolve, 220));
      if (signal.aborted) return;
      onMessage(line.type === 'route' ? { ...line, route: clone(mockRoute) } : line);
    }
    return;
  }
  const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message, history }), signal });
  if (!response.ok || !response.body) throw new Error('Chatul nu este disponibil. Încearcă din nou.');
  const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = '';
  try {
    while (true) {
      const { value, done } = await reader.read(); buffer += decoder.decode(value, { stream: !done });
      const lines = buffer.split('\n'); buffer = lines.pop();
      for (const line of lines) if (line.trim()) onMessage(JSON.parse(line));
      if (done) { if (buffer.trim()) onMessage(JSON.parse(buffer)); break; }
    }
  } finally { reader.releaseLock(); }
}
