import { useEffect, useReducer, useRef, useState } from 'react';
import { controlLive, getSite, injectEvent, planRoute, subscribeLive } from '../api/client';
export function useSite() {
  const [result, setResult] = useState({ data: null, mock: false, error: '' });
  useEffect(() => { let active = true; getSite().then(r => active && setResult(r)).catch(e => active && setResult({ data: null, error: e.message })); return () => { active = false; }; }, []);
  return result;
}
export function useRoute() {
  const [result, setResult] = useState(null), [loading, setLoading] = useState(false), [error, setError] = useState('');
  async function plan(data) { setLoading(true); setError(''); try { const r = await planRoute(data); setResult(r); return r; } catch (e) { setError(e.message); } finally { setLoading(false); } }
  return { result, loading, error, plan, setResult };
}
const initial = { tick: null, decision: null, explanations: {}, history: [], events: [], samples: [], trail: [], receivedAt: null };
function reducer(state, msg) {
  if (msg.type === 'reset') return initial;
  if (msg.type === 'scene') return { ...state, trail: [], tick: null };
  if (msg.type === 'tick') {
    if (!Number.isFinite(msg.astronaut?.row) || !Number.isFinite(msg.astronaut?.col)) return state;
    if (state.tick && msg.t_min < state.tick.t_min) return state;
    const repeated = state.tick?.t_min === msg.t_min;
    return { ...state, tick: msg, receivedAt: Date.now(), trail: [...state.trail.slice(-599), [msg.astronaut.row, msg.astronaut.col]], samples: repeated ? state.samples : [...state.samples.slice(-119), { t: msg.t_min, ...msg.sensors }] };
  }
  if (msg.type === 'decision' && msg.decision_id) return { ...state, history: [msg, ...state.history.filter(d => d.decision_id !== msg.decision_id)].slice(0, 30), decision: !state.decision || msg.t_min >= state.decision.t_min ? msg : state.decision };
  if (msg.type === 'explanation' && msg.decision_id) return { ...state, explanations: Object.fromEntries([...Object.entries(state.explanations).slice(-49), [msg.decision_id, msg]]) };
  if (msg.type === 'event') return { ...state, events: [msg, ...state.events].slice(0, 20) };
  return state;
}
export function useLive(route) {
  const [data, dispatch] = useReducer(reducer, initial);
  const [status, setStatus] = useState('idle'), [state, setState] = useState('idle'), [speed, setSpeed] = useState(10), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const routeId = route?.data?.route_id, mock = !!route?.mock;
  useEffect(() => {
    dispatch({ type: 'reset' }); setState('idle'); setError('');
    if (!routeId) return;
    return subscribeLive(msg => { if (msg.type === 'control') setState(msg.state); else dispatch(msg); }, setStatus, mock);
  }, [routeId, mock]);
  async function control(action, nextSpeed = speed) {
    if (!routeId || busy) return;
    setBusy(true); setError('');
    try {
      const r = await controlLive({ action, speed: nextSpeed, route_id: routeId }, mock);
      if (!r.data?.ok) throw new Error('Comanda nu a fost confirmată.');
      if (action === 'reset') dispatch({ type: 'reset' });
      setState(r.data.state); setSpeed(nextSpeed);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function event(type) { setBusy(true); setError(''); try { await injectEvent(type, mock); } catch (e) { setError(e.message); } finally { setBusy(false); } }
  return { ...data, status, state, speed, busy, error, control, event, mock };
}
export function usePosition(tick, speed, paused) {
  const [position, setPosition] = useState(null); const previous = useRef(null);
  useEffect(() => {
    if (!tick?.astronaut) { previous.current = null; setPosition(null); return; }
    const target = tick.astronaut, last = previous.current; previous.current = tick;
    if (!last || paused || window.matchMedia('(prefers-reduced-motion: reduce)').matches || tick.t_min <= last.t_min) { setPosition(target); return; }
    // Interpolare doar pentru mișcări mici; salturile scenariului se afișează direct.
    if (Math.hypot(target.row - last.astronaut.row, target.col - last.astronaut.col) > 15) { setPosition(target); return; }
    const points = last.remaining_path ?? [];
    const end = points.findIndex(p => Math.hypot(p[0] - target.row, p[1] - target.col) < 0.01);
    const path = end >= 0 ? [[last.astronaut.row, last.astronaut.col], ...points.slice(0, end + 1)] : [[last.astronaut.row, last.astronaut.col], [target.row, target.col]];
    const lengths = path.slice(1).map((p, i) => Math.hypot(p[0] - path[i][0], p[1] - path[i][1])), total = lengths.reduce((a, b) => a + b, 0);
    let frame; const start = performance.now(), duration = Math.min(1000 / speed, 1000);
    function animate(now) { let distance = Math.min(1, (now - start) / duration) * total, i = 0; while (i < lengths.length - 1 && distance > lengths[i]) distance -= lengths[i++]; const f = lengths[i] ? distance / lengths[i] : 1, a = path[i], b = path[i + 1]; setPosition({ row: a[0] + (b[0] - a[0]) * f, col: a[1] + (b[1] - a[1]) * f }); if (now - start < duration) frame = requestAnimationFrame(animate); }
    frame = requestAnimationFrame(animate); return () => cancelAnimationFrame(frame);
  }, [tick, speed, paused]);
  return position;
}
