import { useState } from 'react';
import MapView from './MapView';
import Icon from './Icon';
import { decisions, number } from '../utils';
export default function Navigator({ site, route, live, position, mock, selected, onSelect }) {
  const [watch, setWatch] = useState(false);
  const p = position ?? site.habitat, next = live.tick?.remaining_path?.find(([r, c]) => Math.hypot(r - p.row, c - p.col) > 1);
  const heading = next ? Math.atan2(next[1] - p.col, -(next[0] - p.row)) * 180 / Math.PI : null;
  const meters = next ? Math.hypot(next[0] - p.row, next[1] - p.col) * site.cell_size_m : null;
  return <div className="navigator-page"><div className="page-heading"><div><span className="eyebrow">În teren</span><h1>Navigatorul astronautului</h1></div><div className="segmented"><button aria-pressed={!watch} onClick={() => setWatch(false)}>Telefon</button><button aria-pressed={watch} onClick={() => setWatch(true)}>Ceas</button></div></div><div className={`device-preview ${watch ? 'watch-preview' : ''}`}>
    <section className={watch ? 'watch-device' : 'phone-device'} aria-label={watch ? 'Mod ceas' : 'Mod telefon'}><div className="device-top"><span>Marswalk</span><span>{mock ? 'Demo' : live.status === 'live' ? 'Conectat' : 'Offline'}</span></div><div className="navigation-instruction"><Icon name="arrow" size={watch ? 52 : 38} style={{ transform: `rotate(${heading ?? 0}deg)` }}/><div><strong>{number(meters)} <small>m</small></strong><p>{next ? 'Următorul segment' : 'Așteaptă poziția'}</p></div></div><p className="navigation-state">{decisions[live.decision?.decision] ?? (route ? 'Urmează traseul' : 'Planifică ieșirea')}</p>
    {!watch && <MapView site={site} route={route} live={live} position={position} mock={mock} selected={selected} onSelect={onSelect} compact/>}
    <div className="device-budget"><div><span>Oxigen</span><strong>{number(live.tick?.sensors?.o2_pct, 1)}%</strong></div><div><span>{watch ? 'Timp' : 'Până la apus'}</span><strong>{number(live.tick ? live.tick.budget?.sunset_min - live.tick.t_min : null)}<small> min</small></strong></div></div><p className="device-note">Nordul în sus{!watch && ' · direcția segmentului, fără busolă fizică'}</p></section>
    <div className="device-caption"><Icon name={watch ? 'watch' : 'compass'} size={28}/><h2>{watch ? 'Esențialul, dintr-o privire.' : 'Traseul, mereu la îndemână.'}</h2><p>{watch ? 'Direcția, rezerva de oxigen și decizia curentă, într-un ecran compact.' : 'Aceeași misiune, într-o vedere concentrată pe următorul pas.'}</p><span className="small muted">Mod compact desktop. Localizarea hardware urmează să fie integrată.</span></div>
  </div></div>;
}
