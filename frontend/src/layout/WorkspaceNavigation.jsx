import {useLayoutEffect,useRef,useState} from 'react';
import {NavLink,useLocation} from 'react-router-dom';
import Icon from '../components/Icon';
// `id` is the name the stylesheets know each page by (`view-mission`, ...).
export const pages=[{id:'mission',path:'/planning',icon:'map',label:'Planning'},{id:'simulation',path:'/simulation',icon:'compass',label:'Simulation'},{id:'sensors',path:'/sensors',icon:'activity',label:'Sensors'}];
export default function WorkspaceNavigation({page,mock,offline,site,collapsed,onToggle}) {
  // A single highlight slides between the tabs: it is measured from the current link, so it follows
  // the vertical sidebar, the collapsed sidebar and the horizontal mobile bar alike.
  const nav=useRef(null),[pill,setPill]=useState(null),{pathname}=useLocation();
  useLayoutEffect(()=>{const node=nav.current;if(!node)return;const measure=()=>{const link=node.querySelector('.field-tab.current');setPill(link?{transform:`translate(${link.offsetLeft}px,${link.offsetTop}px)`,width:link.offsetWidth,height:link.offsetHeight}:null);};measure();const observer=new ResizeObserver(measure);observer.observe(node);return()=>observer.disconnect();},[pathname]);
  return <>
    <header className="field-masthead">
      <NavLink className="field-wordmark" to="/planning"><img className="app-brand-logo" src="/images/marswalk_logo_512.png" alt="Marswalk" width="512" height="262"/></NavLink>
      <button className="nav-collapse" onClick={onToggle} aria-label={collapsed?'Expand sidebar':'Collapse sidebar'} aria-expanded={!collapsed} title={collapsed?'Expand sidebar':'Collapse sidebar'}><Icon name="chevron" size={15}/></button>
      <nav aria-label="Application views" ref={nav}>{pill&&<i className="nav-pill" style={pill} aria-hidden="true"/>}{pages.map(p=><NavLink key={p.id} to={p.path} aria-label={p.label} title={p.label} className={({isActive})=>`field-tab ${isActive?'current':''}`}><Icon name={p.icon} size={18}/><span>{p.label}</span></NavLink>)}</nav>
      <div className="field-link-status"><i className={offline?'offline':''}/><span>{offline?'Connection interrupted':mock?'Demo data':'Connected'}</span></div>
    </header>
    <div className="field-context"><div><span>Jezero</span><span className="context-divider">/</span><b key={page.id} className="context-page">{page.label}</b></div><span className="field-coordinates">{Number.isFinite(site?.center?.lat)?site.center.lat.toFixed(2):'—'}° N · {Number.isFinite(site?.center?.lon)?site.center.lon.toFixed(2):'—'}° E</span></div>
  </>;
}
