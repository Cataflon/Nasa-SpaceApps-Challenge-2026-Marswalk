import Icon from './Icon';
import { number } from '../utils';

export default function MissionMetrics({ live }) {
  const readings = [
    ['O₂ disponibil', live.tick?.sensors?.o2_pct, '%', 'shield', 'Rezervă curentă'],
    ['Până la apus', live.tick ? live.tick.budget?.sunset_min - live.tick.t_min : null, 'min', 'compass', 'Fereastră de lumină'],
    ['Doză acumulată', live.tick?.sensors?.dose_total_msv, 'mSv', 'activity', 'Expunere în misiune'],
    ['Vânt', live.tick?.sensors?.wind_ms, 'm/s', 'wind', 'Mediul exterior'],
  ];
  return <section className="mission-metrics" aria-label="Senzori principali">
    {readings.map(([label, value, unit, icon, description]) => <div className="metric-card" key={label}>
      <div><span className="metric-label">{label}</span><strong>{number(value, 2)}<small>{unit}</small></strong><span className="metric-description">{Number.isFinite(value) ? description : 'În așteptarea datelor'}</span></div>
      <span className="metric-icon"><Icon name={icon} size={21}/></span>
    </div>)}
  </section>;
}
