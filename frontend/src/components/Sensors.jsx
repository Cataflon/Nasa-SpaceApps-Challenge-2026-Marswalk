import { useEffect, useRef, useState } from 'react';
import Icon from './Icon';
import { events, number } from '../utils';
import { modules, stateNames, equipmentReading, demoMeasurement } from '../sensors/equipment';
import '../sensors.css';

function ModuleImage({module}) {
  return <span className="module-photo" role="img" aria-label={`${module.name}, concept illustration`} style={{backgroundPosition:`${module.image%3*50}% ${module.image<3?0:100}%`}}/>;
}
function Status({state}) {return <span className={`equipment-status state-${state}`}><i/>{stateNames[state]}</span>;}

function Connections({container,metric,readings}) {
  const [geometry,setGeometry]=useState({width:1,height:1,paths:[]});
  useEffect(()=>{
    const root=container.current;
    if(!root)return;
    function measure(){
      const box=root.getBoundingClientRect();
      const paths=modules.flatMap(m=>{
        const card=root.querySelector(`[data-module="${m.key}"]`),pin=root.querySelector(`[data-pin="${m.key}"]`);
        if(!card||!pin)return [];
        const a=card.getBoundingClientRect(),b=pin.getBoundingClientRect();
        const x1=(m.side==='left'?a.right:a.left)-box.left,y1=a.top+a.height/2-box.top;
        const x2=b.left+b.width/2-box.left,y2=b.top+b.height/2-box.top;
        const bend=x1+(m.side==='left'?1:-1)*Math.min(36,Math.abs(x2-x1)*.35);
        return [{key:m.key,d:`M${x1},${y1} L${bend},${y1} L${x2},${y2}`}];
      });
      setGeometry({width:box.width,height:box.height,paths});
    }
    const observer=new ResizeObserver(measure);observer.observe(root);root.querySelectorAll('[data-module],.suit-figure').forEach(e=>observer.observe(e));measure();
    return()=>observer.disconnect();
  },[container]);
  return <svg className="equipment-connections" viewBox={`0 0 ${geometry.width} ${geometry.height}`} aria-hidden="true"><defs><marker id="equipment-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M1 1L9 5L1 9" fill="none" stroke="context-stroke" strokeWidth="1.4"/></marker></defs>{geometry.paths.map(p=><g key={p.key} className={`connection state-${readings[p.key].state} ${metric===p.key?'active':''}`}><path d={p.d} markerEnd="url(#equipment-arrow)"/><circle r="2.5" className="signal-dot"><animateMotion dur="4s" repeatCount="indefinite" path={p.d}/></circle></g>)}</svg>;
}

