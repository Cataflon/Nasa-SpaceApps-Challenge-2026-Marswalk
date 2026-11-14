import {useEffect,useMemo,useState} from 'react';
import {modules,demoMeasurement,equipmentReading} from '../sensors/equipment';
// Owned by App so page changes never create another sensor clock or source.
export function useEquipmentFeed(live){
  const [demo,setDemo]=useState(false),[states,setStates]=useState({}),[time,setTime]=useState(0),[samples,setSamples]=useState([]);
  useEffect(()=>{if(!demo)return;const timer=setInterval(()=>setTime(t=>t+1),1000);return()=>clearInterval(timer);},[demo]);
  const tick=useMemo(()=>demo?{sensors:Object.fromEntries(modules.map(m=>[m.key,states[m.key]==='fault'?null:demoMeasurement(m,time).value])),sensor_health:Object.fromEntries(modules.map(m=>[m.key,demoMeasurement(m,time,states[m.key]??'ok')]))}:live.tick,[demo,time,states,live.tick]);
  useEffect(()=>{if(demo)setSamples(previous=>[...previous.slice(-119),{t:time,...tick.sensors}]);},[demo,time,tick]);
  const status=demo?'live':live.status;
  const readings=useMemo(()=>Object.fromEntries(modules.map(m=>[m.key,equipmentReading(m,tick,status)])),[tick,status]);
  return {demo,setDemo,states,setStates,time,readings,tick,status,samples:demo?samples:live.samples,receivedAt:demo?null:live.receivedAt};
}
