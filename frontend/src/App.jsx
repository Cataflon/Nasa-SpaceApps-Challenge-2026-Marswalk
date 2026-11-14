<<<<<<< HEAD
﻿import { useState } from 'react';
import { useSite, useRoute, useLive, usePosition } from './hooks/useMission';
import MapView from './components/MapView';
import BudgetPanel from './components/BudgetPanel';
import DecisionPanel from './components/DecisionPanel';
import Planner from './components/Planner';
import Sensors from './components/Sensors';
import Navigator from './components/Navigator';
import { Chat, Information } from './components/Information';
import Icon from './components/Icon';
import { events, number } from './utils';
import WorkspaceNavigation from './components/WorkspaceNavigation';
import MissionMetrics from './components/MissionMetrics';
export default function App() {
  const siteResult = useSite(), planner = useRoute(), live = useLive(planner.result);
  const position = usePosition(live.tick, live.speed, live.state !== 'running' || !['live', 'mock'].includes(live.status));
  const [page, setPage] = useState('mission'), [planning, setPlanning] = useState(false), [selected, setSelected] = useState(null), [chat, setChat] = useState(false), [eventType, setEventType] = useState('local_storm');
  const site = siteResult.data, route = planner.result?.data, mock = siteResult.mock || planner.result?.mock;
  const offline = ['offline', 'reconnecting', 'invalid'].includes(live.status);
  if (!site) return <div className="loading-screen"><Icon name="compass" size={42}/><h1>Marswalk</h1><p>{siteResult.error ?? 'Se încarcă zona de explorare…'}</p></div>;
  return <div className="app"><WorkspaceNavigation page={page} onNavigate={setPage} mock={mock} offline={offline}/>
    {offline && <div className="connection-banner" role="status">Conexiunea live este întreruptă. Ultimele date sunt păstrate; poziția nu este extrapolată.</div>}
    <main className={page === 'mission' ? 'mission-main' : 'content-main'}>
      {page === 'mission' && <><div className="mission-heading"><div><span className="eyebrow">Jezero · Misiune de suprafață</span><h1>Un traseu. Mai multe posibilități.</h1></div><button className="button secondary" onClick={() => setPlanning(!planning)} disabled={live.state !== 'idle'}><Icon name="plus" size={17}/>{route ? 'Modifică planul' : 'Planifică ieșirea'}</button></div>
      <MissionMetrics live={live}/>
      <div className="mission-layout"><div className="map-column"><MapView key={site.site_id} site={site} route={route} live={live} position={position} mock={siteResult.mock} selected={selected} onSelect={setSelected}/><div className="map-caption"><span><i className="legend-route"/> Traseu activ</span><span><i className="legend-pnr"/> Limită de întoarcere</span><span className="caption-note">{mock ? 'Scenariu demonstrativ · fără validare operațională' : 'Coordonate în grila sitului'}</span></div></div>
      <aside className="mission-sidebar">{planning ? <Planner site={site} planner={planner} live={live} onClose={() => setPlanning(false)}/> : <><DecisionPanel live={live} route={route}/>{!route && <button className="button primary full" onClick={() => setPlanning(true)}>Alege opririle<Icon name="chevron" size={16}/></button>}<BudgetPanel route={route} tick={live.tick}/><section className="stops-section"><div className="section-title"><h3>Opriri științifice</h3><span className="small muted">{site.targets.length} disponibile</span></div>{site.targets.map((t, i) => <button className={`stop-row ${selected?.id === t.id ? 'selected' : ''}`} key={t.id} onClick={() => setSelected(selected?.id === t.id ? null : t)}><span className="stop-number">0{i + 1}</span><span><strong>{t.name.split(',')[0]}</strong><small>{t.name.split(',').slice(1).join(',').trim() || 'Țintă științifică'} · {t.dwell_min} min</small></span><Icon name="chevron" size={14}/></button>)}{selected && <div className="target-details"><h4>{selected.name}</h4>{selected.image ? <img src={selected.image} alt={`Imagine de la ${selected.name}`} onError={e => { e.target.hidden = true; }}/>: <p className="small muted">Imagine de la oprire indisponibilă.</p>}<p className="small">r {selected.row} / c {selected.col} · valoare științifică {selected.science_value}</p></div>}</section><button className="chat-toggle" onClick={() => setChat(!chat)} aria-expanded={chat}><Icon name="chat" size={18}/>Discută cu copilotul<Icon name="chevron" size={15}/></button>{chat && <Chat mock={mock} onRoute={planner.setResult} disabled={live.state !== 'idle'}/>}</> }</aside></div>
      {planner.result?.mock && <p className="mock-note">Plan demonstrativ fix: argilă, 215 min. Opțiunile selectate sunt trimise backendului când acesta este disponibil. Evenimentele demo reiau scena înregistrată.</p>}
      <section className="simulation-bar" aria-label="Controale simulare"><div className="simulation-actions"><button className="button primary" disabled={!route || route.verdict === 'NO-GO' || live.busy || offline} onClick={() => live.control(live.state === 'running' ? 'pause' : 'start')}><Icon name={live.state === 'running' ? 'pause' : 'play'} size={17}/>{live.state === 'running' ? 'Pauză' : live.state === 'paused' ? 'Continuă' : 'Pornește ieșirea'}</button><button className="icon-button" aria-label="Resetează simularea" disabled={!route || live.busy} onClick={() => live.control('reset')}><Icon name="reset"/></button><label className="speed-label">Viteză<select aria-label="Viteza simulării" value={live.speed} disabled={!route || live.busy} onChange={e => live.control('speed', Number(e.target.value))}>{[1, 5, 10, 30, 60].map(v => <option key={v} value={v}>{v}×</option>)}</select></label></div><div className="simulation-time"><span>Timp simulat</span><strong>t+{number(live.tick?.t_min ?? 0)}<small> min</small></strong></div><div className="event-controls"><label className="sr-only" htmlFor="event-select">Eveniment simulat</label><select id="event-select" value={eventType} onChange={e => setEventType(e.target.value)}>{Object.entries(events).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select><button className="button secondary" disabled={!route || live.state === 'idle' || live.busy || offline} onClick={() => live.event(eventType)}>Simulează</button></div></section>
      {live.error && <p className="error" role="alert">{live.error}</p>}
      <button className="text-button sensor-shortcut" onClick={() => setPage('sensors')}>Deschide monitorizarea senzorilor<Icon name="chevron" size={16}/></button></>}
      {page === 'sensors' && <Sensors live={live}/>} {page === 'navigation' && <Navigator site={site} route={route} live={live} position={position} mock={mock} selected={selected} onSelect={setSelected}/>} {page === 'information' && <Information/>}
    </main><footer className="app-footer"><span>Marswalk Copilot</span><span>Codul decide. Copilotul explică.</span><span>{site.cell_size_m} m / celulă</span></footer>
  </div>;
=======
import { useEffect, useState } from "react";
import { getSite, injectEvent, liveControl, planRoute, subscribeLive } from "./api/client.js";
import BudgetPanel from "./components/BudgetPanel.jsx";
import DecisionPanel from "./components/DecisionPanel.jsx";
import MapView from "./components/MapView.jsx";

const EVENTS = [
  ["dust_devil", "Dust devil"],
  ["local_storm", "Local storm"],
  ["regional_storm", "Regional storm"],
  ["solar_particle_event", "Solar storm"],
  ["suit_leak", "Suit leak"],
  ["fatigue", "Fatigue"],
];

export default function App() {
  const [site, setSite] = useState(null);
  const [mock, setMock] = useState(false);
  const [activeLayers, setActiveLayers] = useState(["elevation"]);
  const [route, setRoute] = useState(null);
  const [tick, setTick] = useState(null);
  const [decision, setDecision] = useState(null);
  const [explanation, setExplanation] = useState(null);
  const [live, setLive] = useState(false);

  useEffect(() => {
    getSite().then(({ data, mock }) => { setSite(data); setMock(mock); });
  }, []);

  useEffect(() => {
    if (!live) return;
    return subscribeLive((msg) => {
      if (msg.type === "tick") setTick(msg);
      else if (msg.type === "decision") setDecision(msg);
      else if (msg.type === "explanation") setExplanation(msg);
    });
  }, [live]);

  const plan = async () => {
    const target = site.targets[0];
    const { data } = await planRoute({ start: site.habitat, stops: [target.id], preset: "safe" });
    setRoute(data);
  };

  const toggleLive = () => {
    liveControl(live ? "pause" : "start", live ? {} : { speed: 10 });
    setLive((v) => !v);
  };

  const toggleLayer = (id) =>
    setActiveLayers((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));

  if (!site) return <p className="muted pad">Loading site…</p>;

  return (
    <div className="app">
      <header>
        <h1>Marswalk Copilot</h1>
        <span className="muted">{site.name}</span>
        {mock && <span className="badge">mock data</span>}
      </header>

      <main>
        <MapView site={site} activeLayers={activeLayers} route={route} tick={tick} decision={decision} />

        <aside>
          <section className="panel">
            <h2>Layers</h2>
            {site.layers.map((l) => (
              <label key={l.id} className="check">
                <input type="checkbox" checked={activeLayers.includes(l.id)} onChange={() => toggleLayer(l.id)} />
                {l.label}
              </label>
            ))}
          </section>

          <section className="panel">
            <h2>Simulation</h2>
            <div className="row">
              <button onClick={plan}>Plan route</button>
              <button onClick={toggleLive}>{live ? "Pause" : "Start EVA"}</button>
            </div>
            <div className="row wrap">
              {EVENTS.map(([id, label]) => (
                <button key={id} className="small" onClick={() => injectEvent(id)}>{label}</button>
              ))}
            </div>
          </section>

          <BudgetPanel route={route} tick={tick} />
          <DecisionPanel decision={decision} explanation={explanation} />
        </aside>
      </main>
    </div>
  );
>>>>>>> d264b9cf9d1367380612c950112af0ef601db712
}
