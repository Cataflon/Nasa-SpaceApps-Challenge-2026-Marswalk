# Note rolul 1

## Gata

### 1. Situl sintetic v2 (`pipeline/make_synthetic_site.py`)
- **Frontul deltei e mai abrupt:** ~25% din front e perete de netrecut (> 25°), restul sunt rampe. Platoul deltei rămâne accesibil prin rampe. Panta maximă: 44°; celule interzise: 1,4%.
- `HABITAT`, `TARGETS`, numele, fișierele, tipurile și unitățile straturilor sunt **neschimbate**. Toate țintele sunt accesibile din habitat (verificat cu un flood-fill cu 8 vecini).
- `meta.json` are chei noi, **în plus** față de contract (nu s-a scos nimic):
  - `layers.<strat>.data_type` / `analog_of` / `source`: etichetele de proveniență pe fiecare strat;
  - `generator_version` (acum 2) și `fingerprint` (procent interzis, altitudinea medie).
- **Versiunea sitului:** `data/synthetic/` e în `.gitignore`, deci fiecare îl generează local. `python pipeline/make_synthetic_site.py --check` iese cu codul 1 dacă situl de pe disc e vechi. **După fiecare pull, rulați `python pipeline/make_synthetic_site.py`.**
- Teste: `pipeline/tests/test_synthetic.py` (9 teste, ~3 s). Marker-ul `slow` e înregistrat în `pipeline/tests/conftest.py`: testele lente se sar implicit și rulează cu `-m slow`.

### Modificări în afara zonei (cu acordul oamenilor)
- **`scripts/dev.ps1`:** dacă situl activ e cel sintetic, la pornire rulează `make_synthetic_site.py --check` și, dacă situl lipsește sau e vechi, îl regenerează.
- **`backend/app/api/main.py`, `GET /api/site`:** fiecare strat din `layers[]` primește și cheile opționale `data_type`, `mission`, `instrument`, `source`, `analog_of` și `product_id`, doar dacă există în `meta.json` (constanta `LAYER_LABEL_KEYS`). Câmpurile existente sunt neschimbate. **Rolul 4:** le puteți afișa ca etichete pe straturi.

## În lucru

## Cereri

- **Pentru oameni / rolul 4 (amânat, de reamintit):** `npm install` avertizează că scriptul `postinstall` al `esbuild@0.21.5` nu e aprobat (`npm install-scripts approve esbuild`). Dacă `npm run build` pică, de acolo e.

## Presupuneri
- Situl sintetic: geometria e inventată (înălțimea frontului ~55-75 m, lățimea între 12 și 172 m). Pe situl real, frontul vine din DTM.
