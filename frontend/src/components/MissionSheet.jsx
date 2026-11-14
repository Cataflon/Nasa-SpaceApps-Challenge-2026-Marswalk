import BudgetPanel from './BudgetPanel';
import RouteAnalysisPanel from './RouteAnalysisPanel';
import DecisionPanel from './DecisionPanel';
import Planner from './Planner';
import { Chat } from './Information';
import Icon from './Icon';
import { number } from '../utils';
export default function MissionSheet({site,route,live,planner,planning,setPlanning,selected,onSelect,chat,setChat,mock,terrainReport,previewKind,onPreviewKind,terrainSettings,onTerrainSettings,onFocus}){
  const budget={...route?.budget,...live.tick?.budget},minutes=budget.return_by_min,hours=(site.eva_start_ltst_h??8)+(minutes??0)/61.65;
  const clock=Number.isFinite(minutes)?`${String(Math.floor(hours)%24).padStart(2,'0')}:${String(Math.floor(hours%1*60)).padStart(2,'0')}`:'—:—';
  const remaining=Number.isFinite(minutes)?minutes-(live.tick?.t_min??0):null;
  return <aside className="mission-sidebar field-sheet">
    <div className="sheet-registration"><span>Mission overview</span><Icon name="compass" size={17}/></div>
    <section className={`return-window ${remaining!==null&&remaining<30?'urgent':''}`}><div className="return-label"><span>Return to habitat by</span><Icon name="shield" size={16}/></div><strong>{clock}<small>LTST</small></strong><p>{Number.isFinite(remaining)?`${number(remaining)} min remaining in the return window`:'Generate an EVA plan to set the return window.'}</p></section>
    {planning?<Planner initialTargetId={selected?.id} site={site} planner={planner} live={live} onClose={()=>setPlanning(false)}/>:<>
      <details open className="explorer-fold science-fold"><summary>Science targets</summary><section className="stops-section"><div className="section-title"><h3>Science targets</h3><span className="small muted">{site.targets.length} sites</span></div>
        {site.targets.map((target,i)=><button key={target.id} className={`stop-row ${selected?.id===target.id?'selected':''}`} aria-pressed={selected?.id===target.id} onClick={()=>onSelect(selected?.id===target.id?null:target)}><span className="stop-number"><Icon name={target.kind==='clay'?'layers':target.kind==='carbonate'?'target':'compass'} size={14}/>{String(i+1).padStart(2,'0')}</span><span><strong>{target.name.split(',')[0]}</strong><small>{target.name.split(',').slice(1).join(',').trim()||target.kind} · {target.dwell_min} min</small></span><Icon name="chevron" size={13}/></button>)}
        {selected&&<div className="target-details"><h4>{selected.name}</h4>{selected.image&&<img src={selected.image} alt={selected.name} onError={e=>{e.target.hidden=true;}}/>}
          <dl className="selected-target-data"><div><dt>Grid row / column</dt><dd>{selected.row} / {selected.col}</dd></div>{Number.isFinite(selected.lat)&&Number.isFinite(selected.lon)&&<div><dt>Latitude / longitude</dt><dd>{selected.lat}° / {selected.lon}°</dd></div>}<div><dt>CTX source elevation</dt><dd>{number(terrainReport?.selectedElevation,1)} m</dd></div></dl>
          {selected.note&&<p className="small muted">{selected.note}</p>}{selected.source&&<p className="small muted">Source: {selected.source}</p>}{selected.id==='habitat'&&<p className="small muted">Concept inspired by Mars Dune Alpha. Enlarged 12× for map readability; footprint is not at terrain scale.</p>}
          <div className="target-actions"><button className="button secondary" onClick={()=>onFocus(selected)}><Icon name="target" size={14}/>Focus camera</button>{site.targets.some(t=>t.id===selected.id)&&<button className="button secondary" disabled={live.state!=='idle'} onClick={()=>setPlanning(true)}>Plan to target</button>}</div>
        </div>}
      </section></details>
      <section className="sheet-traverse"><div className="traverse-stop"><span className="origin-symbol"/><div><small>From</small><strong>Jezero habitat</strong></div></div><div className="traverse-connector"/><div className="traverse-stop"><span className="destination-symbol"/><div><small>Destination</small><strong>{selected?.name??(route?.stops?.length?site.targets.find(t=>t.id===route.stops[0].id)?.name:'Select on terrain')}</strong></div></div></section>
      <RouteAnalysisPanel report={terrainReport} route={route} live={live} previewKind={previewKind} onPreviewKind={onPreviewKind} settings={terrainSettings} onSettings={onTerrainSettings} onPlan={()=>setPlanning(true)} disabled={live.state!=='idle'}/>
      <DecisionPanel live={live} route={route}/><BudgetPanel route={route} tick={live.tick}/>
      <button className="chat-toggle" aria-expanded={chat} onClick={()=>setChat(!chat)}><Icon name="chat" size={16}/>Contact copilot<Icon name="chevron" size={14}/></button>{chat&&<Chat mock={mock} onRoute={planner.setResult} disabled={live.state!=='idle'}/>}
    </>}
    <div className="sheet-footnote">{mock?'Recorded scenario / not an operational flight plan':'Mission data supplied by the planning service'}</div>
  </aside>;
}
