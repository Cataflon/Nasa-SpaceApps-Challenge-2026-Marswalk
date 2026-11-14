import { lazy, Suspense, useEffect, useState } from 'react';
import Icon from './Icon';
const TerrainView = lazy(() => import('./TerrainView'));
export default function MapView({ site, route, live, position, selected, onSelect, onRoutePreview, compact = false }) {
  const [expanded,setExpanded]=useState(false);
  useEffect(()=>{const listener=e=>{if(e.key==='Escape')setExpanded(false);};window.addEventListener('keydown',listener);return()=>window.removeEventListener('keydown',listener);},[]);
  return <section className={`map-stage is-3d ${compact?'compact':''} ${expanded?'map-expanded':''}`} aria-label="Harta 3D a misiunii"><div className="map-heading"><div><span className="eyebrow">Jezero / Explorare de suprafață</span><h2>{compact?'Navigator 3D':'Relieful misiunii'}</h2></div><button className="icon-button" onClick={()=>setExpanded(!expanded)} aria-label={expanded?'Închide harta extinsă':'Extinde harta'}><Icon name={expanded?'close':'expand'}/></button></div><Suspense fallback={<p className="terrain-message">Se încarcă vizualizarea 3D…</p>}><TerrainView site={site} route={route} live={live} position={position} selected={selected} onSelect={onSelect} onRoutePreview={onRoutePreview} compact={compact}/></Suspense></section>;
}
