import BudgetPanel from './BudgetPanel';
import LayerSources from './LayerSources';
import DecisionPanel from './DecisionPanel';
import Planner from './Planner';
import { Chat } from './Information';
import Icon from './Icon';
import { number } from '../utils';

export default function MissionSheet({site,route,live,planner,planning,setPlanning,selected,onSelect,chat,setChat,mock}) {
  const budget={...route?.budget,...live.tick?.budget};
  const minutes=budget.return_by_min;
  const hours=(site.eva_start_ltst_h??8)+(minutes??0)/61.65;
  const clock=Number.isFinite(minutes)?`${String(Math.floor(hours)%24).padStart(2,'0')}:${String(Math.floor(hours%1*60)).padStart(2,'0')}`:'—:—';
  const remaining=Number.isFinite(minutes)?minutes-(live.tick?.t_min??0):null;
  return <aside className="mission-sidebar field-sheet">
    <div className="sheet-registration"><span>Mission overview</span><Icon name="compass" size={17}/></div>
    <section className={`return-window ${remaining!==null&&remaining<30?'urgent':''}`}><div className="return-label"><span>Return to habitat by</span><Icon name="shield" size={16}/></div><strong>{clock}<small>LTST</small></strong><p>{Number.isFinite(remaining)?`${number(remaining)} min remaining in the return window`:'Generate an EVA plan to set the return window.'}</p></section>
    <section className="sheet-traverse"><div className="traverse-stop"><span className="origin-symbol"/><div><small>From</small><strong>Jezero habitat</strong></div></div><div className="traverse-connector"/><div className="traverse-stop"><span className="destination-symbol"/><div><small>Destination</small><strong>{selected?.name??(route?.stops?.length?site.targets.find(t=>t.id===route.stops[0].id)?.name:'Select on terrain')}</strong></div></div></section>
    {planning?<Planner site={site} planner={planner} live={live} onClose={()=>setPlanning(false)}/>:<><div className="sheet-primary"><button className="button primary full" onClick={()=>setPlanning(true)} disabled={live.state!=='idle'}><Icon name="plus" size={16}/>{route?'Edit EVA plan':'Plan EVA'}</button></div><DecisionPanel live={live} route={route}/><BudgetPanel route={route} tick={live.tick}/><section className="stops-section"><div className="section-title"><h3>Science objectives</h3><span className="small muted">{site.targets.length} sites</span></div>{site.targets.map((t,i)=><button key={t.id} className={`stop-row ${selected?.id===t.id?'selected':''}`} onClick={()=>onSelect(selected?.id===t.id?null:t)}><span className="stop-number">{String(i+1).padStart(2,'0')}</span><span><strong>{t.name.split(',')[0]}</strong><small>{t.name.split(',').slice(1).join(',').trim()} / {t.dwell_min} min</small></span><Icon name="chevron" size={13}/></button>)}{selected&&<div className="target-details"><h4>{selected.name}</h4>{selected.image?<img src={selected.image} alt={selected.name} onError={e=>{e.target.hidden=true;}}/>:null}<p className="small">Grid {selected.row} / {selected.col} · science {selected.science_value??'—'}</p></div>}</section><button className="chat-toggle" aria-expanded={chat} onClick={()=>setChat(!chat)}><Icon name="chat" size={16}/>Contact copilot<Icon name="chevron" size={14}/></button>{chat&&<Chat mock={mock} onRoute={planner.setResult} disabled={live.state!=='idle'}/>}</>}
    <LayerSources site={site}/>
    <div className="sheet-footnote">{mock?'Recorded scenario / not an operational flight plan':'Mission data supplied by the planning service'}</div>
  </aside>;
}
