import {useState} from 'react';
import Icon from './Icon';
import {effectiveVerdict,number} from '../utils';
import {eventSpecs} from '../simulation/events';
export default function SimulationControls({site,route,live,transport,offline,placing,onPlace,onCancelPlace,note}){
  const [kind,setKind]=useState('local_storm'),[values,setValues]=useState({...eventSpecs.local_storm.defaults});
  const blocked=!route||effectiveVerdict(route)==='NO-GO'||live.busy||offline,spec=eventSpecs[kind],active=['running','paused'].includes(live.state);
  function choose(value){setKind(value);setValues({...eventSpecs[value].defaults});if(placing)onCancelPlace();}
  return <section className="flight-controls" aria-label="Simulation controls"><div className="flight-run-controls"><button className="button primary" disabled={blocked||live.state==='finished'} onClick={()=>{transport.chooseMode('live');live.control(live.state==='running'?'pause':'start');}}><Icon name={live.state==='running'?'pause':'play'} size={16}/>{live.state==='running'?'Pause EVA':live.state==='paused'?'Resume EVA':'Start EVA'}</button><button className="button secondary" disabled={!route||live.busy} onClick={()=>{transport.seek(0);live.control('reset');}}><Icon name="reset" size={15}/>Reset mission</button><label>Simulation speed<select aria-label="Simulation speed" value={live.speed} disabled={!route||live.busy} onChange={e=>live.control('speed',Number(e.target.value))}>{[1,5,10,30,60].map(v=><option key={v} value={v}>{v}x</option>)}</select></label><span className="flight-time">t+<strong>{number(live.tick?.t_min??0)}</strong> min</span></div>
  <div className="event-composer event-placer"><span className="event-compact-title">Configure an event</span>
    <div className="event-place-row"><label>Event type<select aria-label="Simulated event" value={kind} onChange={e=>choose(e.target.value)}>{Object.entries(eventSpecs).map(([id,s])=><option key={id} value={id}>{s.label}</option>)}</select></label>
      {placing?<button type="button" className="button secondary" onClick={onCancelPlace}><Icon name="close" size={14}/>Cancel placing</button>:<button type="button" className="button primary" disabled={blocked||!active} onClick={()=>onPlace(kind,values)}><Icon name="target" size={14}/>Place element</button>}
      <p className="event-help">{!active?'Start the EVA first, then place events on the map.':placing?'Follow the steps shown on the map. Press Esc to cancel.':spec.help}</p></div>
    <details className="event-advanced"><summary>Fine-tune (optional)</summary><div className="event-fields">{spec.fields.map(([key,label,min,max,step])=><label key={key}>{label}<input type="number" value={values[key]??''} min={min} max={max} step={step} onChange={e=>setValues(v=>({...v,[key]:e.target.value}))}/></label>)}</div></details>
    {live.mock&&<p className="event-help">Recorded demo uses preset events; placement is applied by the real backend.</p>}
    {note&&<p role="status" className={note.error?'error':'event-note'}>{note.text}</p>}</div>{live.error&&<p className="error" role="alert">{live.error}</p>}</section>;
}
