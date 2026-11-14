export const number = (value, digits = 0) => Number.isFinite(value) ? new Intl.NumberFormat('ro-RO', { maximumFractionDigits: digits }).format(value) : '—';
export const decisions = { CONTINUE: 'Continuă traseul', REROUTE: 'Urmează ocolirea', WAIT: 'Așteaptă', RETURN: 'Revino la habitat', EMERGENCY: 'Urgență' };
export const alternatives = { detour_north: 'Ocolire nord', detour_south: 'Ocolire sud', detour_east: 'Ocolire est', detour_west: 'Ocolire vest', wait: 'Așteptare', return: 'Întoarcere', exit_zone: 'Ieșire din zonă', current: 'Traseu curent' };
export const events = { local_storm: 'Furtună locală', regional_storm: 'Furtună regională', solar_particle_event: 'Furtună solară', suit_leak: 'Scurgere costum', fatigue: 'Oboseală', dust_devil: 'Vârtej de praf', marsquake: 'Cutremur' };
export const violation = code => ({ O2_RESERVE: 'Rezervă O₂ insuficientă', DAYLIGHT: 'Întoarcere după apus', SLOPE: 'Pantă prea mare', DOSE: 'Doză prea mare', HAZARD: 'Pericol pe traseu' }[code] ?? code);

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
