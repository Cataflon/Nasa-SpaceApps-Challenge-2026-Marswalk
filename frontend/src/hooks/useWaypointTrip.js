import {useEffect,useRef,useState} from 'react';
import {loadTerrain} from '../api/client';
export function useWaypointTrip(site,points){
  const [ids,setIds]=useState([]),[returnHome,setReturnHome]=useState(true),[result,setResult]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const active=useRef(null),version=useRef(0);
  const signature=points.map(p=>`${p.id}:${p.row}:${p.col}`).join('|');
  useEffect(()=>{version.current++;active.current?.terminate();setBusy(false);setResult(null);setError('');setIds(previous=>previous.filter(id=>points.some(p=>p.id===id)));},[signature]);
  useEffect(()=>()=>{version.current++;active.current?.terminate();},[]);
  function invalidate(){version.current++;active.current?.terminate();setBusy(false);setResult(null);setError('');}
  const changeIds=next=>{invalidate();setIds(next);};
  const changeReturn=value=>{invalidate();setReturnHome(value);};
  async function build(requestedStops){
    invalidate();const token=version.current;setBusy(true);
    try{const {grid}=await loadTerrain();if(token!==version.current)return;
      const stops=Array.isArray(requestedStops)?requestedStops:ids.map(id=>points.find(p=>p.id===id)).filter(Boolean);if(!stops.length)throw Error('Add at least one waypoint to the trip.');
      const worker=new Worker(new URL('../terrain/routing.worker.js',import.meta.url),{type:'module'});active.current=worker;
      worker.onmessage=({data})=>{if(token!==version.current)return;worker.terminate();setBusy(false);if(data.error||!data.safe){setError(data.error??'No traversable path connects these waypoints.');return;}setResult({...data.safe,route_id:`local_trip_${token}`,name:`Waypoint trip · ${stops.map(p=>p.name).join(' → ')}`,preset:'safe',local:true,stops:ids});};
      worker.onerror=()=>{if(token===version.current){worker.terminate();setBusy(false);setError('Waypoint routing failed.');}};
      worker.postMessage({type:'grid',grid});worker.postMessage({id:token,start:site.habitat,tripStops:[...stops,...(returnHome?[site.habitat]:[])]});
    }catch(e){if(token===version.current){setBusy(false);setError(e.message);}}
  }
  // The trip route follows the itinerary: any change to the stops rebuilds it.
  const idsKey=ids.join('|');
  useEffect(()=>{if(!site||!ids.length)return;const timer=setTimeout(()=>build(),120);return()=>clearTimeout(timer);},[idsKey,returnHome,signature,site?.site_id]);
  return {ids,setIds:changeIds,returnHome,setReturnHome:changeReturn,result,busy,error,build,clear:invalidate};
}
