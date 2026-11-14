"""Construiește straturile pe grila de 20 m din datele brute (data/raw/jezero -> data/processed/jezero).

Pași:
  1. Pantă la rezoluția completă (HiRISE 1 m acolo unde există, altfel CTX ~20 m).
  2. Agregare la 20 m păstrând panta MAXIMĂ din fiecare celulă (ca să nu se piardă obstacolele).
  3. Mască `unsafe` din FOM-ul HiRISE.
  4. CRISM -> minerals (clase din meta.json), THEMIS -> terrain, radiație -> radiation.
  5. Scrie .npy + meta.json (același format ca make_synthetic_site.py) + PNG-urile.

Plan B dacă CRISM/THEMIS întârzie: ținte științifice puse manual după harta USGS SIM 3464.
"""


def main() -> None:
    raise NotImplementedError("TODO (rolul 1)")


if __name__ == "__main__":
    main()
