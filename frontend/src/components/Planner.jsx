import { useState } from 'react';
import Icon from './Icon';
import { number } from '../utils';
export default function Planner({ site, planner, live, onClose }) {
  const [stops, setStops] = useState([site.targets[0]?.id].filter(Boolean)), [preset, setPreset] = useState('safe'), [duration, setDuration] = useState(300);
  async function submit(e) { e.preventDefault(); const result = await planner.plan({ start: site.habitat, stops, return_to_habitat: true, preset, start_time_min: 0, max_duration_min: Number(duration) }); if (result) onClose(); }
  return <section className="planner"><div className="section-title"><h3>Planifică ieșirea</h3><button className="icon-button" onClick={onClose} aria-label="Închide planificarea"><Icon name="close" size={16}/></button></div><form onSubmit={submit}>
    <fieldset><legend>Opriri științifice</legend>{site.targets.map((t, i) => <label className="stop-choice" key={t.id}><input type="checkbox" checked={stops.includes(t.id)} onChange={e => setStops(e.target.checked ? [...stops, t.id] : stops.filter(id => id !== t.id))}/><span><strong>{t.name}</strong><small>{number(t.dwell_min)} min la oprire · valoare {t.science_value}</small></span><span className="muted">0{i + 1}</span></label>)}</fieldset>
    <label className="field-label">Prioritate<select value={preset} onChange={e => setPreset(e.target.value)}><option value="safe">Siguranță</option><option value="fast">Timp minim</option><option value="science">Valoare științifică</option></select></label>
    <label className="field-label">Durată maximă (minute)<input required type="number" min="30" max="1440" step="1" value={duration} onChange={e => setDuration(e.target.value)}/></label>
    {planner.error && <p className="error" role="alert">{planner.error}</p>}<button className="button primary full" disabled={!stops.length || planner.loading || live.state !== 'idle'}>{planner.loading ? 'Se calculează…' : 'Generează traseul'}<Icon name="chevron" size={16}/></button>
    <p className="small muted">Întoarcerea la habitat este inclusă. În modul mock se afișează planul fix de exemplu pentru argilă.</p>
  </form></section>;
}
