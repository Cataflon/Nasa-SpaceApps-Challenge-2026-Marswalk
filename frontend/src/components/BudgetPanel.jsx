// Bugetul: O₂, timp, lumină, doză. TODO (rolul 4): profilul de altitudine din route.elevation_profile.
export default function BudgetPanel({ route, tick }) {
  const s = tick?.sensors;
  const b = route?.budget;
  return (
    <section className="panel">
      <h2>Budget {route && <span className={`verdict ${route.verdict}`}>{route.verdict}</span>}</h2>
      <dl className="grid">
        <dt>O₂ now</dt><dd>{s ? `${s.o2_pct.toFixed(1)}%` : "–"}</dd>
        <dt>O₂ on arrival</dt><dd>{tick?.budget?.o2_end_pct ?? b?.o2_end_pct ?? "–"}%</dd>
        <dt>Return by</dt><dd>t+{tick?.budget?.return_by_min ?? b?.return_by_min ?? "–"} min</dd>
        <dt>Sunset</dt><dd>t+{tick?.budget?.sunset_min ?? b?.sunset_min ?? "–"} min</dd>
        <dt>Dose</dt><dd>{s ? `${s.dose_total_msv} mSv` : b ? `${b.dose_msv} mSv` : "–"}</dd>
        <dt>Dust (τ)</dt><dd>{s?.dust_tau ?? "–"}</dd>
        <dt>Wind</dt><dd>{s ? `${s.wind_ms} m/s` : "–"}</dd>
      </dl>
    </section>
  );
}
