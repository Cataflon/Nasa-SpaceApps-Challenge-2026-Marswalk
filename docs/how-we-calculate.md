# Cum calculăm

Sursa pentru ecranul „Cum calculăm” din aplicație și pentru slide-uri. Fiecare cifră are o sursă sau e marcată **presupunere**.

| Mărime | Formulă / valoare | Sursă | Status |
|---|---|---|---|
| Viteza de mers | Tobler: `6·exp(-3.5·|tan θ + 0.05|)` km/h × factor costum 0,6 | Tobler (1993); factor costum | presupunere |
| Consum O₂ | TODO | NASA NTRS (Apollo, teste de mers în costum) | de verificat |
| Rezervă O₂ la sosire | 30% | — | presupunere |
| Pantă maximă | 25° | studii NASA de ieșiri umane | de verificat |
| Marjă față de apus | 30 min | — | presupunere |
| Doza la suprafață | ~10 µSv/h (ordin de mărime) | Curiosity RAD | de verificat |
| Limita de doză pe ieșire | 1 mSv | — | presupunere |
| Apusul | Mars24 | NASA GISS | TODO |
| Apus efectiv cu praf | `apus − max(0, τ − 0,5)·30` min | — | presupunere |
| Preset-uri de ponderi | vezi `backend/app/core/costmap.py` | — | fix, ales de echipă |
