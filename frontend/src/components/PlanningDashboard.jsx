import {useState,useRef} from 'react';
import Planner from './Planner';
import BudgetPanel from './BudgetPanel';
import RouteAnalysisPanel from './RouteAnalysisPanel';
import Icon from './Icon';
import {number} from '../utils';
export default function PlanningDashboard({site,planner,onCustomPlan,localTrip,live,selected,onSelect,report,previewKind,onPreviewKind,settings,onSettings,points,onPoints,onSimulate,onFocus}){
  const [initialTargetId,setInitialTargetId]=useState(null),form=useRef(null),route=planner.result?.data;
  const focusPlanner=id=>{if(id)setInitialTargetId(id);form.current?.scrollIntoView({block:'center',behavior:'smooth'});};
  return <section className="planning-dashboard" aria-label="Expedition planning dashboard"><div className="workflow-section-heading"><div><span className="eyebrow">Before you step outside</span><h2>Design the excursion.</h2><p>Choose objectives, compare terrain and check the mission budget.</p></div></div>
    <div className="planning-dashboard-grid"><section className="planning-card science-catalog"><h3>Science sites</h3>{site.targets.map((t,i)=><div className={`catalog-target ${selected?.id===t.id?'selected':''}`} key={t.id}><button onClick={()=>onSelect(t)}><span>{String(i+1).padStart(2,'0')}</span><div><strong>{t.name.split(',')[0]}</strong><small>{t.name.split(',').slice(1).join(',').trim()||t.kind} · {t.dwell_min} min</small></div><Icon name="target" size={15}/></button><button className="text-button" onClick={()=>{onSelect(t);focusPlanner(t.id);}}>Use in mission<Icon name="plus" size={12}/></button></div>)}{selected&&<div className="selected-planning-point"><h4>{selected.name}</h4><p>Grid {selected.row} / {selected.col} · {number(report?.selectedElevation,1)} m CTX elevation</p>{selected.note&&<p>{selected.note}</p>}<button className="button secondary" onClick={()=>onFocus(selected)}><Icon name="target" size={14}/>Focus on map</button></div>}</section>
      <section className="planning-card plan-form-card" ref={form}><Planner key={initialTargetId??'default'} points={points} onCustomPlan={onCustomPlan} embedded initialTargetId={initialTargetId} site={site} planner={planner} live={live}/>{planner.result?.mock&&<p className="workflow-demo-note">Recorded demo route. Backend planning uses the selected objectives when available.</p>}</section>
      <section className="planning-card mission-budget-card"><BudgetPanel route={localTrip?null:route} hideProfile/>{localTrip&&<p className="small muted">Waypoint trip is a local terrain preview. Mission budget requires backend validation of custom stops.</p>}</section>
      <section className="planning-card terrain-comparison"><RouteAnalysisPanel report={report} route={route} live={{state:'idle'}} previewKind={previewKind} onPreviewKind={onPreviewKind} settings={settings} onSettings={onSettings} onPlan={()=>focusPlanner(site.targets.some(t=>t.id===selected?.id)?selected.id:null)} disabled={live.state==='running'}/></section>
    </div></section>;
}
