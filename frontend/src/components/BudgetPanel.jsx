// Bugetul: O₂, timp, lumină, doză. TODO (rolul 4): profilul de altitudine din route.elevation_profile.
export default function BudgetPanel({ route, tick }) {
  const s = tick?.sensors;
  const b = route?.budget;
  return (
    <section className="panel">
      <h2>Buget {route && <span className={`verdict ${route.verdict}`}>{route.verdict}</span>}</h2>
      <dl className="grid">
        <dt>O₂ acum</dt><dd>{s ? `${s.o2_pct.toFixed(1)}%` : "–"}</dd>
        <dt>O₂ la sosire</dt><dd>{tick?.budget?.o2_end_pct ?? b?.o2_end_pct ?? "–"}%</dd>
        <dt>Întoarcere până la</dt><dd>t+{tick?.budget?.return_by_min ?? b?.return_by_min ?? "–"} min</dd>
        <dt>Apus</dt><dd>t+{tick?.budget?.sunset_min ?? b?.sunset_min ?? "–"} min</dd>
        <dt>Doză</dt><dd>{s ? `${s.dose_total_msv} mSv` : b ? `${b.dose_msv} mSv` : "–"}</dd>
        <dt>Praf (τ)</dt><dd>{s?.dust_tau ?? "–"}</dd>
        <dt>Vânt</dt><dd>{s ? `${s.wind_ms} m/s` : "–"}</dd>
      </dl>
    </section>
  );
}
