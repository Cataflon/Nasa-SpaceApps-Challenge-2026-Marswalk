# Rolul 1: Date & prezentare

Ești unul dintre 4 agenți care implementează **simultan** Marswalk Copilot în același repo. Ceilalți trei lucrează la algoritmi (`backend/app/core/`), backend + LLM (`backend/app/api/`, `live/engine.py`, `llm/`) și frontend (`frontend/`). Tu ai datele, scenariile și documentația.

## Proiectul în 30 de secunde

Marswalk Copilot ajută un astronaut care iese pe jos pe Marte (delta din craterul Jezero). Are o hartă hiperlocală de 10×10 km pe grilă de 20 m, construită din date NASA, și un copilot live. Copilotul prezice pericolele (furtuni, radiație), generează trasee alternative și elimină variantele nesigure. O regulă deterministă alege varianta, iar un LLM local doar explică. **Codul decide, LLM-ul explică.**

Citește din `README.md`: secțiunile 2 (zona), 3 (sursele de date), 5.1 (pipeline-ul), 5.4 (modelul de pericol), 8 (demo-ul), 9 (riscuri), 10 (criterii). Citește și `shared/contracts/README.md` și `shared/contracts/meta.json`.

## Ce fișiere ai voie să modifici

- `pipeline/**` (inclusiv `pipeline/tests/`)
- `data/**` (`data/raw/` și `data/synthetic/` sunt ignorate de git; `data/processed/jezero/` intră în git)
- `docs/**`, **cu excepția** `docs/roles/**`. Singurul fișier pe care îl atingi acolo e `docs/roles/notes/rol1.md`.
- `backend/app/live/scenario.py`
- `backend/tests/scenario/**`

**Orice alt fișier e doar pentru citit.**

## Interfețele pe care le livrezi

### 1. Situl real: `data/processed/jezero/`

Exact același format ca situl sintetic (`pipeline/make_synthetic_site.py` e referința):

- `meta.json`: **toate** cheile din `shared/contracts/meta.json`, cu `site_id: "jezero"` și `source: "nasa"`. Ținte reale (argilă la frontul deltei, carbonați la margine etc.), fiecare cu pantă ≤ 25° în celula ei. Habitatul pe teren plat.
- `elevation.npy`, `slope.npy`, `terrain.npy`, `minerals.npy`, `radiation.npy`, `unsafe.npy`: forma `shape`, cu tipurile din `meta.json`. Convenție: `row` crește spre sud, `col` spre est, celula are 20 m.
- `png/<strat>.png` pentru fiecare strat, 500×500.
- Imaginile de la opriri: `png/stops/<target_id>.jpg` (≤ 300 KB fiecare). În `meta.json`, `targets[].image = "/static/layers/stops/<target_id>.jpg"`. Backendul servește deja `png/` la `/static/layers`, deci nu e nevoie de nicio schimbare în backend.
- Fiecare `.npy` ≤ 2 MB, fiecare PNG ≤ 1 MB.

Backendul îl încarcă cu `MARSWALK_SITE=jezero`, prin `backend/app/core/site_data.py` (doar citești fișierul, nu îl modifici).

### 2. Generatorul de scenarii: `backend/app/live/scenario.py`

Rolul 3 apelează `generate(seed, duration_min, events) -> Scenario`. Nu schimba semnătura și nici dataclass-urile.

- `Scenario.sensors` e o listă cu un dict pe minut, cu **exact** cheile: `dust_tau`, `wind_ms`, `temp_c`, `pressure_pa`, `dose_rate_usv_h`. O₂-ul și doza totală le calculează motorul (rolul 3), nu tu.
- Deterministic: `numpy.random.default_rng(seed)`. Aceeași intrare dă exact aceeași ieșire.
- Valorile sunt calibrate pe Perseverance MEDA, Curiosity REMS și RAD: intervale, ciclu diurn al temperaturii, rafale de vânt. Notează sursa fiecărei constante în comentariu.
- Evenimentele modifică seriile: `solar_particle_event` înmulțește `dose_rate_usv_h` pe durata lui, `regional_storm` crește treptat `dust_tau` și `wind_ms`, `local_storm` și `dust_devil` cresc local vântul și praful când trec. Partea spațială a furtunii o face `core/hazards.py` (rolul 2), nu tu.
- `DEMO_SCENARIO_EVENTS` = scenariul din demo (secțiunea 8 din README): furtună locală pe la minutul 72, furtună regională mai târziu.

## Sarcinile, în ordinea priorității

**P0, prima jumătate de zi:**
1. **Situl sintetic rămâne funcțional.** Poți face frontul deltei mai abrupt, ca să existe obstacole clare (acum doar ~1,3% din celule depășesc 25°, mai ales marginile craterelor). **Nu** schimba `HABITAT`, `TARGETS` și nici numele sau tipurile straturilor: ceilalți se bazează pe ele. Testele din `pipeline/tests/` trebuie să rămână verzi.
2. **`scenario.generate`** + teste în `backend/tests/scenario/test_scenario.py`: determinism, chei corecte, efectul fiecărui eveniment.
3. **`pipeline/fetch_stac.py`:** găsește colecțiile HiRISE DTM și CTX DTM în STAC-ul USGS, caută item-urile peste bbox-ul Jezero și decupează fereastra de 10×10 km din COG în `data/raw/jezero/` cu `rasterio.windows.from_bounds`, fără să descarci fișierele întregi. Verifică și corectează centrul zonei (`CENTER_LAT`, `CENTER_LON`).

