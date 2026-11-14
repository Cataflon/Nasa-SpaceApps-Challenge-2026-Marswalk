import { number } from '../utils';
export default function BudgetPanel({ route, tick }) {
  const b = tick?.budget ?? route?.budget, o2 = b?.o2_end_pct;
  const profile = route?.elevation_profile ?? [];
  const min = Math.min(...profile.map(p => p.elevation_m)), max = Math.max(...profile.map(p => p.elevation_m));
  const distance = Math.max(1, ...profile.map(p => p.distance_m));
  const path = profile.map(p => `${12 + p.distance_m / distance * 256},${65 - (p.elevation_m - min) / Math.max(1, max - min) * 45}`).join(' ');
  return <section className="budget-section"><div className="section-title"><h3>Bugetul misiunii</h3>{route && <span className={`verdict ${route.verdict}`}>{route.verdict}</span>}</div>
    <div className="budget-primary"><span>O₂ estimat la întoarcere</span><strong>{number(o2, 1)}<small>%</small></strong></div><div className="meter"><span style={{ width: `${Math.max(0, Math.min(100, o2 ?? 0))}%` }}/></div>
    <dl className="data-list"><div><dt>Distanță planificată</dt><dd>{number(route?.budget?.distance_m / 1000, 1)} km</dd></div><div><dt>Durată planificată</dt><dd>{number(route?.budget?.duration_min)} min</dd></div><div><dt>Întoarcere până la</dt><dd>t+{number(b?.return_by_min)} min</dd></div><div><dt>Apus</dt><dd>t+{number(b?.sunset_min)} min</dd></div><div><dt>Doză planificată</dt><dd>{number(route?.budget?.dose_msv, 2)} mSv</dd></div></dl>
    {profile.length > 1 && <details className="altitude"><summary>Profil de altitudine</summary><svg viewBox="0 0 280 88" role="img" aria-label={`Altitudine între ${min} și ${max} metri pe ${distance} metri de traseu`}><polyline points={path} fill="none" stroke="var(--accent)" strokeWidth="2"/><text x="12" y="85">0 km</text><text x="225" y="85">{number(distance / 1000, 1)} km</text></svg><p className="small muted">{number(min)} → {number(max)} m altitudine</p></details>}
  </section>;
}
