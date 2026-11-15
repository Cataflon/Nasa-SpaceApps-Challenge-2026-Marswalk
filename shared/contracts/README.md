# Contracte

Formele JSON pe care le schimbă rolurile între ele. Se stabilesc în ora 0 și se modifică **doar cu acordul tuturor**.

Fișierele `.json` de aici sunt și **mock-uri**: frontendul le importă direct până e gata backendul, iar backendul le întoarce din rutele încă neimplementate.

| Fișier | Cine produce | Cine consumă | Ce e |
|---|---|---|---|
| `meta.json` | pipeline (rolul 1) | core (rolul 2), API | Descrierea sitului: grilă, habitat, ținte, straturi |
| `site.json` | `GET /api/site` | frontend | Ce vede frontendul despre sit |
| `route_request.json` | frontend | `POST /api/route` | Cererea de traseu |
| `route_response.json` | `POST /api/route` | frontend | Traseu + buget + verdict |
| `live_messages.json` | `WS /api/live` | frontend | Exemple pentru fiecare tip de mesaj live |
| `live_event.json` | frontend | `POST /api/live/event` | Injectarea unui eveniment |
| `live_control.json` | frontend | `POST /api/live/control` | Start / pauză / reset / viteza ceasului |
| `chat_stream.json` | `POST /api/chat` | frontend | Răspunsul de chat în streaming (NDJSON) |

Câmpul `image` din `targets` e opțional (`null` sau URL către imaginea Perseverance de la oprire).

> ## 🆕 Câmpuri noi, opționale (14.11.2026, vezi `README.md` → „🆕 Noutăți”)
> Încă nu sunt în fișierele `.json` de mai jos. Se adaugă în exemple de un om, cu acordul echipei. Consumatorii trebuie să le trateze ca **opționale**, cu fallback.
>
> | Unde | Câmp | Formă | Produs de | Folosit pentru |
> |---|---|---|---|---|
> | `site.json` | `eva_start_ltst_h` | `9.0` | rolul 3 (din `scenario.EVA_START_LTST_H`) | ceasul de întoarcere „Te întorci până la 14:20” |
> | `site.json` | `earth_delay_min` | `{"one_way": 14, "round_trip": 28, "source": "…"}` | rolul 3 (constante de la rolul 1) | contorul „Pământul vs. copilotul” |
> | `site.json` → `layers[]` | `mission`, `instrument`, `data_type`, `source`, `analog_of`, `product_id` | text | pipeline (rolul 1), trimise deja de `/api/site` | etichetele straturilor, popup-ul de la click |
> | `GET /api/point` | `sources` | `{"slope": {"mission": "MRO", "instrument": "HiRISE", "data_type": "topographic"}, …}` | rolul 3 | click pe hartă: „pantă 12° · HiRISE · MRO” |
> | `live_messages.json` → `decision` | `compute_ms` | `48.2` | rolul 3 (măsurat doar pentru afișare) | „copilotul a decis în 0,05 s” |
> | `site.json`, `meta.json` | 🆕 `artifacts` | `[{"id", "name", "type": "recovery_target \| landmark \| historical_hardware \| hazard_debris", "row", "col", "lat"?, "lon"?, "caution_radius_m", "note", "source", "status": "verified \| to verify \| synthetic"}]` (**deja în mock-uri**) | pipeline (rolul 1), trimis de `/api/site` | stratul „NASA hardware” pe hartă (POI, nu intră în rutare) |
> | `site.json`, `meta.json` | 🆕 `rover_traverse` | `{"name", "source", "sols": [a, b], "path": [[row, col], …]}` sau `null` (situl sintetic) | pipeline (rolul 1), din waypoint-urile NASA ale roverului | traseul real Perseverance pe hartă |
> | `GET /api/benchmark` | `headline` | `{"copilot_safe_pct": X, "plan_safe_pct": Y, "n_scenarios": 100}` (procente 0-100; cifrele reale vin din benchmark) | rolul 2 → rolul 3 | numărul de titlu pe slide și în UI |

## Convenții

- **Coordonate:** celule de grilă `{"row": r, "col": c}`, cu `row` crescând spre sud și `col` spre est. Celula are `cell_size_m` (20 m). Traseele sunt liste `[[row, col], ...]`.
- **Timp:** minute simulate de la începutul ieșirii (`t_min`).
- **Unități:** metri, minute, procente (O₂), mSv (doză), m/s (vânt), °C.
- **Decizii:** `CONTINUE | REROUTE | WAIT | RETURN | EMERGENCY`.
- **Preset-uri de ponderi:** `safe | fast | science`.
- **Verdict:** `GO | CAUTION | NO-GO`.

## Mesajele live

Mesajele WebSocket au mereu un câmp `type`:

- `tick`: starea la fiecare minut simulat (astronaut, senzori, pericole, traseu).
- `decision`: o decizie nouă a regulii, cu alternativele și ce le-a eliminat validatorul. Câmpul `explanation` e `null`, pentru că explicația vine separat. Alternative.path = traseul rămas complet, de la poziția curentă până la habitat; la wait, doar [position].
- `explanation`: textul explicației, legat prin `decision_id`. `source` e `llm` sau `template`.
- `event`: un eveniment injectat sau din scenariu (furtună, furtună solară, scurgere în costum etc.).