export default function Sensors({live}) {
  const [metric,setMetric]=useState('o2_pct'),[demo,setDemo]=useState(false),[demoStates,setDemoStates]=useState({}),[demoTime,setDemoTime]=useState(0),[demoSamples,setDemoSamples]=useState([]);
  const container=useRef(null), demoStatesRef=useRef(demoStates);
  demoStatesRef.current=demoStates;
  useEffect(()=>{
    if(!demo)return;
    let time=0;setDemoTime(0);setDemoSamples([]);
    const timer=setInterval(()=>{time++;setDemoTime(time);setDemoSamples(previous=>[...previous.slice(-119),{t:time,...Object.fromEntries(modules.map(m=>[m.key,demoStatesRef.current[m.key]==='fault'?null:demoMeasurement(m,time).value]))}]);},1000);
    return()=>clearInterval(timer);
  },[demo]);
  const readings=Object.fromEntries(modules.map(m=>[m.key,equipmentReading(m,live.tick,demo?'live':live.status,demo?demoMeasurement(m,demoTime,demoStates[m.key]??'ok'):null)]));
  const selected=modules.find(m=>m.key===metric),reading=readings[metric];
  const history=(demo?demoSamples:live.samples).filter(s=>Number.isFinite(s[metric])&&(selected.min===undefined||s[metric]>=selected.min)&&(selected.max===undefined||s[metric]<=selected.max));
  const min=history.length?Math.min(...history.map(s=>s[metric])):null,max=history.length?Math.max(...history.map(s=>s[metric])):null;
  const t0=history[0]?.t??0,t1=history.at(-1)?.t??0;
  const chart=history.map(s=>`${30+(s.t-t0)/Math.max(1,t1-t0)*620},${130-(s[metric]-min)/Math.max(.1,max-min)*95}`).join(' ');
  const faults=Object.values(readings).filter(r=>r.state==='fault').length,warnings=Object.values(readings).filter(r=>r.state==='warning').length,available=Object.values(readings).filter(r=>Number.isFinite(r.value)).length;
  function card(m){const r=readings[m.key];return <button key={m.key} data-module={m.key} className={`equipment-module state-${r.state} ${metric===m.key?'selected':''}`} onClick={()=>setMetric(m.key)} aria-pressed={metric===m.key} aria-controls="equipment-inspector"><div className="module-top"><span>{m.code} <small>/ {String(m.image+1).padStart(2,'0')}</small></span><Status state={r.state}/></div><div className="module-body"><ModuleImage module={m}/><div><h2>{m.name}</h2><strong className="module-value">{number(r.value,m.key==='dust_tau'?2:1)}<small>{m.unit}</small></strong><p>{m.description}</p></div></div><div className="module-bottom"><span>Measured accuracy <b>{r.accuracy?`±${number(r.accuracy.value,2)} ${r.accuracy.unit}`:'Not supplied'}</b></span><Icon name="chevron" size={14}/></div></button>;}
  return <div className="equipment-page">
    <div className="page-heading equipment-heading"><div><span className="eyebrow">Equipment & environmental telemetry</span><h1>A closer look at every system.</h1><p>Inspect a module or select its connection on the suit.</p></div><div className="equipment-source"><div className="segmented"><button aria-pressed={!demo} onClick={()=>setDemo(false)}>Mission feed</button><button aria-pressed={demo} onClick={()=>setDemo(true)}>Equipment demo</button></div><span>{demo?'Simulated readings & diagnostics':live.receivedAt?`Last received ${new Date(live.receivedAt).toLocaleTimeString()}`:'Waiting for mission telemetry'}</span></div></div>
    {demo&&<div className="equipment-demo-note" role="status"><Icon name="activity" size={16}/><span>Equipment demo · values, accuracy and faults are simulated. Mission telemetry is unaffected.</span></div>}
    <div className="equipment-summary"><div><span className={`summary-dot ${faults?'fault':warnings?'warning':''}`}/><strong>{faults?`${faults} module fault${faults>1?'s':''}`:warnings?`${warnings} reading${warnings>1?'s':''} to verify`:available?'Telemetry available':'Awaiting measurements'}</strong></div><span>{available} / 6 channels reporting</span><span>{warnings} warnings</span><span>{faults} faults</span><span className="summary-mode">{demo?'Demo diagnostics':live.tick?'Basic data validation · hardware health unreported':'Start an EVA to receive mission values'}</span></div>
    <section className="equipment-layout" ref={container} aria-label="Suit equipment map">
      <Connections container={container} metric={metric} readings={readings}/>
      <div className="equipment-stack left">{modules.filter(m=>m.side==='left').map(card)}</div>
      <div className="suit-stage"><div className="suit-title"><span>EVA suit</span><small>Equipment overview</small></div><div className="suit-figure"><img src="/equipment/eva-suit-watch.png" alt="Concept EVA spacesuit with a decorative wristwatch and interactive equipment attachment points"/>{modules.map(m=><button key={m.key} data-pin={m.key} className={`suit-hotspot state-${readings[m.key].state} ${metric===m.key?'selected':''}`} style={{left:`${m.pin[0]}%`,top:`${m.pin[1]}%`}} onClick={()=>setMetric(m.key)} aria-label={`Inspect ${m.name}: ${stateNames[readings[m.key].state]}`} aria-pressed={metric===m.key} aria-controls="equipment-inspector"><i/><span>{m.code}</span></button>)}</div><p className="suit-caption">Concept suit & module positions.<br/>Environmental readings describe conditions outside the suit.</p></div>
      <div className="equipment-stack right">{modules.filter(m=>m.side==='right').map(card)}</div>
    </section>
    <section id="equipment-inspector" className={`equipment-inspector state-${reading.state}`} aria-label={`${selected.name} details`}>
      <div className="inspector-overview"><div className="inspector-identity"><ModuleImage module={selected}/><div><span className="eyebrow">Selected module / {selected.code}</span><h2>{selected.name}</h2><p>{selected.location}</p></div></div><Status state={reading.state}/><p className="equipment-reason" aria-live="polite">{reading.reason}</p><dl className="equipment-facts"><div><dt>Current reading</dt><dd>{number(reading.value,2)} {selected.unit}</dd></div><div><dt>Measured accuracy</dt><dd>{reading.accuracy?`±${number(reading.accuracy.value,2)} ${reading.accuracy.unit}`:'Not supplied'}</dd></div><div><dt>Calibration</dt><dd>{demo?'Simulated self-test':'Not supplied'}</dd></div><div><dt>Source</dt><dd>{demo?'Equipment demo':live.mock?'Recorded mission scenario':'Mission telemetry'}</dd></div></dl><p className="equipment-action"><Icon name="shield" size={16}/>{selected.action}</p>{demo&&<fieldset className="diagnostic-controls"><legend>Preview this module's state</legend>{[['ok','Normal'],['warning','Warning'],['fault','Fault']].map(([state,label])=><button key={state} className={`state-${state}`} aria-pressed={(demoStates[metric]??'ok')===state} onClick={()=>setDemoStates(s=>({...s,[metric]:state}))}>{label}</button>)}</fieldset>}</div>
      <div className="equipment-trend"><div className="section-title"><h3>Measurement history</h3><span>{demo?'Last 120 seconds':'Last 120 samples'}</span></div>{history.length>1?<><svg viewBox="0 0 680 165" className="sensor-chart" role="img" aria-label={`${selected.name} history, minimum ${min}, maximum ${max} ${selected.unit}`}><defs><linearGradient id="equipment-trend-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="var(--accent)" stopOpacity=".18"/><stop offset="1" stopColor="var(--accent)" stopOpacity="0"/></linearGradient></defs>{[35,80,130].map(y=><path key={y} d={`M30 ${y}H650`} className="trend-grid"/>)}<polygon points={`30,140 ${chart} 650,140`} fill="url(#equipment-trend-fill)"/><polyline points={chart} fill="none" stroke="var(--accent)" strokeWidth="2"/><text x="30" y="160">{demo?'s':'t'}+{number(t0)}</text><text x="580" y="160">{demo?'s':'t'}+{number(t1)}</text></svg><div className="trend-range"><span>Min <b>{number(min,2)} {selected.unit}</b></span><span>Max <b>{number(max,2)} {selected.unit}</b></span><span>{history.length} valid samples</span></div></>:<div className="empty-chart"><Icon name="activity" size={30}/><p>{demo?'Collecting simulated samples…':'Trend appears after two valid mission readings.'}</p></div>}<div className="equipment-legend"><span className="state-ok"><i/>Normal / reported</span><span className="state-warning"><i/>Verify reading</span><span className="state-fault"><i/>Hardware fault</span><span className="state-waiting"><i/>Not available</span></div><p className="accuracy-note">Accuracy requires a reference measurement or calibration report. A plausible value alone does not establish accuracy or hardware health.</p></div>
    </section>
    <section className="equipment-events"><div className="section-title"><h3>Mission event log</h3><span>{live.events.length} events</span></div>{live.events.length?live.events.map((e,i)=><div className="event-row" key={`${e.t_min}-${i}`}><span>t+{e.t_min} min</span><Icon name="alert" size={16}/><strong>{events[e.event]??e.event}</strong><span>{live.mock?'Recorded scenario':'Mission event'}</span></div>):<p>No mission events received in this session.</p>}</section>
  </div>;
}
