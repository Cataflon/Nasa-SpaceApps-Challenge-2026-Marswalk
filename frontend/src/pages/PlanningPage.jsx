import {useEffect,useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {useMissionContext} from '../mission/MissionContext';
import {useTripProfile} from '../hooks/useTripProfile';
import PlanningMap from '../components/planning/PlanningMap';
import TerrainLayersPanel from '../components/planning/TerrainLayersPanel';
import MapPointPopup from '../components/planning/MapPointPopup';
import MissionOverlay from '../components/planning/MissionOverlay';
import TripProfile from '../components/planning/TripProfile';
const planningLive={state:'idle',tick:null,decision:null,trail:[],history:[],explanations:{}};
// Planning: the terrain map with the mission card on it, then the elevation and slope profile of the trip.
export default function PlanningPage(){
  const m=useMissionContext(),navigate=useNavigate(),{site,mapSite,route,trip,points,selected,setSelected,live}=m;
  const [report,setReport]=useState(null),[settings,setSettings]=useState({layer:'surface',showHazards:true,showRoutes:true}),[profileHover,setProfileHover]=useState(null),[layersOpen,setLayersOpen]=useState(false);
  useEffect(()=>{setProfileHover(null);},[selected?.id]);
  // The profile follows the validated mission route from the backend (no local routing in the frontend).
  const tripPath=route?.path??null,profile=useTripProfile(tripPath);
  const stops=trip.ids.map(id=>mapSite.targets.find(p=>p.id===id)).filter(Boolean);
  // Din panoul de misiune: deschide Simulation și pornește EVA la viteza 1× (dacă nu rulează deja).
  function startSimulation(){m.transport.chooseMode('live');navigate('/simulation');if(['idle','finished'].includes(live.state))live.control('start',1);}
  return <div className="planning-workspace planning-fullscreen">
    <div id="planning-map-top" className="planning-map-top"><PlanningMap popup={selected&&selected.id!=='habitat'?<MapPointPopup selected={selected} points={points} trip={trip} onAdd={m.addWaypoint} onDelete={()=>{m.savePoints(points.filter(p=>p.id!==selected.id));setSelected(null);}} onClose={()=>setSelected(null)}/>:null} onFloatingChange={m.setHasPip} site={mapSite} route={route} live={planningLive} position={null} selected={selected} onSelect={setSelected} onRoutePreview={m.setNavigationRoute} settings={settings} onReport={setReport} profileHover={profileHover} routeKind="safe" mapTitle="Jezero · route design" layersOpen={layersOpen} onLayersToggle={()=>setLayersOpen(v=>!v)} layerPanel={<TerrainLayersPanel hideOverview site={site} info={report?.info} settings={settings} onChange={setSettings} hazardCount={0}/>} overlay={<MissionOverlay site={site} points={points} trip={trip} route={route} mock={!!m.planner.result?.mock} estimate={m.estimate} settings={m.planSettings} onSettings={m.setPlanSettings} locked={m.planLocked} busy={live.busy} onEndEva={()=>live.control('reset')} onSelect={setSelected} onSimulate={startSimulation}/>}/>
    </div>
    <div className="planning-map-legend"><span>USGS CTX · {report?.info?`${report.info.cols*report.info.cell_size_m/1000} × ${report.info.rows*report.info.cell_size_m/1000} km · ${report.info.cell_size_m} m grid · vertical ${report.info.verticalScale}×`:'Loading source metadata'}</span><div><span><i style={{background:'#4BC3A2'}}/>Slope weighted</span><span><i style={{background:'#E97845'}}/>Shortest / mission route</span><span><i style={{background:'#A18AF0'}}/>Science preset</span></div></div>
    <TripProfile profile={profile} stops={stops} label={tripPath?'Mission route':null} busy={m.estimate.busy} onHover={setProfileHover}/>
    {m.notesError&&<p className="error" role="status">{m.notesError}</p>}
  </div>;
}