### Puncte proprii în planificare (15.11, contractul frontendului 1.1 §5)

Adăugiri compatibile la `POST /api/route`:
- **Cererea:** `custom_stops: [{"id": "note_…", "name", "row", "col", "tag": "waypoint|science|hazard|shelter", "dwell_min"}]`. Id-urile lor apar în `stops`, amestecate cu cele din catalog.
- **Răspunsul:**
  - fiecare oprire are în plus `name`, `row`, `col`, `source` (`catalog | custom`), `visit_order`;
  - `omitted` = opririle cerute pe care planificatorul le-a lăsat deoparte;
  - `validation_status: "validated"`.
- **Comportament:**
  - ordinea o alege planificatorul (CP-SAT) și e cea din `stops`;
  - punctele proprii nu apar în `GET /api/site`;
  - erorile (în afara grilei, teren interzis sau inaccesibil, id lipsă sau duplicat) dau 422 cu `detail` text.

### Traseele vin doar din backend (15.11, `docs/RAPORT_PANTA_20.md`)

- Frontendul nu mai are rutare proprie (`routing.worker.js` a fost șters): previzualizarea la clic pe hartă și traseul misiunii vin din `POST /api/route`.
- `route_request.preview` (opțional, implicit `false`): `true` = doar previzualizare. Traseul nu e salvat pentru simulare, iar `route_id` e `"preview"`.
- `route_response.budget.max_slope_deg` și `budget.ascent_m` (opționale): panta maximă și urcarea totală pe traseu, din straturile backendului (`slope`, `elevation`). Frontendul le afișează în loc să le calculeze pe grila lui de afișare.

### Câmpuri noi, opționale (arhitectura de rutare V2, `docs/roles/ARHITECTURA_RUTARE_V2.md`)

Adăugiri compatibile: exemplele vechi rămân valide, consumatorii le tratează ca opționale.

- `tick.mode`: modul de alertă `NOMINAL | MONITOR | REACT | EMERGENCY` (rata de re-evaluare). `tick.route_version`: crește la fiecare traseu nou aplicat.
- `tick.scan` (🆕 rolul 3, 15.11): scanarea împrejurimilor, făcută de cod la fiecare tick (fără LLM). `{status, text, t_min, problems[, hazard_id, hazard, distance_m][, eta_min]}`:
  - `status`: `clear` (niciun pericol), `watch` (pericol sau problemă activă, traseul e liber), `warning` (traseul întâlnește un pericol în fereastra de reacție), `danger` (astronautul e într-un pericol);
  - `text`: propoziția gata de afișat, în engleză; `problems`: problemele fără formă pe hartă (`solar_particle_event`, `suit_leak`, `fatigue`, `crewmate_injured`);
  - `hazard_id`, `hazard`, `distance_m` apar doar când există un pericol urmărit; `eta_min` doar când prognoza lui atinge traseul.
- Anunțurile de scanare: la fiecare situație nouă și sigură (start, pericol apărut departe, pericol dispărut) vine un `decision` cu `decision: CONTINUE`, `trigger: scan` și `reason_code` `ALL_CLEAR` sau `MONITORING`, urmat de `explanation` ca la orice decizie. Nu schimbă traseul. `MARSWALK_SCAN_ANNOUNCE=0` le oprește.
- `decision.phase`: `OUTBOUND | INBOUND`. Pe drumul spre casă (`INBOUND`) deciziile sunt `REROUTE` / `WAIT` (nu `RETURN`), iar drumul se replanifică la fel ca la dus.
- `decision.flags`: steaguri stabile, de ex. `NO_SHELTER`, `OFF_MAP`, `UNRECOVERABLE`, `ISOLATED`. `decision.omitted`: candidații omiși, `{id, reason[, merged_with]}`, cu `reason` ∈ `SIDESTEP_INFEASIBLE`, `WAYPOINT_OFF_MAP`, `NO_PATH`, `DUPLICATE`, `STOP_BLOCKED`, `HAZARD_GLOBAL`, `ISOLATED`. `decision.trigger`: `event | hazard | budget | proximity | periodic | resume | scan`.
- Id-urile alternativelor sunt șiruri libere: `current`, `detour_north|south|east|west`, `detour_free`, `wait`, `exit_zone`, `replan_stops`, `return`, `shelter`. Coduri de încălcare noi: `NO_RETURN_POINT`, `OFF_MAP`, `NO_SHELTER`.
- `live_event.json`: pe lângă `{event, params}`, `POST /api/live/event` acceptă un HazardSpec cu `op` = `add | update | remove` (vezi `_hazard_spec_example`, `_hazard_spec_update_example`, `_allowed_ops`). Un `update` re-ancorează pericolul la poziția curentă și crește `rev`; parametrii invalizi dau 422 cu un cod stabil (`NAN_VALUE`, `BAD_SHAPE`, `MISSING_CENTER`).
