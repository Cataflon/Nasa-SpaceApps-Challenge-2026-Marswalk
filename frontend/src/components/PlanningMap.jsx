import {useEffect,useRef,useState} from 'react';
import MapView from './MapView';
import Icon from './Icon';
export default function PlanningMap({children,onFloatingChange,...mapProps}){
  const anchor=useRef(null),[floating,setFloating]=useState(false),[dismissed,setDismissed]=useState(false);
  useEffect(()=>{const node=anchor.current;if(!node)return;const observer=new IntersectionObserver(([entry])=>{const away=!entry.isIntersecting&&entry.boundingClientRect.bottom<80;setFloating(away);if(entry.isIntersecting)setDismissed(false);},{threshold:0});observer.observe(node);return()=>observer.disconnect();},[]);
  useEffect(()=>{onFloatingChange?.(floating&&!dismissed);},[floating,dismissed,onFloatingChange]);
  useEffect(()=>()=>onFloatingChange?.(false),[onFloatingChange]);
  const back=()=>{setDismissed(false);anchor.current?.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});};
  return <><div className="planning-map-anchor" ref={anchor}><div className={`planning-map ${floating&&!dismissed?'is-pip':''}`}><div className="pip-heading"><span>Route overview</span><button onClick={back} aria-label="Return to full map" title="Return to full map"><Icon name="expand" size={14}/></button><button onClick={()=>setDismissed(true)} aria-label="Hide floating map"><Icon name="close" size={14}/></button></div><MapView {...mapProps} explorer/><button className="pip-return" onClick={back}>Back to map<Icon name="arrow" size={12}/></button></div></div>{floating&&dismissed&&<button className="restore-pip button secondary" onClick={()=>setDismissed(false)}><Icon name="map" size={14}/>Show route map</button>}{children}</>;
}
