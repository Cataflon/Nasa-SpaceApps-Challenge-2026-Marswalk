export const number = (value, digits = 0) => Number.isFinite(value) ? new Intl.NumberFormat('ro-RO', { maximumFractionDigits: digits }).format(value) : '—';
export const decisions = { CONTINUE: 'Continuă traseul', REROUTE: 'Urmează ocolirea', WAIT: 'Așteaptă', RETURN: 'Revino la habitat', EMERGENCY: 'Urgență' };
export const alternatives = { detour_north: 'Ocolire nord', detour_south: 'Ocolire sud', wait: 'Așteptare', return: 'Întoarcere', current: 'Traseu curent' };
export const events = { local_storm: 'Furtună locală', regional_storm: 'Furtună regională', solar_particle_event: 'Furtună solară', suit_leak: 'Scurgere costum', fatigue: 'Oboseală', dust_devil: 'Vârtej de praf', marsquake: 'Cutremur' };
export const violation = code => ({ O2_RESERVE: 'Rezervă O₂ insuficientă', DAYLIGHT: 'Întoarcere după apus', SLOPE: 'Pantă prea mare', DOSE: 'Doză prea mare', HAZARD: 'Pericol pe traseu' }[code] ?? code);
