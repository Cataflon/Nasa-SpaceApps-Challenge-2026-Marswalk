import {useEffect,useMemo,useState} from 'react';
import MapView from './MapView';
import FieldTracker from './FieldTracker';
import EVAWatch from './EVAWatch';
import DecisionPanel from './DecisionPanel';

import SensorSummary from './SensorSummary';
import SimulationControls from './SimulationControls';
import MissionMetrics from './MissionMetrics';
import Icon from './Icon';
import {decisions,number} from '../utils';
import {eventSpecs,eventPayload} from '../simulation/events';
const previewLive={state:'idle',tick:null,decision:null,trail:[],history:[],explanations:{}};
export default function SimulationWorkspace({equipment,site,mapSite,route,live,offline,transport,selected,onSelect,onSensors,onPlanning,mock,onCopilotRoute}){
  const displayedLive=transport.isLive?live:previewLive,scan=live.state==='idle'?null:live.tick?.scan;
  const displayedRoute=useMemo(()=>transport.path?{...route,path:transport.path}:route,[route,transport.path]);
  // Event placement happens on the map: `placing` holds the event being placed, the map reports the result.
  const [placing,setPlacing]=useState(null),[astronautAlert,setAstronautAlert]=useState(false),[zones,setZones]=useState([]),[note,setNote]=useState(null);
  useEffect(()=>{if(live.state==='idle'){setPlacing(null);setAstronautAlert(false);setZones([]);setNote(null);}},[live.state]);
  const placement=useMemo(()=>placing?{key:placing.kind+placing.at,mode:eventSpecs[placing.kind].place,color:eventSpecs[placing.kind].color,label:eventSpecs[placing.kind].label}:null,[placing]);
  const now=live.tick?.t_min??0,activeZones=useMemo(()=>zones.filter(z=>'pending' in z?z.pending===live.tick:now<z.until),[zones,now,live.tick]);
  function startPlacing(kind,values){transport.chooseMode('live');setNote(null);setPlacing({kind,values,at:Date.now()});document.getElementById('simulation-map-top')?.scrollIntoView({block:'start',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});}
  async function placed(result){if(!placing)return;const {kind,values}=placing,spec=eventSpecs[kind];setPlacing(null);
    try{const params=eventPayload(kind,values,result,site);await live.event(kind,params);
      if(spec.place==='astronaut')setAstronautAlert(true);
      // Until the engine sends its next tick (e.g. while paused) the placed hazard is shown from local state.
      else if(!spec.marker)setZones(list=>[...list.filter(z=>!('pending' in z)||z.pending===live.tick),{id:kind+Date.now(),row:result.center.row,col:result.center.col,radius_m:result.radius_m,color:spec.color,pending:live.tick,pulse:kind==='marsquake'}]);
      if(spec.marker)setZones(list=>[...list,{id:kind+Date.now(),row:result.center.row,col:result.center.col,radius_m:result.radius_m,color:spec.color,until:now+params.duration_min}]);
      setNote({text:`${spec.label} placed at t+${number(now)} min.${live.state==='paused'&&spec.place!=='astronaut'?' Resume the EVA to see it move.':''}`});
    }catch(err){setNote({error:true,text:err.message});}}
  // Sus: harta + tracker + ceas. Sub hartă: instrumentele; lângă ele (sub dispozitive): răspunsul copilotului.
  // Apoi controalele compacte și, la final, telemetria astronautului.
  return <div className="simulation-workspace sim-compact">
    {transport.localTrip&&<div className="workflow-info">Waypoint trip preview - follows your saved points. Generate a mission plan in Planning to run the live EVA.</div>}
    {!route&&!transport.localTrip&&<div className="workflow-info"><Icon name="compass" size={17}/><span>Choose a route in Planning to run the live EVA.</span><button onClick={onPlanning}>Open Planning</button></div>}
    <div className="flight-workspace"><section className="flight-map-column" id="simulation-map-top">
      <MapView site={mapSite} route={displayedRoute} live={displayedLive} position={transport.position} selected={selected} onSelect={onSelect} explorer previewEnabled={false} mapTitle="Astronaut tracking" placement={placement} onPlaced={placed} onPlacementCancel={()=>setPlacing(null)} astronautAlert={astronautAlert} effectZones={activeZones}/>
      {transport.mode==='preview'&&transport.frame&&<label className="flight-progress">Route playback <strong>{number(transport.progress*100)}%</strong><input aria-label="Shared route progress" type="range" min="0" max="1" step=".001" value={transport.progress} onChange={e=>transport.seek(e.target.value)}/></label>}
      <MissionMetrics live={live} equipment={equipment}/>
    </section>
    <section className="flight-devices" aria-label="Synchronized astronaut devices"><div className="flight-tracker-slot"><div className="device-section-label">First-person tracker</div><FieldTracker equipment={equipment} site={site} route={route} live={live} transport={transport} selected={selected} onSelect={onSelect}/></div><div className="flight-watch-slot"><div className="device-section-label">Habitat & route compass</div><EVAWatch equipment={equipment} embedded site={site} route={route} live={displayedLive} position={transport.position} path={transport.path} frame={transport.frame} progress={transport.progress} setProgress={transport.seek} playing={transport.playing} setPlaying={()=>transport.toggle()}/></div>
      <div className={`sim-copilot-card ${offline?'offline':''}`} aria-live="polite">
        {/* Scanarea împrejurimilor: vine în fiecare tick din backend (`tick.scan`), fără LLM. */}
        <div className={`scan-line scan-${offline?'offline':scan?.status??'idle'}`} role="status"><i/><strong>Scan</strong><span>{offline?'Link interrupted. Last scan result is shown.':scan?scan.text:live.state==='idle'?'Starts with the EVA: surroundings are checked every tick.':'Scanning…'}</span>{scan&&<small>t+{number(scan.t_min)} min</small>}</div>
        <DecisionPanel live={live} route={route}/></div>
    </section>
    </div>
    <SimulationControls site={site} route={transport.localTrip?null:route} live={live} transport={transport} offline={offline} placing={placing} onPlace={startPlacing} onCancelPlace={()=>setPlacing(null)} note={note}/>
    <SensorSummary feed={equipment} live={live} onDetails={onSensors}/>
  </div>;
}
