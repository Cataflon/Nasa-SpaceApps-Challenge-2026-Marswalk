import { lazy, Suspense, useEffect, useState } from 'react';
const TerrainView=lazy(()=>import('./TerrainView'));
export default function MapView({site,route,live,position,selected,onSelect,onRoutePreview,compact=false,mapTitle="Mission Terrain Explorer",...explorerProps}){
  const [expanded,setExpanded]=useState(false);
  useEffect(()=>{if(!expanded)return;const previous=document.body.style.overflow;document.body.style.overflow='hidden';const close=e=>{if(e.key==='Escape')setExpanded(false);};window.addEventListener('keydown',close);return()=>{document.body.style.overflow=previous;window.removeEventListener('keydown',close);};},[expanded]);
  return <section className={`map-stage is-3d ${compact?'compact':''} ${expanded?'map-expanded':''}`} aria-label="Mission Terrain Explorer"><div className="map-heading"><div><span className="eyebrow">Jezero / Surface exploration</span><h2>{mapTitle}</h2></div></div><Suspense fallback={<p className="terrain-message terrain-loading">Loading the 3D viewport…</p>}><TerrainView site={site} route={route} live={live} position={position} selected={selected} onSelect={onSelect} onRoutePreview={onRoutePreview} compact={compact} {...explorerProps} expanded={expanded} onExpand={()=>setExpanded(value=>!value)}/></Suspense></section>;
}
