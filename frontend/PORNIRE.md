# Lansarea Marswalk din surse — Windows

Ghid pentru colegii care clonează proiectul de pe GitHub. Aplicația desktop se construiește local; folderul `release` nu trebuie primit de la alt coleg.

## 1. Cerințe

- Git și o copie locală a repository-ului.
- Python 3.11 sau mai nou, conform cerințelor proiectului.
- Node.js 18 sau mai nou, cu npm, conform cerințelor proiectului.
- Acces la internet la prima instalare, pentru dependențele Python, npm și runtime-ul Electron.

Verificare într-un terminal PowerShell:

```powershell
py --version
node --version
npm.cmd --version
```

Dacă `py` nu există, dar `python --version` funcționează, folosește `python` în loc de `py -3` la crearea mediului de mai jos. Nu este necesar Blender pentru lansare: modelele exportate sunt deja în `frontend/public/terrain/`.

## 2. Instalarea inițială

Deschide PowerShell în rădăcina repository-ului, unde se află folderele `backend`, `frontend` și `pipeline`.

Creează mediul Python și instalează dependențele backendului:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

Instalează dependențele aplicației desktop:

```powershell
cd frontend
npm.cmd ci
cd ..
```

`npm.cmd ci` folosește versiunile din `package-lock.json`. Nu copia `node_modules` de la un coleg. Comenzile de mai jos folosesc direct Python din `.venv`, fără activarea mediului și fără schimbarea politicii PowerShell.

## 3. Lansarea zilnică: două terminale

### Terminalul 1 — backendul

Pornește din rădăcina repository-ului:

```powershell
$env:MARSWALK_SITE = "jezero"
$env:LIVE_MOCK = "0"
$env:LLM_ENABLED = "0"
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

- `MARSWALK_SITE=jezero` folosește datele din `data/processed/jezero/`, incluse în repository.
- `LIVE_MOCK=0` folosește motorul misiunii, nu redarea în buclă a contractului de exemplu.
- `LLM_ENABLED=0` permite lansarea fără Ollama; explicațiile folosesc fallback-ul din backend. Este o alegere pentru această comandă de pornire, nu o modificare a configurației proiectului.

Lasă terminalul deschis. Verifică backendul la `http://127.0.0.1:8000/api/health`. Documentația API se află la `http://127.0.0.1:8000/docs`.

### Terminalul 2 — aplicația desktop

Deschide un terminal nou în rădăcina aceluiași repository:

```powershell
cd frontend
$env:BACKEND_URL = "http://127.0.0.1:8000"
npm.cmd run desktop
```

Se compilează interfața și se deschide fereastra Electron **Marswalk Copilot**. Nu trebuie deschis un browser și nu trebuie pornit Vite separat. Păstrează terminalul deschis cât timp folosești aplicația.

În aplicație: creează planul EVA, apoi apasă **Start EVA** pentru a primi telemetrie de misiune. Vizualizarea locală a unui traseu și redarea lui în ceas/tracker sunt previzualizări; ele nu pornesc singure simularea backendului.

## 4. După ce primești actualizări de pe GitHub

Închide aplicația și oprește backendul cu `Ctrl+C` în terminalul lui. După actualizarea surselor, reinstalează dependențele dacă fișierele lor s-au schimbat:

```powershell
# Din rădăcina repository-ului:
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
cd frontend
npm.cmd ci
cd ..
```

Reia pașii din secțiunea 3. `npm.cmd run desktop` reconstruiește interfața înainte de lansare, deci încarcă și schimbările colegilor.

## 5. Opțiuni

### Situl sintetic

Dacă vrei scenariul sintetic, generează-l local din rădăcină:

```powershell
.\.venv\Scripts\python.exe pipeline/make_synthetic_site.py
$env:MARSWALK_SITE = "synthetic"
$env:LLM_ENABLED = "0"
$env:LIVE_MOCK = "0"
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

`data/synthetic/` este ignorat de Git, deci se generează pe fiecare calculator. Regenerează-l după actualizarea generatorului. Situl ales schimbă datele de planificare; relieful 3D împachetat rămâne Jezero. Pozițiile sintetice sunt ilustrative, iar alinierea reliefului cu situl backendului nu trebuie presupusă validată.

### Explicații prin Ollama

Ollama este opțional. Cu Ollama instalat și pornit și modelul disponibil local:

```powershell
ollama pull qwen2.5:7b-instruct
```

În terminalul backendului, înainte de comanda `uvicorn`, setează:

```powershell
$env:LLM_ENABLED = "1"
$env:OLLAMA_URL = "http://localhost:11434"
$env:OLLAMA_MODEL = "qwen2.5:7b-instruct"
```

Repornește backendul după schimbarea variabilelor. Explicațiile LLM sunt separate de deciziile motorului misiunii.

### Executabil generat local

Pentru a lansa ulterior o copie construită pe propriul calculator:

```powershell
cd frontend
npm.cmd run desktop:package
.\release\Marswalk-win32-x64\Marswalk.exe
```

Backendul se pornește separat, ca în secțiunea 3. După schimbarea surselor, rulează din nou `npm.cmd run desktop:package` pentru a actualiza această copie. Pentru lucrul zilnic este suficient `npm.cmd run desktop`.

## 6. Probleme uzuale

| Simptom | Ce verifici |
|---|---|
| Colegul nu are folderul `release` după clonare | Este normal: `frontend/.gitignore` îl exclude. Lansarea din surse folosește `npm.cmd run desktop`. |
| PowerShell blochează `npm.ps1` | Folosește comenzile `npm.cmd` din ghid. |
| `py`, `python`, `node` sau `npm.cmd` nu sunt recunoscute | Verifică instalarea și PATH, apoi deschide un terminal nou. |
| Portul 8000 este ocupat | Oprește instanța veche sau pornește backendul pe 8001 și setează `BACKEND_URL=http://127.0.0.1:8001` în terminalul desktopului. |
| Apar „Demo data”, valori exemplu sau nu vine telemetria | Verifică `/api/health`, planifică un traseu și pornește EVA. Fără backend, interfața poate folosi fallback-uri marcate ca demo. „Equipment demo” este separat și simulează doar dashboardul senzorilor. |
| Electron rulează ca Node sau nu deschide fereastra | În terminalul aplicației rulează `Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue`, apoi repetă `npm.cmd run desktop`. |
| Lipsesc datele sitului sintetic | Rulează generatorul din secțiunea 5. |
| Vrei actualizarea automată a codului backendului | Adaugă `--reload` la comanda `uvicorn`, doar pentru dezvoltare. |
| Se deschide un browser când folosești `scripts/dev.ps1` | Scriptul existent pornește Vite, varianta de dezvoltare în browser. Pentru aplicația desktop folosește secțiunea 3. |

## 7. Oprirea proiectului

Închide fereastra Marswalk. Dacă terminalul aplicației încă rulează, apasă `Ctrl+C`. În terminalul backendului apasă `Ctrl+C`. Datele, modelele și dependențele instalate rămân pe calculator pentru următoarea lansare.
