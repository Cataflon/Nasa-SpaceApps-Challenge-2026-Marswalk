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
- `decision`: o decizie nouă a regulii, cu alternativele și ce le-a eliminat validatorul. Câmpul `explanation` e `null`, pentru că explicația vine separat.
- `explanation`: textul explicației, legat prin `decision_id`. `source` e `llm` sau `template`.
- `event`: un eveniment injectat sau din scenariu (furtună, furtună solară, scurgere în costum etc.).
