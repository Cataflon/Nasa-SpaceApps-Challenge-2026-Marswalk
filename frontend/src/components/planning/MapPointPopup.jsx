import {useEffect,useState} from 'react';
import Icon from '../Icon';
// Small menu anchored on the map at the selected location: name a new point and add it to the trip.
export default function MapPointPopup({selected,points,trip,onAdd,onDelete,onClose}){
  const [name,setName]=useState('');
  const isNew=selected?.kind==='custom',saved=points.some(p=>p.id===selected?.id),inTrip=trip.ids.includes(selected?.id);
  useEffect(()=>{setName(isNew?`Waypoint ${points.length+1}`:'');},[selected?.id]);
  if(!selected||selected.id==='habitat'||selected.id==='astronaut')return null;
  const toggle=()=>trip.setIds(inTrip?trip.ids.filter(id=>id!==selected.id):[...trip.ids,selected.id]);
  return <div className="map-popup-body"><button className="map-popup-close" aria-label="Close" onClick={onClose}><Icon name="close" size={12}/></button>
    {isNew?<><span className="map-popup-title">New waypoint</span><form onSubmit={e=>{e.preventDefault();if(name.trim())onAdd(name.trim());}}><input aria-label="Waypoint name" autoFocus maxLength="60" placeholder="Name this waypoint" value={name} onFocus={e=>e.target.select()} onChange={e=>setName(e.target.value)}/><button className="button primary" disabled={!name.trim()}><Icon name="plus" size={13}/>Add to trip</button></form></>
    :<><strong>{selected.name.split(',')[0]}</strong><small>{saved?'Saved waypoint':`Science site · ${selected.dwell_min} min on site`}</small><button className={`button ${inTrip?'secondary':'primary'}`} onClick={toggle}><Icon name={inTrip?'close':'plus'} size={13}/>{inTrip?'Remove from trip':'Add to trip'}</button>{saved&&<button className="map-popup-delete" onClick={onDelete}>Delete waypoint</button>}</>}
  </div>;
}
