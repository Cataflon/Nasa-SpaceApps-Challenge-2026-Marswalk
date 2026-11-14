import Icon from './Icon';
const pages=[['mission','map','Mission'],['navigation','compass','Navigation'],['sensors','activity','Sensors'],['information','book','Reference']];
export default function WorkspaceNavigation({page,onNavigate,mock,offline,site}) {
  return <>
    <header className="field-masthead">
      <a className="field-wordmark" href="#mission" onClick={e=>{e.preventDefault();onNavigate('mission');}}><span className="field-insignia"><Icon name="compass" size={25}/></span><span>Marswalk<small>Jezero exploration</small></span></a>
      <nav aria-label="Application views">{pages.map(([id,icon,label])=><button key={id} className={`field-tab ${page===id?'current':''}`} onClick={()=>onNavigate(id)} aria-current={page===id?'page':undefined}><Icon name={icon} size={18}/><span>{label}</span></button>)}</nav>
      <div className="field-link-status"><i className={offline?'offline':''}/><span>{offline?'Connection interrupted':mock?'Demo data':'Connected'}</span></div>
    </header>
    <div className="field-context"><div><span>Jezero</span><span className="context-divider">/</span><b>{pages.find(([id])=>id===page)?.[2]}</b></div><span className="field-coordinates">{Number.isFinite(site?.center?.lat)?site.center.lat.toFixed(2):'—'}° N · {Number.isFinite(site?.center?.lon)?site.center.lon.toFixed(2):'—'}° E</span></div>
  </>;
}
