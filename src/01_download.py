"""Étape 1 : téléchargement des fichiers DVF géolocalisés (data.gouv.fr).

Un fichier par département et par année, enregistré dans data/raw/.
Si le téléchargement automatique échoue (URL modifiée, réseau), télécharge
les fichiers à la main depuis la page du jeu de données
« Demandes de valeurs foncières géolocalisées » sur data.gouv.fr
et place-les dans data/raw/ (format .csv ou .csv.gz, un fichier par département).
"""
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/departements/{dep}.csv.gz"
DEPARTEMENTS = ["75", "77", "78", "91", "92", "93", "94", "95"]  # Île-de-France
YEARS = [2022, 2023, 2024, 2025]


def download(year: int, dep: str) -> bool:
    dest = RAW / f"{year}_{dep}.csv.gz"
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  déjà présent : {dest.name}")
        return True
    url = BASE_URL.format(year=year, dep=dep)
    try:
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        print(f"  téléchargé   : {dest.name} ({dest.stat().st_size / 1e6:.1f} Mo)")
        return True
    except Exception as exc:  # noqa: BLE001
        if dest.exists():
            dest.unlink()
        print(f"  ÉCHEC        : {year}/{dep} -> {exc}")
        return False


def main() -> None:
    ok = sum(download(y, d) for y in YEARS for d in DEPARTEMENTS)
    total = len(YEARS) * len(DEPARTEMENTS)
    print(f"\n{ok}/{total} fichiers disponibles dans {RAW}")
    if not any(RAW.glob("*.csv*")):
        print("Aucun fichier : télécharge-les manuellement (voir l'en-tête de ce script).")
        sys.exit(1)


if __name__ == "__main__":
    main()
