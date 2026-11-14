import {useState,useRef} from 'react';
import Planner from './Planner';
import BudgetPanel from './BudgetPanel';
import RouteAnalysisPanel from './RouteAnalysisPanel';
import Icon from './Icon';
export default function PlanningDashboard({site,planner,onCustomPlan,localTrip,live,selected,onSelect,report,previewKind,onPreviewKind,settings,onSettings,points,onPoints,onSimulate,onFocus}){
  const [initialTargetId,setInitialTargetId]=useState(null),form=useRef(null),route=planner.result?.data;
  const focusPlanner=id=>{if(id)setInitialTargetId(id);form.current?.scrollIntoView({block:'center',behavior:'smooth'});};
  return <section className="planning-dashboard" aria-label="Expedition planning dashboard"><div className="workflow-section-heading"><div><span className="eyebrow">Before you step outside</span><h2>Design the excursion.</h2><p>Choose objectives, compare terrain and check the mission budget.</p></div></div>
    <div className="planning-dashboard-grid"><section className="planning-card science-catalog compact"><h3>Science sites</h3><div className="catalog-list">{site.targets.map((t,i)=><div className={`catalog-target ${selected?.id===t.id?'selected':''}`} key={t.id}><button title="Show on map" onClick={()=>{onSelect(t);onFocus(t);}}><span>{String(i+1).padStart(2,'0')}</span><div><strong>{t.name.split(',')[0]}</strong><small>{t.dwell_min} min on site</small></div></button><button className="catalog-use" title="Use in mission plan" aria-label={`Use ${t.name.split(',')[0]} in mission plan`} onClick={()=>{onSelect(t);focusPlanner(t.id);}}><Icon name="plus" size={12}/></button></div>)}</div></section>
      <section className="planning-card plan-form-card" ref={form}><Planner key={initialTargetId??'default'} points={points} onCustomPlan={onCustomPlan} embedded initialTargetId={initialTargetId} site={site} planner={planner} live={live}/>{planner.result?.mock&&<p className="workflow-demo-note">Recorded demo route. Backend planning uses the selected objectives when available.</p>}</section>
      <section className="planning-card mission-budget-card"><BudgetPanel route={localTrip?null:route} hideProfile/>{localTrip&&<p className="small muted">Waypoint trip is a local terrain preview. Mission budget requires backend validation of custom stops.</p>}</section>
      <section className="planning-card terrain-comparison"><RouteAnalysisPanel report={report} route={route} live={{state:'idle'}} previewKind={previewKind} onPreviewKind={onPreviewKind} settings={settings} onSettings={onSettings} onPlan={()=>focusPlanner(site.targets.some(t=>t.id===selected?.id)?selected.id:null)} disabled={live.state==='running'}/></section>
    </div></section>;
}
