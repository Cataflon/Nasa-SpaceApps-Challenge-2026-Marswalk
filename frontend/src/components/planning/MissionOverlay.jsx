import Icon from '../Icon';
import {effectiveVerdict,number,pointOfNoReturnLabel} from '../../utils';
// Translucent mission card on the left of the planning map: stops, live estimate from the backend,
// compact settings and the way into the simulation. Appears once the trip has a stop.
const MARS_HOUR_MIN=61.65;
function clock(site,minutes){
  if(!Number.isFinite(minutes))return '—';
  const hours=(site.eva_start_ltst_h??8)+minutes/MARS_HOUR_MIN;
  return `${String(Math.floor(hours)%24).padStart(2,'0')}:${String(Math.floor(hours%1*60)).padStart(2,'0')}`;
}
export default function MissionOverlay({site,points,trip,route,mock,estimate,settings,onSettings,locked,busy,onEndEva,onSelect,onSimulate}){
  if(!trip.ids.length)return <aside className="mission-overlay mission-overlay-hint" aria-label="How to plan"><Icon name="target" size={15}/><p>Click a science site or anywhere on the terrain, then press <strong>Add to trip</strong>. The mission estimate appears here.</p></aside>;
  const all=[...site.targets,...points],byId=id=>all.find(p=>p.id===id);
  const visit=Object.fromEntries((route?.stops??[]).map((s,i)=>[s.id,s.visit_order??i+1]));
  const omitted=new Set(route?.omitted??[]);
  // Ordinea în care planificatorul le vizitează; cele încă neplanificate sau omise rămân la final.
  const ordered=[...trip.ids].sort((a,b)=>(visit[a]??Infinity)-(visit[b]??Infinity));
  const verdict=route&&!mock?effectiveVerdict(route):null,b=route?.budget;
  const status=estimate.busy?'Estimating…':estimate.error?'Not available':verdict??(mock?'Demo data':'—');
  const o2=b?.o2_end_pct;
  const blocked=!route||mock||verdict==='NO-GO'||estimate.busy||!!estimate.error;
  return <aside className="mission-overlay" aria-label="Mission estimate">
    <header className="mo-head"><h3>Mission</h3><span className={`mo-status verdict ${verdict??''}`} role="status">{status}</span></header>
    <ol className="mo-stops">
      <li className="mo-end"><i/>Habitat</li>
      {ordered.map(id=>{const p=byId(id);return <li key={id} className={omitted.has(id)?'omitted':''}>
        <span className="mo-order">{visit[id]??'·'}</span>
        <button className="mo-name" onClick={()=>p&&onSelect(p)} title={p?.name}>{p?.name.split(',')[0]??id}<small>{omitted.has(id)?'Skipped: does not fit the budget':site.targets.some(t=>t.id===id)?'Science site':'Your waypoint'}</small></button>
        <button className="mo-remove" aria-label={`Remove ${p?.name??id}`} disabled={locked} onClick={()=>trip.setIds(trip.ids.filter(x=>x!==id))}><Icon name="close" size={11}/></button>
      </li>;})}
      {trip.returnHome&&<li className="mo-end"><i/>Back to habitat</li>}
    </ol>
    {estimate.error&&<p className="mo-error" role="alert">{estimate.error}</p>}
    {route&&!estimate.error&&<>
      <div className="mo-o2"><span>O₂ on return</span><strong>{number(o2,1)}<small>%</small></strong></div>
      <div className="meter"><span style={{width:`${Math.max(0,Math.min(100,o2??0))}%`}}/></div>
      <dl className="mo-budget">
        <div><dt>Distance</dt><dd>{number(b?.distance_m/1000,1)} km</dd></div>
        <div><dt>Duration</dt><dd>{number(b?.duration_min)} min</dd></div>
        <div><dt>Return by</dt><dd>{clock(site,b?.return_by_min)} <small>LTST</small></dd></div>
        <div><dt>No-return point</dt><dd>{pointOfNoReturnLabel(route)}</dd></div>
        <div><dt>Dose</dt><dd>{number(b?.dose_msv,2)} mSv</dd></div>
      </dl>
      {route.stops?.length>1&&<p className="mo-note">Stops are listed in the order the planner visits them.</p>}
    </>}
    <details className="mo-settings"><summary>Settings</summary>
      <label>Priority<select value={settings.preset} disabled={locked} onChange={e=>onSettings({...settings,preset:e.target.value})}><option value="safe">Safety</option><option value="fast">Minimum time</option><option value="science">Science value</option></select></label>
      <label>Max duration (min)<input type="number" min="30" max="720" step="10" value={settings.duration} disabled={locked} onChange={e=>onSettings({...settings,duration:Math.max(30,Math.min(720,Number(e.target.value)||300))})}/></label>
      <label className="mo-check"><input type="checkbox" checked={trip.returnHome} disabled={locked} onChange={e=>trip.setReturnHome(e.target.checked)}/>Return to habitat</label>
    </details>
    {locked?<><button className="button secondary full" disabled={busy} onClick={onEndEva}><Icon name="reset" size={14}/>End EVA &amp; edit plan</button><p className="mo-note">An EVA is in progress. End it to change the plan.</p></>
      :<button className="button primary full" disabled={blocked} onClick={onSimulate}><Icon name="play" size={14}/>Start simulation</button>}
    {!locked&&verdict==='NO-GO'&&<p className="mo-note">NO-GO: the plan breaks a safety limit. Remove a stop or change the settings.</p>}
  </aside>;
}
