import Icon from './Icon';
import { number } from '../utils';
export default function RouteAnalysisPanel({report,route,live,previewKind,onPreviewKind,settings,onSettings,onPlan,disabled}){
  const budget=live.tick?.budget??route?.budget,local=report?.preview?.[previewKind];
  const chosen=live.decision?.alternatives?.find(a=>a.id===live.decision.alternative_id),risk=chosen?.risk??route?.risk;
  const oxygenUsed=Number.isFinite(route?.budget?.o2_start_pct)&&Number.isFinite(budget?.o2_end_pct)?route.budget.o2_start_pct-budget.o2_end_pct:null;
  return <section className="route-analysis"><div className="section-title"><h3>Route analysis</h3><span className="route-phase">{report?.planning?'Calculating…':route?'Mission planned':local?'Terrain preview':'Awaiting destination'}</span></div>
    {report?.preview&&<div className="route-preview-choices">{[['safe','Slope weighted'],['short','Shortest']].map(([id,label])=><button key={id} disabled={!report.preview[id]} aria-pressed={previewKind===id} onClick={()=>onPreviewKind(id)}><i style={{background:id==='safe'?'#4BC3A2':'#E97845'}}/>{label}</button>)}</div>}
    <label className="route-visibility"><input type="checkbox" checked={settings.showRoutes} onChange={e=>onSettings({...settings,showRoutes:e.target.checked})}/>Show routes on terrain</label>
    <dl className="route-analysis-data"><div><dt>Terrain preview distance</dt><dd>{number(local?.distance/1000,2)} km</dd></div><div><dt>Terrain ascent</dt><dd>{number(local?.ascent)} m</dd></div><div><dt>Maximum path slope</dt><dd>{number(local?.maxSlope,1)}°</dd></div><div><dt>Mission distance</dt><dd>{number(route?.budget?.distance_m/1000,2)} km</dd></div><div><dt>Estimated duration</dt><dd>{number(route?.budget?.duration_min)} min</dd></div><div><dt>Mission risk score</dt><dd>{Number.isFinite(risk)?number(risk,2):'Not supplied'}</dd></div><div><dt>Estimated O₂ used</dt><dd>{number(oxygenUsed,1)}%</dd></div><div><dt>O₂ on return</dt><dd>{number(budget?.o2_end_pct,1)}%</dd></div></dl>
    {report?.error&&<p className="error" role="alert">{report.error}</p>}<p className="route-preview-note">Local routes compare source terrain only. Oxygen, travel time and mission validity come from the backend plan.</p><button className="button primary full" disabled={disabled} onClick={onPlan}><Icon name="plus" size={15}/>Plan Mission Route</button>
  </section>;
}
