import {Suspense,useEffect,useState} from 'react';
import {Outlet,useLocation} from 'react-router-dom';
import {useMissionContext} from '../mission/MissionContext';
import WorkspaceNavigation,{pages} from './WorkspaceNavigation';
// Shell around every page: sidebar, connection banner, footer and the animated page slot.
export default function AppLayout(){
  const {siteResult,site,mock,offline,hasPip}=useMissionContext(),{pathname}=useLocation();
  const [navCollapsed,setNavCollapsed]=useState(()=>window.innerWidth<1200);
  const page=pages.find(p=>pathname.startsWith(p.path))??pages[0];
  useEffect(()=>{window.scrollTo({top:0,behavior:'instant'});},[page.path]);
  if(!site)return <div className="loading-screen"><img className="loading-brand-logo" src="/images/marswalk_logo_transparent.png" alt="Marswalk"/><p>{siteResult.error??'Loading expedition area…'}</p></div>;
  return <div className={`app expedition-shell workflow-shell ${hasPip?'has-pip':''} ${navCollapsed?'nav-collapsed':''} view-${page.id}`}>
    <WorkspaceNavigation collapsed={navCollapsed} onToggle={()=>setNavCollapsed(v=>!v)} page={page} mock={mock} offline={offline} site={site}/>
    {offline&&<div className="connection-banner" role="status">Live link interrupted. Last received data retained; position is held.</div>}
    <main className="workflow-main"><Suspense fallback={<p className="page-loading" role="status">Loading…</p>}><div className="page-transition" key={page.path}><Outlet/></div></Suspense></main>
    <footer className="app-footer"><span>Marswalk Copilot</span><span>{mock?'DEMONSTRATION DATA':'MISSION SERVICE'} · {site.cell_size_m} m planning grid</span><span>Jezero surface exploration</span></footer>
  </div>;
}
