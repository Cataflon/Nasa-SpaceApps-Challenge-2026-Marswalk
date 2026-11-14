import Icon from './Icon';

export const pages = [
  ['mission', 'map', 'Misiune'],
  ['navigation', 'compass', 'Navigare'],
  ['sensors', 'activity', 'Senzori'],
  ['information', 'book', 'Cum calculăm'],
];

export default function WorkspaceNavigation({ page, onNavigate, mock, offline }) {
  return <>
    <aside className="workspace-navigation">
      <a className="brand" href="#mission" onClick={event => { event.preventDefault(); onNavigate('mission'); }} aria-label="Marswalk, centrul de misiune">
        <span className="brand-symbol"><Icon name="compass" size={25}/></span>
        <span>Marswalk<small>Explorare asistată</small></span>
      </a>
      <div className="navigation-divider"/>
      <p className="navigation-label">Spațiul de lucru</p>
      <nav aria-label="Navigare principală">
        {pages.map(([id, icon, label]) => <button key={id} className={page === id ? 'nav-item selected' : 'nav-item'} aria-current={page === id ? 'page' : undefined} onClick={() => onNavigate(id)}>
          <span className="nav-icon"><Icon name={icon} size={18}/></span><span>{label}</span>
        </button>)}
      </nav>
      <div className="sidebar-mission">
        <span className="sidebar-mission-icon"><Icon name="shield" size={22}/></span>
        <h3>Explorăm Jezero</h3>
        <p>Traseul, condițiile și întoarcerea la habitat, într-un singur loc.</p>
        <button className="button secondary full" onClick={() => onNavigate('information')}>Despre misiune<Icon name="chevron" size={15}/></button>
      </div>
      <div className="sidebar-footer"><span className={`connection-dot ${offline ? 'offline' : ''}`}/><span>{offline ? 'Conexiune întreruptă' : mock ? 'Date demonstrative' : 'Date API'}</span></div>
    </aside>
    <header className="workspace-bar">
      <div><p className="breadcrumb">Marswalk <span>/</span> {pages.find(([id]) => id === page)?.[2]}</p><span className="workspace-title">Jezero / Expediția 01</span></div>
      <div className="header-status"><span className={`connection-dot ${offline ? 'offline' : ''}`}/><span>{offline ? 'Offline' : mock ? 'Date mock' : 'Date API'}</span><span className="mission-id">EVA / 01</span></div>
    </header>
  </>;
}
