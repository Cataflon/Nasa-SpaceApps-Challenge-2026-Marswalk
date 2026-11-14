// Audit: teste `node --test` pentru funcțiile pure din frontend, fără dependențe noi și fără DOM.
// Rulare din rădăcina repo-ului:  node --test frontend/tests
// Oracole: shared/contracts (exemplele ca intrare), convenția de coordonate (row spre sud, col spre est),
// geometrie calculată independent. client.js și useMission.js nu se pot importa fără Vite/React (vezi raportul).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { routeFrame, bearingTo, distanceTo } from '../src/terrain/navigation.js';
import { decisions, events, violation, number } from '../src/utils.js';
import { modules, equipmentReading } from '../src/sensors/equipment.js';

const contract = name => JSON.parse(readFileSync(fileURLToPath(new URL(`../../shared/contracts/${name}`, import.meta.url)), 'utf8'));

test('bearingTo: nord = 0°, est = 90°, sud = 180°, vest = 270° (row crește spre sud)', () => {
  const o = { row: 10, col: 10 };
  assert.equal(bearingTo(o, { row: 5, col: 10 }), 0);
  assert.equal(bearingTo(o, { row: 10, col: 15 }), 90);
  assert.equal(bearingTo(o, { row: 15, col: 10 }), 180);
  assert.equal(bearingTo(o, { row: 10, col: 5 }), 270);
  assert.equal(bearingTo(o, o), null);
  assert.equal(bearingTo(o, { row: NaN, col: 1 }), null);
});

test('distanceTo: celule × cell_size_m (20 m, contract site.json); valori invalide -> null', () => {
  const cell = contract('site.json').cell_size_m;
  assert.equal(distanceTo({ row: 0, col: 0 }, { row: 3, col: 4 }, cell), 5 * cell);
  assert.equal(distanceTo({ row: 0, col: 0 }, { row: 3, col: 4 }, 0), null);
});

test('routeFrame pe traseul din route_response.json: lungimea totală = suma segmentelor, capetele corecte', () => {
  const path = contract('route_response.json').path;
  let total = 0;
  for (let i = 1; i < path.length; i++) total += Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]);
  const start = routeFrame(path, 0), end = routeFrame(path, 1);
  assert.ok(Math.abs(start.total - total) < 1e-9);
  assert.deepEqual([start.eye.row, start.eye.col], path[0]);
  assert.deepEqual([end.eye.row, end.eye.col], path.at(-1));
  assert.ok(Math.abs(end.remaining) < 1e-9);
});

test('routeFrame: poziția astronautului (tick.astronaut) e proiectată pe traseu; trasee degenerate -> null', () => {
  const path = [[0, 0], [0, 10]];
  const f = routeFrame(path, 0, { row: 3, col: 4 });
  assert.ok(Math.abs(f.distance - 4) < 1e-9);
  assert.equal(f.heading, 90);
  assert.equal(routeFrame([[1, 1]]), null);
  assert.equal(routeFrame([[1, 1], [1, 1]]), null);
  assert.equal(routeFrame(null), null);
});

test('utils: decizii și evenimente = enumurile din contracte; fiecare cod de încălcare are etichetă', () => {
  assert.deepEqual(new Set(Object.keys(decisions)), new Set(['CONTINUE', 'REROUTE', 'WAIT', 'RETURN', 'EMERGENCY']));
  assert.deepEqual(new Set(Object.keys(events)), new Set(contract('live_event.json')._allowed_events));
  for (const code of ['O2_RESERVE', 'DAYLIGHT', 'SLOPE', 'DOSE', 'HAZARD']) assert.notEqual(violation(code), code);
  assert.equal(number(NaN), '—');
});

test('equipment: canalele senzorilor există în tick-ul din contract și se citesc ca valori plauzibile', () => {
  const tick = contract('live_messages.json')[0];
  for (const m of modules) {
    assert.ok(m.key in tick.sensors, `${m.key} lipsește din tick.sensors`);
    const r = equipmentReading(m, tick, 'live');
    assert.equal(r.value, tick.sensors[m.key]);
    assert.equal(r.valid, true);
  }
  const lost = equipmentReading(modules[0], tick, 'offline');
  assert.equal(lost.state, 'warning');
  assert.equal(equipmentReading(modules[0], null, 'live').state, 'waiting');
});