**P1:**
4. **`pipeline/build_layers.py`:** din `data/raw/jezero/` în `data/processed/jezero/`. CTX acoperă toată zona, HiRISE are prioritate acolo unde există. Panta se calculează la rezoluția completă, apoi se agregă la 20 m păstrând **maximul**. `unsafe` vine din FOM-ul HiRISE, iar unde nu există FOM, din pantă > 35°.
5. **Minerale și teren:** CRISM și THEMIS dacă merg repede. **Plan B, dacă nu în 2-3 ore:** poligoane trasate manual după harta geologică USGS SIM 3464, scrise ca listă de coordonate în `pipeline/manual_units.py`. Radiația: același model ca în situl sintetic (doză în funcție de altitudine), declarat ca presupunere.

**P2:**
6. **`docs/sources.md`:** toate sursele din secțiunea 3 a README-ului, fiecare cu link **verificat** (deschis efectiv), ce date folosim din ea și statusul (verificat / de verificat).
7. **`docs/how-we-calculate.md`:** completează fiecare rând cu sursa. Constantele din `backend/app/core/budget.py` și `costmap.py` le citești (nu le modifici). Dacă vrei alte valori, scrie-le în notele tale la „Cereri pentru rolul 2”.
8. **`docs/demo.md`:** scenariul demo-ului de 2 minute, secundă cu secundă: ce se apasă și ce se spune. **`docs/slides.md`:** structura slide-urilor după criteriile juriului.
9. **Imaginile de la opriri:** imagini raw Perseverance (Mastcam-Z / Navcam) apropiate de fiecare țintă, redimensionate.

## Teste: rulează doar ce ai modificat

Din rădăcina repo-ului:

```bash
.venv/Scripts/python -m pytest -q pipeline/tests/test_synthetic.py
```

Din `backend/`:

```bash
../.venv/Scripts/python -m pytest tests/scenario/test_scenario.py
```

- **rasterio** și **pystac-client** le instalezi într-un mediu separat, ca să nu strici `.venv` comun:

  ```bash
  python -m venv .venv-pipeline
  .venv-pipeline/Scripts/pip install -r pipeline/requirements.txt
  ```

  Testele din `pipeline/tests/` folosesc doar numpy, pentru că CI-ul nu instalează rasterio. Testele care au nevoie de rasterio sau de rețea le marchezi `@pytest.mark.slow`, iar în fișierul lor pui `pytest.importorskip("rasterio")`.

## Reguli comune (obligatorii pentru toți cei 4 agenți)

### Git
- **NU** rula `git commit`, `git push`, `git add`, `git pull`, `git merge`, `git rebase`, `git stash`, `git checkout`, `git reset` sau orice altă comandă care schimbă starea repo-ului. Doar scrii cod. Ai voie la `git status` și `git diff`.
- Commit-ul și push-ul le fac oamenii, separat pentru fiecare rol. Folderele nu se suprapun, deci nu apar conflicte la merge.

### Fără interferențe
- Modifici **doar** fișierele din secțiunea „Ce fișiere ai voie să modifici”. Alți 3 agenți scriu în același timp în același repo.
- Nu muta, nu redenumi, nu șterge și nu reformata fișiere din afara zonei tale. Nu rula formatere sau lintere pe tot repo-ul (`black .`, `ruff --fix .`, `prettier --write .`), ci doar pe fișierele tale.
- **Înghețate:** `shared/contracts/**`, `backend/app/core/types.py`, `README.md`, `.gitignore`, `.github/**`, `backend/pytest.ini`, `backend/tests/conftest.py`, `backend/requirements.txt`, `frontend/package.json`. Dacă ai nevoie de o schimbare acolo, o scrii la „Cereri” în notele tale.
- Nu instala pachete în `.venv` comun și nu adăuga dependențe npm. Cererile le scrii în note.
- Dacă depinzi de o funcție a altui rol care încă aruncă `NotImplementedError`, **nu o implementa tu**. Folosește un fake în teste și un fallback în cod.
- Nu porni servere pe porturile 8000 sau 5173 (sunt ale oamenilor). Dacă ai nevoie de backend, folosește portul 8002.

### Teste
- Rulezi **doar** testele pentru fișierele pe care tocmai le-ai modificat, nu toată suita la fiecare schimbare.
- La finalul fiecărei sarcini, rulezi **o dată** toate testele din zona ta.
- Un test care durează peste 5 s se marchează `@pytest.mark.slow` și nu rulează implicit. Testele trebuie să fie deterministe (seed fix), fără rețea și fără Ollama.
- Testele noi stau doar în folderele tale de teste. Un test existent din zona ta poate fi modificat, nu șters.

### Cod
- Python compatibil cu 3.11 (CI rulează 3.12, local e 3.14). Comentariile și mesajele sunt în română, ca în restul codului; numele de variabile și funcții sunt în engleză.
- Determinism peste tot: seed fix, sortări stabile, fără `time.time()` în logică.

### Note de predare: `docs/roles/notes/rol1.md`
Le ții la zi după fiecare sarcină, cu secțiunile fixe **Gata**, **În lucru**, **Cereri** (pentru alt rol sau pentru oameni) și **Presupuneri** (cifre fără sursă). E singurul canal de comunicare cu ceilalți agenți.
