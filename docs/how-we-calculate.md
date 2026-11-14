# Cum calculăm

Sursa pentru ecranul „Cum calculăm” din aplicație și pentru slide-uri. Fiecare cifră are o sursă sau e marcată **presupunere**.

**Status** (rolul 4 îl afișează ca badge): `sursă` = valoare luată dintr-o sursă citită efectiv · `de verificat` = sursă cunoscută, încă necitită · `presupunere` = aleasă de noi, declarată ca atare.

| Mărime | Formulă / valoare | Sursă | Status |
|---|---|---|---|
| Viteza de mers | Tobler: `6·exp(-3.5·abs(tan θ + 0.05))` km/h × factor costum 0,6 | Tobler (1993); factor costum | presupunere |
| Consum O₂ | TODO | NASA NTRS (Apollo, teste de mers în costum) | de verificat |
| Rezervă O₂ la sosire | 30% | — | presupunere |
| Pantă maximă | 25° | studii NASA de ieșiri umane | de verificat |
| Marjă față de apus | 30 min | — | presupunere |
| Doza la suprafață | 26,7 µSv/h doză echivalentă (0,64 mSv/zi; doza absorbită e 0,21 mGy/zi) | Curiosity RAD, Hassler et al. 2014, Science | de verificat |
| Limita de doză pe ieșire | 1 mSv | — | presupunere |
| Apusul | Mars24 | NASA GISS | de verificat |
| Apus efectiv cu praf | `apus − max(0, τ − 0,5)·30` min | — | presupunere |
| Preset-uri de ponderi | vezi `backend/app/core/costmap.py` | — | presupunere |
| Ora de start a ieșirii | 09:00 ora solară locală (LTST); o oră marțiană = 61,65 min | Mars24 (durata solului) | presupunere |
| Întârzierea Pământ-Marte | ~3-22 min dus, după poziția planetelor; valoarea pentru data demo-ului: TODO | JPL Horizons / NASA | de verificat |
| Scenarii meteo și radiație | vezi `backend/app/live/scenario.py` (fiecare constantă are sursa în comentariu) | Perseverance MEDA, Curiosity REMS și RAD | de verificat |

> TODO (rolul 1, P1): câte un rând pentru **fiecare** constantă din `core/` (buget, cost, validator, pericole, decizie) și din `scenario.py`.
