import {useMemo} from 'react';
import MapView from './MapView';
import FieldTracker from './FieldTracker';
import EVAWatch from './EVAWatch';
import DecisionPanel from './DecisionPanel';
import {Chat} from './Information';
import SensorSummary from './SensorSummary';
import SimulationControls from './SimulationControls';
import MissionMetrics from './MissionMetrics';
import Icon from './Icon';
import {number} from '../utils';
const previewLive={state:'idle',tick:null,decision:null,trail:[],history:[],explanations:{}};
export default function SimulationWorkspace({equipment,site,mapSite,route,live,offline,transport,selected,onSelect,onSensors,onPlanning,mock,onCopilotRoute}){
  const displayedLive=transport.isLive?live:previewLive;
  const displayedRoute=useMemo(()=>transport.path?{...route,path:transport.path}:route,[route,transport.path]);
  return <div className="simulation-workspace"><div className="workflow-page-heading"><div><span className="eyebrow">Astronaut operations</span><h1>Simulate. Track. Respond.</h1><p>One shared position for the terrain, first-person tracker and habitat compass.</p></div><button className="button secondary" onClick={onPlanning}><Icon name="map" size={15}/>Edit mission plan</button></div>
    {transport.localTrip&&<div className="workflow-info">Waypoint trip preview - follows your saved points. Custom-stop mission budgets and live events require backend support.</div>}
    {!route&&!transport.localTrip&&<div className="workflow-info"><Icon name="compass" size={17}/><span>{transport.path?'Local terrain preview selected. Generate a mission plan in Planning to run the live EVA.':'Choose a route in Planning to activate shared navigation.'}</span><button onClick={onPlanning}>Open Planning</button></div>}
    <SimulationControls route={transport.localTrip?null:route} live={live} transport={transport} offline={offline}/>
    <div className="flight-workspace"><section className="flight-map-column"><div className="flight-mode-row"><div className="segmented"><button aria-pressed={transport.mode==='preview'} disabled={live.state==='running'} onClick={()=>transport.chooseMode('preview')}>Route preview</button><button aria-pressed={transport.mode==='live'} disabled={!route} onClick={()=>transport.chooseMode('live')}>Live mission</button></div><span>{transport.isLive?live.state==='paused'?'Mission paused':'Live position':transport.mode==='live'?'Waiting for mission telemetry':`${number(transport.progress*100)}% · preview only`}</span></div>
      <MapView site={mapSite} route={displayedRoute} live={displayedLive} position={transport.position} selected={selected} onSelect={onSelect} explorer previewEnabled={false} mapTitle="Astronaut tracking"/>
      <div className="shared-position-row"><span><i/>Shared navigation position</span><span>{transport.position?`r ${number(transport.position.row,1)} / c ${number(transport.position.col,1)}`:'No position yet'}</span></div>
      {transport.mode==='preview'&&transport.frame&&<label className="flight-progress">Route playback <strong>{number(transport.progress*100)}%</strong><input aria-label="Shared route progress" type="range" min="0" max="1" step=".001" value={transport.progress} onChange={e=>transport.seek(e.target.value)}/><small>Preview, Step, Back and Reset on the tracker update this map and both watch dials.</small></label>}
      <MissionMetrics live={live} equipment={equipment}/><p className="flight-mode-note">{transport.mode==='live'?'Live movement is controlled by the mission engine. Pause and switch to Route preview to step through the path without changing telemetry.':'Local preview moves the astronaut and both devices together. It does not consume mission resources.'}</p>
    </section>
    <section className="flight-devices" aria-label="Synchronized astronaut devices"><div className="flight-tracker-slot"><div className="device-section-label">First-person tracker</div><FieldTracker equipment={equipment} site={site} route={route} live={live} transport={transport} selected={selected} onSelect={onSelect}/></div><div className="flight-watch-slot"><div className="device-section-label">Habitat & route compass</div><EVAWatch equipment={equipment} embedded site={site} route={route} live={displayedLive} position={transport.position} path={transport.path} frame={transport.frame} progress={transport.progress} setProgress={transport.seek} playing={transport.playing} setPlaying={()=>transport.toggle()}/></div></section>
    </div>
    <SensorSummary feed={equipment} live={live} onDetails={onSensors}/>
    <div className="flight-copilot"><div className="workflow-section-heading"><div><span className="eyebrow">Decision support</span><h2>Mission copilot</h2></div><span className="small muted">{mock?'Recorded scenario':'Connected to mission service'}</span></div><div className="flight-copilot-grid"><DecisionPanel live={live} route={route}/><section className="flight-chat"><Chat mock={mock} disabled={live.state!=='idle'} onRoute={onCopilotRoute}/><p className="small muted">Copilot proposals update the mission plan while idle. Review their budget in Planning before starting the EVA.</p></section></div></div>
  </div>;
}
