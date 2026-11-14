# Marswalk pentru Windows

Aplicație desktop Electron cu fereastră proprie. Interfața este inclusă local în aplicație; nu are nevoie de Vite sau de un browser deschis.

Din `frontend/`:

```powershell
npm.cmd run desktop
npm.cmd run desktop:package
```

Varianta portabilă rezultă în `release/Marswalk-win32-x64/Marswalk.exe`. Copiază întregul folder, nu doar executabilul. Backendul rămâne un proces separat; se configurează prin `BACKEND_URL` (implicit `http://127.0.0.1:8000`). Fără backend, aplicația folosește exemplele marcate ca mock.

Modelul real de relief este produs din DTM-ul oficial USGS CTX, decupat la 10 × 10 km în jurul coordonatelor 18,44 N / 77,45 E. Altitudinile originale în metri rămân intacte în `jezero.json` și în atributul Blender `USGS_elevation_m`. Mesh-ul de afișare folosește toate cele 250000 de eșantioane de 20 m, cu triangulație explicită și aceeași interpolare pentru trasee. Densitatea suplimentară față de modelul inițial nu inventează rezoluție sub 20 m.

Vizualizarea este exclusiv 3D, inclusiv navigatorul compact. Selectarea unei ținte etichetate sau a unui punct pe teren coboară camera din vederea de sus către o perspectivă laterală. Poți reveni cu „De sus”, roti liber, mări și compara „Pantă ponderată” / „Distanță minimă”. Habitatul are un model distinct și etichetă albă. Traseele locale A* sunt previzualizări pe relief (distanță, urcare, pantă), nu înlocuiesc validarea EVA din backend.

Prezentarea are o exagerare verticală **6×**, o bază geologică de **850 m în coordonatele scenei** și un soclu de 220 m. Aceste dimensiuni sunt de prezentare, nu măsurători geologice. Transformarea este `display_z = 850 + (altitudine_USGS − altitudine_referință) × 6`. Factorul și baza sunt exportate ca metadate GLB și folosite și la desenarea traseului/pozițiilor. Datele de rutare, pantele și bugetele nu se calculează din geometria exagerată.

Regenerare:

```powershell
node terrain/prepare.mjs terrain/source/jezero-ctx-20m.tif
terrain/tools/blender-4.5.9-windows-x64/blender.exe --background --python terrain/build_blender.py
```

Rezultate: `terrain/jezero.blend`, `public/terrain/jezero.glb`, `public/terrain/jezero.json`, `public/terrain/jezero-preview.png`.

Pozițiile și traseele din mock nu devin rute validate pe relieful real. Integrarea cu situl real din pipeline/core și verificarea habitatului/țintelor sunt necesare înaintea folosirii operaționale. Portul HTTP intern se deschide doar pe loopback; Electron nu expune Node în interfață și blochează navigarea externă.

## Colegii primesc sursele, nu folderul release

`frontend/.gitignore` exclude intenționat `release/`. Folderul conține runtime-ul Electron și fișiere generate; `git push` trimite doar fișierele urmărite de Git.

După clonare/pull, fiecare coleg pe Windows poate genera aplicația local:

```powershell
cd frontend
npm.cmd ci
npm.cmd run desktop:package
```

Executabilul apare în `frontend/release/Marswalk-win32-x64/Marswalk.exe`. Pentru distribuire fără compilare, arhivați întregul folder `Marswalk-win32-x64` și distribuiți ZIP-ul separat (de exemplu ca asset într-un GitHub Release). Nu mutați doar `.exe` și nu includeți runtime-ul generat în istoricul surselor.

Ghidul complet pentru colegi, de la clonare la lansarea backendului și aplicației desktop: [PORNIRE.md](../PORNIRE.md).
