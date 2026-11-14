import {useEffect,useMemo,useState} from 'react';
import {useSite,useRoute,useLive,usePosition} from './hooks/useMission';
import {useNavigationTransport} from './hooks/useNavigationTransport';
import WorkspaceNavigation from './components/WorkspaceNavigation';
import PlanningMap from './components/PlanningMap';
import PlanningDashboard from './components/PlanningDashboard';
import TerrainLayersPanel from './components/TerrainLayersPanel';
import ElevationProfile from './components/ElevationProfile';
import SimulationWorkspace from './components/SimulationWorkspace';
import Sensors from './components/Sensors';
import Icon from './components/Icon';
import TaggedPoints from './components/TaggedPoints';
import {useEquipmentFeed} from './hooks/useEquipmentFeed';
import {useWaypointTrip} from './hooks/useWaypointTrip';
const planningLive={state:'idle',tick:null,decision:null,trail:[],history:[],explanations:{}};
function readNotes(siteId){try{const data=JSON.parse(localStorage.getItem(`marswalk.notes.${siteId}`)??'[]');return Array.isArray(data)?data.filter(p=>p&&typeof p.name==='string'&&p.kind==='annotation'&&Number.isFinite(p.row)&&Number.isFinite(p.col)).slice(0,100):[];}catch{return [];}}
export default function App(){
  const siteResult=useSite(),planner=useRoute(),live=useLive(planner.result),equipment=useEquipmentFeed(live);
  const livePosition=usePosition(live.tick,live.speed,live.state!=='running'||!['live','mock'].includes(live.status));
  const [hasPip,setHasPip]=useState(false),[navCollapsed,setNavCollapsed]=useState(()=>window.innerWidth<1200),[page,setPage]=useState('mission'),[selected,setSelected]=useState(null),[navigationRoute,setNavigationRoute]=useState(null),[report,setReport]=useState(null),[settings,setSettings]=useState({layer:'surface',showHazards:true,showRoutes:true}),[profileHover,setProfileHover]=useState(null),[cameraRequest,setCameraRequest]=useState(null),[previewKind,setPreviewKind]=useState('safe'),[layersOpen,setLayersOpen]=useState(false),[points,setPoints]=useState([]),[notesError,setNotesError]=useState('');
  const site=siteResult.data,route=planner.result?.data,mock=siteResult.mock||planner.result?.mock,offline=['offline','reconnecting','invalid'].includes(live.status);
  useEffect(()=>{setPoints(site?readNotes(site.site_id):[]);setNotesError('');},[site?.site_id]);
  useEffect(()=>{setProfileHover(null);setPreviewKind('safe');},[selected?.id]);
  useEffect(()=>{window.scrollTo({top:0,behavior:'instant'});},[page]);
  const mapSite=useMemo(()=>site?{...site,targets:[...site.targets,...points]}:null,[site,points]);
  const trip=useWaypointTrip(site,points);
  const transport=useNavigationTransport({tripRoute:trip.result,route,navigationRoute,live,livePosition,cellSize:site?.cell_size_m??20});
  function savePoints(next){if(next.length>100){setNotesError('This map supports up to 100 local notes.');return;}setPoints(next);try{localStorage.setItem(`marswalk.notes.${site.site_id}`,JSON.stringify(next));setNotesError('');}catch{setNotesError('Notes are available for this session but could not be saved on this device.');}}
  function focus(target){setCameraRequest({target,at:Date.now()});document.getElementById('planning-map-top')?.scrollIntoView({block:'start',behavior:'smooth'});}
  if(!site)return <div className="loading-screen"><img className="loading-brand-logo" src="/images/marswalk_logo_transparent.png" alt="Marswalk"/><p>{siteResult.error??'Loading expedition area…'}</p></div>;
  return <div className={`app expedition-shell workflow-shell ${hasPip?'has-pip':''} ${navCollapsed?'nav-collapsed':''} view-${page}`}><WorkspaceNavigation collapsed={navCollapsed} onToggle={()=>setNavCollapsed(v=>!v)} page={page} onNavigate={setPage} mock={mock} offline={offline} site={site}/>{offline&&<div className="connection-banner" role="status">Live link interrupted. Last received data retained; position is held.</div>}
    <main className="workflow-main">
    {page==='mission'&&<div className="planning-workspace"><div className="workflow-page-heading"><div><span className="eyebrow">Route design</span><h1>Plan the next expedition.</h1><p>Explore the terrain, mark locations and build a mission you can afford.</p></div><div className="planning-heading-actions"><button className="button primary" onClick={()=>setPage('simulation')}>Open simulation<Icon name="chevron" size={15}/></button></div></div>
      <TaggedPoints siteId={site.site_id} selected={selected} points={points} onChange={savePoints} onSelect={setSelected} trip={trip} onPreview={()=>{transport.chooseMode('preview');setPage('simulation');}} running={live.state==='running'}/><div id="planning-map-top" className="planning-map-top"><PlanningMap onFloatingChange={setHasPip} site={mapSite} route={trip.result??route} live={planningLive} position={null} selected={selected} onSelect={setSelected} onRoutePreview={setNavigationRoute} settings={settings} onReport={setReport} profileHover={profileHover} focusRequest={cameraRequest} routeKind={previewKind} mapTitle="Jezero · route design" layersOpen={layersOpen} onLayersToggle={()=>setLayersOpen(v=>!v)} layerPanel={<TerrainLayersPanel hideOverview site={site} info={report?.info} settings={settings} onChange={setSettings} hazardCount={0}/>}/>
      </div>
      <div className="planning-map-legend"><span>USGS CTX · {report?.info?`${report.info.cols*report.info.cell_size_m/1000} × ${report.info.rows*report.info.cell_size_m/1000} km · ${report.info.cell_size_m} m grid · vertical ${report.info.verticalScale}×`:'Loading source metadata'}</span><div><span><i style={{background:'#4BC3A2'}}/>Slope weighted</span><span><i style={{background:'#E97845'}}/>Shortest / mission route</span><span><i style={{background:'#A18AF0'}}/>Science preset</span></div></div>
      <ElevationProfile profile={report?.profile} label={report?.profileLabel} onHover={setProfileHover}/>{notesError&&<p className="error" role="status">{notesError}</p>}
      <PlanningDashboard site={site} planner={planner} onCustomPlan={trip.build} localTrip={trip.result} live={live} selected={selected} onSelect={setSelected} report={report} previewKind={previewKind} onPreviewKind={setPreviewKind} settings={settings} onSettings={setSettings} points={points} onPoints={savePoints} onSimulate={()=>setPage('simulation')} onFocus={focus}/>
    </div>}
    {page==='simulation'&&<SimulationWorkspace equipment={equipment} site={site} mapSite={mapSite} route={route} live={live} offline={offline} transport={transport} selected={selected} onSelect={setSelected} onSensors={()=>setPage('sensors')} onPlanning={()=>setPage('mission')} mock={mock} onCopilotRoute={planner.setResult}/>}
    {page==='sensors'&&<Sensors live={live} feed={equipment}/>}
    </main><footer className="app-footer"><span>Marswalk Copilot</span><span>{mock?'DEMONSTRATION DATA':'MISSION SERVICE'} · {site.cell_size_m} m planning grid</span><span>Jezero surface exploration</span></footer>
  </div>;
}
