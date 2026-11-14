import { useEffect, useState } from 'react';
import { useSite, useRoute, useLive, usePosition } from './hooks/useMission';
import MapView from './components/MapView';
import Sensors from './components/Sensors';
import Navigator from './components/Navigator';
import { Information } from './components/Information';
import Icon from './components/Icon';
import { events, number } from './utils';
import WorkspaceNavigation from './components/WorkspaceNavigation';
import MissionMetrics from './components/MissionMetrics';
import MissionSheet from './components/MissionSheet';

export default function App() {
  const siteResult = useSite(), planner = useRoute(), live = useLive(planner.result);
  const position = usePosition(live.tick, live.speed, live.state !== 'running' || !['live', 'mock'].includes(live.status));
  const [page, setPage] = useState('mission'), [planning, setPlanning] = useState(false);
  const [selected, setSelected] = useState(null), [chat, setChat] = useState(false);
  const [eventType, setEventType] = useState('local_storm'), [navigationRoute, setNavigationRoute] = useState(null);
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'instant' }); }, [page]);
  const site = siteResult.data, route = planner.result?.data, mock = siteResult.mock || planner.result?.mock;
  const offline = ['offline', 'reconnecting', 'invalid'].includes(live.status);
  if (!site) return <div className="loading-screen"><img className="loading-brand-logo" src="/images/marswalk_logo_transparent.png" alt="Marswalk"/><p>{siteResult.error ?? 'Loading expedition area...'}</p></div>;
  return <div className={`app expedition-shell view-${page}`}>
    <WorkspaceNavigation page={page} onNavigate={setPage} mock={mock} offline={offline} site={site}/>
    {offline && <div className="connection-banner" role="status">Live link interrupted. Last received data retained; position is held.</div>}
    <main className={page === 'mission' ? 'mission-main' : 'content-main'}>
      {page === 'mission' && <>
        <div className="mission-layout field-workbench">
          <div className="map-column">
            <MapView key={site.site_id} site={site} route={route} live={live} position={position} mock={siteResult.mock} selected={selected} onSelect={setSelected} onRoutePreview={setNavigationRoute}/>
            <MissionMetrics live={live}/>
            <section className="simulation-bar" aria-label="Simulation controls">
              <div className="simulation-actions">
                <button className="button primary" disabled={!route || route.verdict === 'NO-GO' || live.busy || offline} onClick={() => live.control(live.state === 'running' ? 'pause' : 'start')}><Icon name={live.state === 'running' ? 'pause' : 'play'} size={15}/>{live.state === 'running' ? 'Pause EVA' : live.state === 'paused' ? 'Resume EVA' : 'Start EVA'}</button>
                <button className="icon-button" aria-label="Reset simulation" disabled={!route || live.busy} onClick={() => live.control('reset')}><Icon name="reset" size={16}/></button>
                <label className="speed-label">RATE<select aria-label="Simulation speed" value={live.speed} disabled={!route || live.busy} onChange={e => live.control('speed', Number(e.target.value))}>{[1, 5, 10, 30, 60].map(v => <option key={v} value={v}>{v}×</option>)}</select></label>
              </div>
              <div className="simulation-time"><span>ELAPSED</span><strong>t+{number(live.tick?.t_min ?? 0)}<small> min</small></strong></div>
              <div className="event-controls"><label className="sr-only" htmlFor="event-select">Simulated event</label><select id="event-select" value={eventType} onChange={e => setEventType(e.target.value)}>{Object.entries(events).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select><button className="button secondary" disabled={!route || live.state === 'idle' || live.busy || offline} onClick={() => live.event(eventType)}>Inject</button></div>
            </section>
          </div>
          <MissionSheet site={site} route={route} live={live} planner={planner} planning={planning} setPlanning={setPlanning} selected={selected} onSelect={setSelected} chat={chat} setChat={setChat} mock={mock}/>
        </div>
        {planner.result?.mock && <p className="mock-note">Recorded demo plan / clay site / 215 min. Backend planning uses the submitted selections when available.</p>}
        {live.error && <p className="error" role="alert">{live.error}</p>}
      </>}
      {page === 'sensors' && <Sensors live={live}/>}
      {page === 'navigation' && <Navigator navigationRoute={navigationRoute} site={site} route={route} live={live} position={position} mock={mock} selected={selected} onSelect={setSelected}/>}
      {page === 'information' && <Information/>}
    </main>
    <footer className="app-footer"><span>Marswalk Copilot</span><span>{mock ? 'DEMONSTRATION DATA' : 'MISSION SERVICE'} <b>·</b> {site.cell_size_m} m planning grid</span><span>Jezero surface exploration</span></footer>
  </div>;
}
