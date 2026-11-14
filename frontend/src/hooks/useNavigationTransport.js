import {useEffect,useMemo,useState,useCallback} from 'react';
import {advancePreview,routeFrame} from '../terrain/navigation';
export function useNavigationTransport({route,tripRoute,navigationRoute,live,livePosition,cellSize}){
  const [mode,setMode]=useState('preview'),[progress,setProgress]=useState(0),[playing,setPlaying]=useState(false);
  const previewPath=tripRoute?.path??route?.path??navigationRoute?.path;
  const isLive=mode==='live'&&live.state!=='idle'&&!!live.tick;
  const path=isLive?live.tick.remaining_path:previewPath;
  const frame=useMemo(()=>routeFrame(path,progress,isLive?livePosition??live.tick?.astronaut:null),[path,progress,isLive,livePosition,live.tick?.astronaut]);
  const total=useMemo(()=>routeFrame(previewPath)?.total??0,[previewPath]);
  useEffect(()=>{setProgress(0);setPlaying(false);},[tripRoute?.route_id,navigationRoute?.targetId,navigationRoute?.kind,route?.route_id]);
  useEffect(()=>{if(live.state==='running'){setMode('live');setPlaying(false);}},[live.state]);
  useEffect(()=>{if(!playing||mode!=='preview'||!total)return;let raf,last=performance.now();const run=now=>{if(now-last<32){raf=requestAnimationFrame(run);return;}const elapsed=Math.min(.1,(now-last)/1000);last=now;setProgress(p=>{const next=advancePreview(p,elapsed*100,total,cellSize);if(next===1)setPlaying(false);return next;});raf=requestAnimationFrame(run);};raf=requestAnimationFrame(run);return()=>cancelAnimationFrame(raf);},[playing,mode,total,cellSize]);
  const seek=useCallback(value=>{if(mode!=='preview')return;setPlaying(false);setProgress(Math.max(0,Math.min(1,Number(value))));},[mode]);
  const step=useCallback(meters=>{if(mode!=='preview')return;setPlaying(false);setProgress(p=>advancePreview(p,meters,total,cellSize));},[mode,total,cellSize]);
  const canToggle=mode==='preview'?!!frame:!!route&&route.verdict!=='NO-GO'&&!live.busy&&!['offline','reconnecting','invalid'].includes(live.status)&&live.state!=='finished';
  const toggle=()=>{if(!canToggle)return;if(mode==='live'){if(route&&!live.busy)live.control(live.state==='running'?'pause':'start');}else if(frame){setPlaying(p=>!p);}};
  const reset=()=>{setProgress(0);setPlaying(false);if(mode==='live')live.control('reset');};
  const chooseMode=next=>{if(next==='preview'&&live.state==='running')return;setPlaying(false);setMode(next);};
  const position=isLive?livePosition??live.tick?.astronaut:frame?.eye??null;
  return {mode,isLive,localTrip:mode==='preview'&&!!tripRoute,path,frame,position,progress,playing,canToggle,seek,step,toggle,reset,chooseMode,canStep:mode==='preview'&&!!frame,destination:isLive?'Live mission route':tripRoute?tripRoute.name:route?'Mission plan':navigationRoute?.name??'No route selected'};
}
