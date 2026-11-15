import {useEffect,useRef,useState} from 'react';
import {planRoute} from '../api/client';
// Asks the mission backend for a validated plan whenever the trip or the settings change.
// Catalog targets are sent by id; saved waypoints travel as `custom_stops` (contract 1.1, §5).
export function useMissionEstimate({site,ids,points,returnHome,preset,duration,locked,onResult}){
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const version=useRef(0);
  const used=points.filter(p=>ids.includes(p.id));
  const key=JSON.stringify([ids,used.map(p=>[p.id,p.name,p.row,p.col,p.dwell_min]),returnHome,preset,duration]);
  useEffect(()=>{
    if(!site||locked)return;
    const token=++version.current;
    if(!ids.length){setBusy(false);setError('');onResult(null);return;}
    const timer=setTimeout(async()=>{
      setBusy(true);setError('');
      const catalog=new Set(site.targets.map(t=>t.id));
      const custom=used.filter(p=>!catalog.has(p.id)).map(p=>({id:p.id,name:p.name,row:Math.round(p.row),col:Math.round(p.col),tag:p.tag??'waypoint',dwell_min:p.dwell_min??0}));
      try{
        const r=await planRoute({start:site.habitat,stops:ids,custom_stops:custom,return_to_habitat:returnHome,preset,start_time_min:0,max_duration_min:Number(duration)});
        if(token!==version.current)return;
        if(r.mock&&custom.length){onResult(null);setError('Mission service unavailable: custom points need the planning backend.');}
        else onResult(r);
      }catch(e){if(token===version.current){onResult(null);setError(e.message);}}
      finally{if(token===version.current)setBusy(false);}
    },400);
    return()=>clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[key,site?.site_id,locked]);
  return {busy,error};
}
