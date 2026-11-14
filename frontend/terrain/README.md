# Relief și habitat

Relieful geometric provine din DTM USGS CTX 20 m. Texturile procedurale de regolit sunt ilustrative: culoare, granulație și normal map nu reprezintă o ortofotografie și nu intră în calculul pantelor, distanțelor sau siguranței. Ele nu deplasează vârfurile modelului.

`materials.py` generează trei texturi PBR 2048² cu seed fix; `build_blender.py` le aplică pe teren și le include în GLB și în fișierul Blender. Umbrele aplicației sunt calculate din geometrie, iar iluminarea este de prezentare, nu o simulare a poziției Soarelui pe Marte.

`build_habitat.py` generează separat `habitat.blend`, `habitat.glb` și `habitat-preview.png`. Este un concept inspirat de Mars Dune Alpha: volum de referință 20 × 8 m și zonă EVA 10 × 11 m, straturi de imprimare, acoperiș jos curbat, sas și echipamente. Dimensiunile reprezintă o interpretare pentru machetă, nu planuri măsurate ale clădirii originale. Marcajul este mărit 12× în hartă pentru lizibilitate; nu se deduc dimensiuni reale din amprenta sa vizuală.

Referințe consultate:
- NASA CHAPEA: https://www.nasa.gov/humans-in-space/chapea/about-chapea/
- Proiectul arhitecților BIG: https://big.dk/projects/mars-chapea-4310
- NASA Spinoff / ICON: https://spinoff.nasa.gov/Mission_Home

Regenerare din `frontend/`:

```powershell
terrain/tools/blender-4.5.9-windows-x64/blender.exe --background --python terrain/build_blender.py
terrain/tools/blender-4.5.9-windows-x64/blender.exe --background --python terrain/build_habitat.py
npm.cmd run desktop:package
```
