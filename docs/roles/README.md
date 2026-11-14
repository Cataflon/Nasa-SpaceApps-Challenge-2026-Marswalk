# Rolurile pentru implementarea în paralel

> ## 🆕 NOU (14.11.2026)
> Au fost adăugate 7 funcționalități legate de tema challenge-ului: Survival Guide printabil (acum prioritate), contorul „Pământul vs. copilotul”, ceasul de întoarcere ca cifră principală, click pe hartă cu sursa fiecărei misiuni, numărul de titlu din benchmark, „Cum calculăm” cu fiecare constantă marcată și slide-ul salvamont. Tabelul cu ce face fiecare rol e în `README.md`, secțiunea „🆕 Noutăți”. **Fiecare fișier de rol are la început o casetă „🆕 NOU” cu sarcinile lui noi**, marcate 🆕 și în lista de sarcini.
>
> **Contractele:** câmpurile noi sunt toate **opționale** (`eva_start_ltst_h`, `earth_delay_min`, `sources`, `compute_ms`, `headline`). Exemplele JSON din `shared/contracts/` se actualizează de un om, cu acordul echipei. Până atunci, frontendul folosește fallback-urile din `ROL4_frontend.md`.

Patru agenți (sau oameni) lucrează **simultan**, fiecare pe fișierul lui:

| Fișier | Rol | Deține |
|---|---|---|
| [ROL1_date.md](ROL1_date.md) | Date & prezentare | `pipeline/`, `data/`, `docs/` (fără `docs/roles/`), `backend/app/live/scenario.py` |
| [ROL2_algoritmi.md](ROL2_algoritmi.md) | Algoritmi | `backend/app/core/` |
| [ROL3_backend_llm.md](ROL3_backend_llm.md) | Backend & LLM | `backend/app/api/`, `backend/app/live/engine.py`, `backend/app/llm/`, `schemas.py`, `config.py` |
| [ROL4_frontend.md](ROL4_frontend.md) | Frontend | `frontend/` |

Fiecare fișier de rol conține tot ce trebuie: contextul, ce fișiere poate modifica, interfețele, sarcinile în ordinea priorității, comenzile de test și regulile comune. Dați fiecărui agent **doar** fișierul lui, plus acces la repo.

## Cum se face commit-ul (de către oameni, nu de agenți)

Agenții **nu** fac commit și nici push. Pentru că fiecare rol are foldere separate, un om poate comite fiecare rol separat, fără conflicte. Înainte de fiecare commit, verifică cu `git status` că rolul nu a atins fișiere din afara zonei lui.

Rolul 1:

```bash
git add pipeline data backend/app/live/scenario.py backend/tests/scenario docs ':!docs/roles' docs/roles/notes/rol1.md
```

Rolul 2:

```bash
git add backend/app/core backend/tests/core docs/roles/notes/rol2.md
```

Rolul 3:

```bash
git add backend/app/api backend/app/live ':!backend/app/live/scenario.py' backend/app/llm backend/app/schemas.py backend/app/config.py backend/tests/api backend/tests/live backend/tests/llm docs/roles/notes/rol3.md
```

Rolul 4:

```bash
git add frontend docs/roles/notes/rol4.md
```

Apoi `git commit -m "rolN: ..."` după fiecare `git add`. La final, `git push` o singură dată.

## Fișiere înghețate (nu le modifică nimeni în timpul lucrului în paralel)

- `shared/contracts/**`
- `backend/app/core/types.py` (excepție: rolul 2 poate **adăuga** câmpuri cu valoare implicită la final)
- semnăturile funcțiilor publice din `backend/app/core/*.py` (rolul 2 poate adăuga doar parametri opționali)
- `README.md`, `.gitignore`, `.github/**`, `backend/pytest.ini`, `backend/tests/conftest.py`, `backend/requirements.txt`, `frontend/package.json`

Cine are nevoie de o schimbare aici o scrie în fișierul lui de note (`docs/roles/notes/rolN.md`), la secțiunea „Cereri”. Schimbările se fac de un om, după runda de lucru.

## CI pe GitHub

Fiecare rol are workflow-ul lui în `.github/workflows/`, declanșat **doar** de modificări în folderele rolului:

| Workflow | Se declanșează la | Rulează |
|---|---|---|
| `core.yml` | `backend/app/core/**` | `pytest tests/core` |
| `service.yml` | API, `live/engine.py`, LLM, contracte | `pytest tests/api tests/live tests/llm` |
| `data.yml` | `pipeline/**`, `scenario.py` | `pytest pipeline/tests` + `tests/scenario` |
| `frontend.yml` | `frontend/**`, contracte | `npm ci && npm run build` |

Testele marcate `slow` sau `ollama` nu rulează niciodată automat.
