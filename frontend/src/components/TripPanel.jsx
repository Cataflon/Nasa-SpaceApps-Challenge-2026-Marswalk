import Icon from './Icon';
// Compact itinerary under the map. Stops are added from the map popup; the route rebuilds on every change.
export default function TripPanel({stops,trip,onSelect,onPreview,running}){
  const byId=id=>stops.find(p=>p.id===id);
  function move(index,delta){const ids=[...trip.ids],target=index+delta;if(target<0||target>=ids.length)return;[ids[index],ids[target]]=[ids[target],ids[index]];trip.setIds(ids);}
  return <section id="waypoint-editor" className="planning-card trip-panel" aria-label="Trip itinerary">
    <div className="trip-panel-head"><h3><Icon name="target" size={15}/>Your trip</h3><span className="trip-status" role="status">{trip.busy?'Routing…':trip.error?'':trip.result?`${(trip.result.distance/1000).toFixed(2)} km · ${Math.round(trip.result.ascent)} m ascent`:trip.ids.length?'':'No stops yet'}</span></div>
    {trip.ids.length?<ol className="trip-chips"><li className="trip-end">Habitat</li>{trip.ids.map((id,index)=><li key={id} className="trip-chip"><span>{index+1}</span><button className="trip-chip-name" onClick={()=>onSelect(byId(id))}>{byId(id)?.name.split(',')[0]}</button><button aria-label={`Move stop ${index+1} earlier`} title="Move earlier" disabled={index===0} onClick={()=>move(index,-1)}><Icon className="arrow-left" name="chevron" size={12}/></button><button aria-label={`Move stop ${index+1} later`} title="Move later" disabled={index===trip.ids.length-1} onClick={()=>move(index,1)}><Icon name="chevron" size={12}/></button><button aria-label={`Remove stop ${index+1} from trip`} title="Remove from trip" onClick={()=>trip.setIds(trip.ids.filter(p=>p!==id))}><Icon name="close" size={12}/></button></li>)}{trip.returnHome&&<li className="trip-end">Habitat</li>}</ol>
    :<p className="trip-empty">Click anywhere on the map, name the point and press <strong>Add to trip</strong>. Science sites can be added the same way.</p>}
    <div className="trip-panel-foot"><label className="trip-return"><input type="checkbox" checked={trip.returnHome} onChange={e=>trip.setReturnHome(e.target.checked)}/>Return to habitat</label>{trip.ids.length>0&&<div className="trip-actions"><button className="button primary" disabled={!trip.result||running} onClick={onPreview}>Preview trip</button><button className="text-button" onClick={()=>trip.setIds([])}>Clear trip</button></div>}</div>
    {trip.error&&<p className="error" role="alert">{trip.error}</p>}{trip.result&&<p className="local-notes-caption">Local terrain routing. Oxygen, hazards and mission budgets are validated only for a generated mission route.</p>}
  </section>;
}
