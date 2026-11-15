export const number = (value, digits = 0) => Number.isFinite(value) ? new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(value) : '—';
export const decisions = { CONTINUE: 'Continue on route', REROUTE: 'Take the detour', WAIT: 'Wait', RETURN: 'Return to habitat', EMERGENCY: 'Emergency' };
export const alternatives = { detour_north: 'North detour', detour_south: 'South detour', detour_east: 'East detour', detour_west: 'West detour', detour_free: 'Direct detour', wait: 'Wait in place', step_back: 'Step back & wait', return: 'Return to habitat', exit_zone: 'Exit the zone', replan_stops: 'Skip a blocked stop', shelter: 'Shelter', current: 'Current route' };
export const events = { local_storm: 'Local dust storm', regional_storm: 'Regional dust storm', solar_particle_event: 'Solar particle event', suit_leak: 'Suit leak', fatigue: 'Fatigue', dust_devil: 'Dust devil', marsquake: 'Marsquake', egress_complete: 'Back at the habitat', o2_depleted: 'O₂ depleted', time_limit: 'Time limit reached' };
export const violation = code => ({ O2_RESERVE: 'O₂ below reserve', DAYLIGHT: 'Back after sunset', SLOPE: 'Slope too steep', DOSE: 'Dose too high', HAZARD: 'Crosses the hazard', NO_RETURN_POINT: 'Past the point of no return', OFF_MAP: 'Leaves the map', NO_SHELTER: 'No usable shelter' }[code] ?? code);

// Punctul de neîntoarcere poate fi `null` în route_response: nici de la start O₂-ul nu ajunge pentru
// drumul spre casă cu rezerva. Atunci planul nu are întoarcere sigură: verdictul afișat e NO-GO și pe
// hartă nu apare niciun marcaj. Doar `null` explicit înseamnă asta (un câmp lipsă nu).
export const hasSafeReturn = route => !route || route.point_of_no_return !== null;
export const effectiveVerdict = route => !route ? null : hasSafeReturn(route) ? route.verdict : 'NO-GO';
export const pointOfNoReturnLabel = route => {
  if (!route) return '—';
  if (!hasSafeReturn(route)) return 'No safe return';
  const t = route.point_of_no_return?.t_min;
  return Number.isFinite(t) ? `t+${number(t)} min` : '—';
};
export const pointOfNoReturnCell = route => {
  const p = route?.point_of_no_return;
  return p && Number.isFinite(p.row) && Number.isFinite(p.col) ? p : null;
};

// Alternative.path = traseul rămas COMPLET, de la poziția curentă până la habitat (la wait, doar
// [position]). Pentru desen: porțiunea până la ultima oprire (o țintă din sit) și întoarcerea de după
// ea, ca a doua să poată avea altă culoare. Punctul de la ultima oprire apare în ambele părți.
export function splitAtLastStop(path, targets) {
  if (!Array.isArray(path) || path.length < 2) return [Array.isArray(path) ? path : [], []];
  const cells = new Set((targets ?? []).map(t => `${t.row},${t.col}`));
  let last = -1;
  path.forEach((p, i) => { if (cells.has(`${p[0]},${p[1]}`)) last = i; });
  if (last <= 0 || last >= path.length - 1) return [path, []];
  return [path.slice(0, last + 1), path.slice(last)];
}
