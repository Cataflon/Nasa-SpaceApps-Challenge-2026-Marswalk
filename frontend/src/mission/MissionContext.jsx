import {createContext,useContext,useEffect,useMemo,useState} from 'react';
import {useSite,useRoute,useLive,usePosition} from '../hooks/useMission';
import {useNavigationTransport} from '../hooks/useNavigationTransport';
import {useEquipmentFeed} from '../hooks/useEquipmentFeed';
import {useWaypointTrip} from '../hooks/useWaypointTrip';
import {useMissionEstimate} from '../hooks/useMissionEstimate';
// Mission state shared by the three pages (Planning, Simulation, Sensors). It lives above the router,
// so the plan, the live EVA and the sensor feed survive navigation between pages.
const MissionContext=createContext(null);
export const useMissionContext=()=>useContext(MissionContext);
function readNotes(siteId){try{const data=JSON.parse(localStorage.getItem(`marswalk.notes.${siteId}`)??'[]');return Array.isArray(data)?data.filter(p=>p&&typeof p.name==='string'&&p.kind==='annotation'&&Number.isFinite(p.row)&&Number.isFinite(p.col)).slice(0,100):[];}catch{return [];}}
export function MissionProvider({children}){
  const siteResult=useSite(),planner=useRoute(),live=useLive(planner.result),equipment=useEquipmentFeed(live);
  const livePosition=usePosition(live.tick,live.speed,live.state!=='running'||!['live','mock'].includes(live.status));
  const [selected,setSelected]=useState(null),[navigationRoute,setNavigationRoute]=useState(null),[points,setPoints]=useState([]),[notesError,setNotesError]=useState(''),[hasPip,setHasPip]=useState(false);
  const site=siteResult.data,route=planner.result?.data,mock=siteResult.mock||planner.result?.mock,offline=['offline','reconnecting','invalid'].includes(live.status);
  useEffect(()=>{setPoints(site?readNotes(site.site_id):[]);setNotesError('');},[site?.site_id]);
  const mapSite=useMemo(()=>site?{...site,targets:[...site.targets,...points]}:null,[site,points]);
  const trip=useWaypointTrip(site,mapSite?.targets??[]);
  // Planul de misiune vine din backend la fiecare schimbare a trip-ului (panoul de pe harta de planning).
  const [planSettings,setPlanSettings]=useState({preset:'safe',duration:300}),planLocked=['running','paused'].includes(live.state);
  const estimate=useMissionEstimate({site,ids:trip.ids,points,returnHome:trip.returnHome,preset:planSettings.preset,duration:planSettings.duration,locked:planLocked,onResult:planner.setResult});
  const transport=useNavigationTransport({tripRoute:route?null:trip.result,route,navigationRoute,live,livePosition,cellSize:site?.cell_size_m??20});
  function savePoints(next){if(next.length>100){setNotesError('This map supports up to 100 local notes.');return;}setPoints(next);try{localStorage.setItem(`marswalk.notes.${site.site_id}`,JSON.stringify(next));setNotesError('');}catch{setNotesError('Notes are available for this session but could not be saved on this device.');}}
  function addWaypoint(name){if(!selected)return;if(points.length>=100){setNotesError('This map supports up to 100 local notes.');return;}const point={id:'note_'+crypto.randomUUID(),name,tag:'waypoint',row:selected.row,col:selected.col,kind:'annotation',dwell_min:0};savePoints([...points,point]);trip.setIds([...trip.ids,point.id]);setSelected(null);}
  const value={siteResult,site,mapSite,planner,route,mock,offline,live,equipment,transport,trip,estimate,planSettings,setPlanSettings,planLocked,points,savePoints,addWaypoint,notesError,selected,setSelected,setNavigationRoute,hasPip,setHasPip};
  return <MissionContext.Provider value={value}>{children}</MissionContext.Provider>;
}
